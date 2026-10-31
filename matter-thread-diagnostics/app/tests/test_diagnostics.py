"""
Unit tests for Matter & Thread AI Diagnostic logic, Thread TLV decoding,
Matter Cluster 0x0035 parsing, and RLOC16/NeighborTable topology resolution.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from thread_analyzer import ThreadAnalyzer
from matter_client import MatterClient
from ha_client import HAClient, parse_thread_dataset_tlv
from ai_engine import AIDiagnosticEngine
from network_checker import NetworkChecker


def test_parse_thread_dataset_tlv():
    # Construct a real Thread TLV hex:
    # 0x00 (Channel, len 3): page 0, channel 25 (0x0019) -> 0003000019
    # 0x01 (PAN ID, len 2): 0x1234 -> 01021234
    # 0x02 (Ext PAN ID, len 8): 1122334455667788 -> 02081122334455667788
    # 0x03 (Network Name, len 6): "MyMesh" -> 03064d794d657368
    # 0x07 (Mesh-Local Prefix, len 8): fd11:2233:4455:6677 -> 0708fd11223344556677
    tlv_hex = "0003000019010212340208112233445566778803064d794d6573680708fd11223344556677"
    decoded = parse_thread_dataset_tlv(tlv_hex)
    assert decoded["channel"] == 25
    assert decoded["pan_id"] == "0x1234"
    assert decoded["extended_pan_id"] == "1122334455667788"
    assert decoded["network_name"] == "MyMesh"
    assert decoded["mesh_local_prefix"] == "fd11:2233:4455:6677::/64"


def test_matter_cluster_0x0035_parsing_and_parent_child_resolution():
    mc = MatterClient()
    raw_nodes = [
        # Node 1: Mains-powered Thread Router (RLOC16 0x2800 = 10240)
        {
            "node_id": 1,
            "available": True,
            "attributes": {
                "0/40/1": "Eve Systems",
                "0/40/3": "Eve Energy",
                "0/51/0": [{"0": "wpan0", "1": True, "6": ["fd11:2233:4455:6677::1"]}],
                "0/53/0": 25,
                "0/53/1": 5,  # Router
                "0/53/2": "MyMesh",
                "0/53/3": 0x1234,
                "0/53/4": 0x1122334455667788,
                "0/53/7": [
                    # Child node 2 in router's neighbor table (RLOC16 0x2801 = 10241)
                    {
                        "0": 0xAABBCCDDEEFF0002,
                        "1": 30,
                        "2": 0x2801,
                        "5": 240,
                        "6": -58,
                        "7": -56,
                        "13": True,  # isChild
                    }
                ],
                "0/53/62": 0xAABBCCDDEEFF0001,
                "0/53/63": 0x2800,
            },
        },
        # Node 2: Sleepy End Device attached to Node 1 (RLOC16 0x2801 = 10241)
        {
            "node_id": 2,
            "available": True,
            "attributes": {
                "0/40/1": "Aqara",
                "0/40/3": "Contact Sensor P2",
                "0/53/0": 25,
                "0/53/1": 2,  # Sleepy End Device
                "0/53/4": 0x1122334455667788,
                "0/53/7": [],
                "0/53/62": 0xAABBCCDDEEFF0002,
                "0/53/63": 0x2801,
            },
        },
    ]

    formatted = mc._format_nodes(raw_nodes)
    assert len(formatted) == 2
    router = formatted[0]
    sed = formatted[1]

    assert router["routing_role"] == "Router"
    assert router["rloc16"] == "0x2800"
    assert router["extended_pan_id"] == "1122334455667788"
    assert "fd11:2233:4455:6677::1" in router["ipv6_addresses"]

    # SED should inherit RSSI/LQI and parent RLOC16 from parent router's NeighborTable
    assert sed["routing_role"] == "Sleepy End Device (SED/ICD)"
    assert sed["rloc16"] == "0x2801"
    assert sed["rssi"] == -56
    assert sed["lqi"] == 240
    assert sed["parent_rloc16"] == "0x2800"

    # Build topology and verify real parent-child link between Node 1 and Node 2
    topo = ThreadAnalyzer.build_real_mesh_topology(
        discovered_routers=[{
            "name": "HA OTBR",
            "type": "ha",
            "extended_pan_id": "1122334455667788",
            "channel": 25,
        }],
        matter_nodes=formatted,
    )
    assert len(topo["nodes"]) == 3
    edge_pairs = {(e["source"], e["target"]) for e in topo["edges"]}
    assert ("node_1", "node_2") in edge_pairs or ("node_2", "node_1") in edge_pairs


def test_rf_coexistence_channel_11_conflict():
    result = ThreadAnalyzer.analyze_rf_coexistence(11, detected_wifi_channels=[1])
    assert result["thread_channel"] == 11
    assert result["severity"] == "HIGH"
    assert result["overlapping_wifi_channel"] == 1
    assert 1 in result["detected_conflicts"]
    assert "Channel 25" in result["recommendation"]


def test_rf_coexistence_channel_25_clean():
    result = ThreadAnalyzer.analyze_rf_coexistence(25, detected_wifi_channels=[1, 6, 11])
    assert result["thread_channel"] == 25
    assert result["severity"] == "MINIMAL"
    assert result["overlapping_wifi_channel"] is None
    assert len(result["detected_conflicts"]) == 0


def test_detect_split_networks_detected():
    routers = [
        {"extended_pan_id": "1111222233334444", "name": "Apple TV 4K", "channel": 15},
        {"extended_pan_id": "AAAABBBBCCCCDDDD", "name": "Home Assistant SkyConnect", "channel": 15},
    ]
    datasets = []
    analysis = ThreadAnalyzer.detect_split_networks(routers, datasets)
    assert analysis["is_split_network"] is True
    assert analysis["distinct_network_count"] == 2
    assert "CRITICAL" in analysis["summary"]


def test_detect_split_networks_synchronized():
    routers = [
        {"extended_pan_id": "1111222233334444", "name": "Apple TV 4K", "channel": 15},
        {"extended_pan_id": "1111222233334444", "name": "Home Assistant SkyConnect", "channel": 15},
    ]
    datasets = [{"extended_pan_id": "1111222233334444", "network_name": "MyMesh"}]
    analysis = ThreadAnalyzer.detect_split_networks(routers, datasets)
    assert analysis["is_split_network"] is False
    assert analysis["distinct_network_count"] == 1
    assert "healthy" in analysis["recommendation"].lower()


def test_evaluate_node_link_quality():
    nodes = [
        {"node_id": 1, "product_name": "Eve Plug", "available": True, "rssi": -60},
        {"node_id": 2, "product_name": "Aqara Contact P2", "available": True, "rssi": -86},  # Weak
        {"node_id": 3, "product_name": "Eve Motion", "available": False, "rssi": None},      # Offline
    ]
    result = ThreadAnalyzer.evaluate_node_link_quality(nodes)
    assert result["total_nodes"] == 3
    assert result["healthy_count"] == 1
    assert result["weak_count"] == 1
    assert result["offline_count"] == 1
    assert len(result["weak_nodes"]) == 1
    assert len(result["offline_nodes"]) == 1
    assert result["health_score"] < 80

    # Verify OpenThread 2-bit Link Quality scale (0-3) where lqi=3 (Excellent) and lqi=2 (Good) are 100% healthy
    ot_nodes = [
        {"node_id": 13, "product_name": "Node 13", "available": True, "rssi": -51, "lqi": 3},
        {"node_id": 14, "product_name": "Node 14", "available": True, "rssi": -58, "lqi": 3},
        {"node_id": 16, "product_name": "Node 16", "available": True, "rssi": -62, "lqi": 2},
    ]
    ot_res = ThreadAnalyzer.evaluate_node_link_quality(ot_nodes)
    assert ot_res["healthy_count"] == 3
    assert ot_res["weak_count"] == 0
    assert ot_res["health_score"] == 100


def test_ai_diagnostic_engine_key_and_model_validation():
    engine_gemini = AIDiagnosticEngine(provider="gemini", model="gemini-3.8-flash", gemini_key="AIzaSyDummyKeyTest")
    assert engine_gemini.has_valid_key() is True
    # User-selected model is preserved verbatim
    assert engine_gemini.model == "gemini-3.8-flash"

    # Verify live ListModels ranking resolves gemini-3.8-flash to live gemini-3* / gemini-2.5* and never dead 1.5
    live_sample = [
        {"value": "gemini-3-flash-preview", "label": "Gemini 3 Flash Preview"},
        {"value": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
        {"value": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
    ]
    ranked = engine_gemini._pick_best_live_gemini_model("gemini-3.8-flash", live_sample)
    assert ranked[0] == "gemini-3-flash-preview"
    assert "gemini-1.5-flash" not in ranked

    engine_gemini_25 = AIDiagnosticEngine(provider="gemini", model="gemini-2.5-pro", gemini_key="AIzaSyDummyKeyTest")
    assert engine_gemini_25.model == "gemini-2.5-pro"

    engine_openai = AIDiagnosticEngine(provider="openai", model="o3-mini", openai_key="")
    assert engine_openai.has_valid_key() is False
    assert engine_openai.model == "o3-mini"

    engine_claude = AIDiagnosticEngine(provider="anthropic", model="claude-3-7-sonnet-latest", anthropic_key="sk-ant-validtestkey")
    assert engine_claude.has_valid_key() is True
    assert engine_claude.model == "claude-3-7-sonnet-latest"


def test_border_router_multi_source_deduplication():
    """Verify routers discovered by both HA Discovery and Live UDP mDNS (including partial UNKNOWN mDNS replies) are merged without duplication."""
    ha_routers = [
        {
            "instance_name": "Home Assistant OpenThread Border Router #F8E4",
            "brand_name": "Home Assistant",
            "model_name": "OpenThread Border Router",
            "network_name": "NEST-PAN-2E89",
            "extended_pan_id": "49F5DAF7314F6B62",
            "extended_address": "AABBCCDDEEFF0001",
            "thread_version": "1.4.0",
            "addresses": ["192.168.86.38"],
            "source": "mDNS / HA Discovery",
        },
        {
            "instance_name": "Nest Wifi Mesh #9074",
            "brand_name": "Google",
            "model_name": "Nest Wifi Mesh",
            "network_name": "NEST-PAN-2E89",
            "extended_pan_id": "49F5DAF7314F6B62",
            "extended_address": "AABBCCDDEEFF0002",
            "thread_version": "1.4.0",
            "addresses": ["192.168.86.1"],
            "source": "mDNS / HA Discovery",
        },
        {
            "instance_name": "Nest Wifi Mesh #9166",
            "brand_name": "Google",
            "model_name": "Nest Wifi Mesh",
            "network_name": "NEST-PAN-2E89",
            "extended_pan_id": "49F5DAF7314F6B62",
            "extended_address": "AABBCCDDEEFF0003",
            "thread_version": "1.4.0",
            "addresses": ["192.168.86.130"],
            "source": "mDNS / HA Discovery",
        },
        {
            "instance_name": "Nursery",
            "brand_name": "Apple",
            "model_name": "BorderRouter",
            "network_name": "NEST-PAN-2E89",
            "extended_pan_id": "49F5DAF7314F6B62",
            "extended_address": "AABBCCDDEEFF0004",
            "thread_version": "1.4.0",
            "addresses": ["192.168.86.41"],
            "source": "mDNS / HA Discovery",
        },
    ]
    mdns_routers = [
        {
            "instance_name": "Nest Wifi Mesh #9074",
            "vendor_name": "Google",
            "model_name": "Nest Wifi Mesh",
            "network_name": "NEST-PAN-2E89",
            "extended_pan_id": "49F5DAF7314F6B62",
            "ext_address": "AABBCCDDEEFF0002",
            "border_agent_id": "11111111222222223333333344444444",
            "addresses": ["192.168.86.1"],
            "source": "Live UDP mDNS (_meshcop._udp)",
        },
        {
            "instance_name": "Nest Wifi Mesh #9166",
            "vendor_name": "Google",
            "model_name": "Nest Wifi Mesh",
            "network_name": "NEST-PAN-2E89",
            "extended_pan_id": "49F5DAF7314F6B62",
            "ext_address": "AABBCCDDEEFF0003",
            "border_agent_id": "55555555666666667777777788888888",
            "addresses": ["192.168.86.130"],
            "source": "Live UDP mDNS (_meshcop._udp)",
        },
        {
            "instance_name": "Nursery",
            "network_name": "Nursery",
            "extended_pan_id": "UNKNOWN",
            "addresses": ["192.168.86.41"],
            "source": "Live UDP mDNS (_meshcop._udp)",
        },
        {
            "instance_name": "Home Assistant OpenThread Border Router #F8E4",
            "vendor_name": "Home Assistant",
            "model_name": "OpenThread Border Router",
            "network_name": "NEST-PAN-2E89",
            "extended_pan_id": "49F5DAF7314F6B62",
            "ext_address": "AABBCCDDEEFF0001",
            "border_agent_id": "99999999AAAAAAAABBBBBBBBCCCCCCCC",
            "addresses": ["fe80::f55d:7222:4687:b814"],
            "source": "Live UDP mDNS (_meshcop._udp)",
        },
    ]
    datasets = [
        {
            "extended_pan_id": "49F5DAF7314F6B62",
            "network_name": "NEST-PAN-2E89",
            "channel": 21,
            "pan_id": "0x2e89",
            "mesh_local_prefix": "fd39:7b97:c02d::/64",
            "preferred": True,
        }
    ]
    res = ThreadAnalyzer.detect_split_networks(
        border_routers=ha_routers,
        active_datasets=datasets,
        mdns_routers=mdns_routers,
        target_network_id="49F5DAF7314F6B62",
    )
    assert len(res["all_discovered_routers"]) == 4, f"Expected 4 deduplicated routers, got {len(res['all_discovered_routers'])}"
    assert res["is_split_network"] is False
    assert res["distinct_network_count"] == 1
    assert "UNKNOWN" not in res["networks"]
    nursery = next(r for r in res["all_discovered_routers"] if r["name"] == "Nursery")
    assert nursery["extended_pan_id"] == "49F5DAF7314F6B62"
    assert nursery["brand"] == "Apple"
    assert nursery["is_target_network"] is True
    ha_otbr = next(r for r in res["all_discovered_routers"] if "F8E4" in r["name"])
    assert ha_otbr["addresses"][0] == "192.168.86.38"
    assert "fe80::f55d:7222:4687:b814" in ha_otbr["addresses"]

    # Verify only 1 Border Router is marked preferred (never all 4)
    preferred_routers = [r for r in res["all_discovered_routers"] if r.get("preferred")]
    assert len(preferred_routers) == 1, f"Expected exactly 1 preferred border router, got {len(preferred_routers)}"

    # Verify topology RF proximity spring distance calculation
    topo = ThreadAnalyzer.build_real_mesh_topology(
        discovered_routers=res["all_discovered_routers"],
        matter_nodes=[
            {"node_id": 10, "product_name": "Close Plug", "available": True, "rssi": -50, "extended_pan_id": "49F5DAF7314F6B62"},
            {"node_id": 11, "product_name": "Far Sensor", "available": True, "rssi": -88, "extended_pan_id": "49F5DAF7314F6B62"},
        ],
    )
    edge_close = next(e for e in topo["edges"] if e["target"] == "node_10" or e["source"] == "node_10")
    edge_far = next(e for e in topo["edges"] if e["target"] == "node_11" or e["source"] == "node_11")
    assert edge_close["target_distance"] < edge_far["target_distance"], "Stronger RSSI node must have shorter target spring distance"


def test_ha_friendly_name_and_area_enrichment():
    """Verify Matter nodes are enriched with their Home Assistant friendly name, Area, and Entity ID."""
    nodes = [
        {
            "node_id": 13,
            "product_name": "Essentials A19",
            "vendor_name": "Nanoleaf",
            "serial_number": "NL12345",
            "available": True,
        },
        {
            "node_id": 14,
            "product_name": "Eve Energy",
            "vendor_name": "Eve Systems",
            "available": True,
        },
    ]
    device_registry = [
        {
            "id": "dev_13",
            "name": "Nanoleaf A19",
            "name_by_user": "Living Room Light",
            "area_id": "living_room",
            "identifiers": [["matter", "deviceid_8877665544332211-000000000000000D-MatterNodeDevice"]],
        },
        {
            "id": "dev_14",
            "name": "Eve Energy",
            "name_by_user": None,
            "area_id": "kitchen",
            "identifiers": [["matter", "deviceid_8877665544332211-000000000000000E-MatterNodeDevice"]],
        },
    ]
    area_registry = [
        {"area_id": "living_room", "name": "Living Room"},
        {"area_id": "kitchen", "name": "Kitchen"},
    ]
    entity_registry = [
        {"device_id": "dev_13", "entity_id": "light.living_room_light", "name": None},
        {"device_id": "dev_14", "entity_id": "switch.kitchen_coffee_plug", "name": "Kitchen Coffee Plug"},
    ]

    HAClient.enrich_matter_nodes_with_ha_names(
        nodes,
        device_registry=device_registry,
        area_registry=area_registry,
        entity_registry=entity_registry,
    )

    assert nodes[0]["ha_name"] == "Living Room Light"
    assert nodes[0]["product_name"] == "Living Room Light"
    assert nodes[0]["hardware_model"] == "Essentials A19"
    assert nodes[0]["ha_area"] == "Living Room"
    assert nodes[0]["ha_entity_id"] == "light.living_room_light"

    assert nodes[1]["ha_name"] == "Kitchen Coffee Plug"
    assert nodes[1]["product_name"] == "Kitchen Coffee Plug"
    assert nodes[1]["hardware_model"] == "Eve Energy"
    assert nodes[1]["ha_area"] == "Kitchen"
    assert nodes[1]["ha_entity_id"] == "switch.kitchen_coffee_plug"


def test_zbt1_channel_management():
    """Verify ZBT-1 / OTBR channel boundary validation and 11-26 RF spectrum matrix generation."""
    import asyncio

    # Test invalid channel boundaries (< 11 or > 26)
    loop = asyncio.new_event_loop()
    try:
        err_low = loop.run_until_complete(NetworkChecker.set_otbr_channel_direct(10))
        assert err_low["success"] is False
        assert "Invalid channel" in err_low["error"]

        err_high = loop.run_until_complete(NetworkChecker.set_otbr_channel_direct(27))
        assert err_high["success"] is False
        assert "Invalid channel" in err_high["error"]

        ha = HAClient()
        ha_err_low = loop.run_until_complete(ha.set_otbr_channel(9))
        assert ha_err_low["success"] is False
        assert "Invalid Thread channel" in ha_err_low["error"]

        status = loop.run_until_complete(ha.get_zbt1_channel_status())
        assert "hardware" in status
        assert "channels_matrix" in status
        matrix = status["channels_matrix"]
        assert len(matrix) == 16, f"Expected 16 channels (11 to 26), got {len(matrix)}"

        # Check Ch 25 & 26 recommendation tags
        ch25 = next(c for c in matrix if c["channel"] == 25)
        ch26 = next(c for c in matrix if c["channel"] == 26)
        assert ch25["is_recommended"] is True
        assert ch26["is_recommended"] is True
        assert "Cleanest" in ch26["recommendation_badge"]

        # Test HAClient.set_otbr_channel with simulated HA WebSocket success
        commands_received = []

        async def mock_query_ws(cmd, timeout=12.0):
            commands_received.append(cmd)
            if cmd.get("type") == "otbr/info":
                return {
                    "type": "result",
                    "success": True,
                    "result": {
                        "49f5daf7314f6b62": {
                            "channel": 21,
                            "extended_address": "49f5daf7314f6b62",
                            "extended_pan_id": "49f5daf7314f6b62",
                        }
                    },
                }
            return {"type": "result", "success": True, "result": None}

        ha.supervisor_token = "test-token"
        ha.query_ha_websocket = mock_query_ws

        res = loop.run_until_complete(ha.set_otbr_channel(25))
        assert res["success"] is True
        assert res["channel"] == 25
        assert res["method"] == "ha_websocket"
        # Verify otbr/set_channel command includes the required extended_address
        otbr_cmds = [c for c in commands_received if c.get("type") == "otbr/set_channel"]
        assert len(otbr_cmds) == 1
        assert otbr_cmds[0] == {
            "type": "otbr/set_channel",
            "channel": 25,
            "extended_address": "49f5daf7314f6b62",
        }

        # Test HAClient.get_available_join_networks
        commands_received.clear()

        async def mock_join_ws(cmd, timeout=12.0):
            commands_received.append(cmd)
            t = cmd.get("type")
            if t == "otbr/info":
                return {
                    "type": "result",
                    "success": True,
                    "result": {
                        "49f5daf7314f6b62": {
                            "channel": 21,
                            "extended_address": "49f5daf7314f6b62",
                            "extended_pan_id": "49f5daf7314f6b62",
                        }
                    },
                }
            elif t == "thread/list_datasets":
                return {
                    "type": "result",
                    "success": True,
                    "result": {
                        "preferred_dataset": "ds_nest_2e89",
                        "datasets": [
                            {
                                "dataset_id": "ds_nest_2e89",
                                "network_name": "NEST-PAN-2E89",
                                "pan_id": 0x2E89,
                                "extended_pan_id": "49f5daf7314f6b62",
                                "channel": 21,
                                "preferred": True,
                            },
                            {
                                "dataset_id": "ds_apple_home",
                                "network_name": "Nursery-Mesh",
                                "pan_id": 0x1A2B,
                                "extended_pan_id": "1122334455667788",
                                "channel": 25,
                                "preferred": False,
                            },
                        ],
                    },
                }
            elif t in ("otbr/set_network", "thread/set_preferred_dataset", "thread/add_dataset_tlv"):
                return {"type": "result", "success": True, "result": None}
            return {"type": "result", "success": True, "result": None}

        ha.query_ha_websocket = mock_join_ws
        joinable = loop.run_until_complete(ha.get_available_join_networks())
        assert "current_mesh" in joinable
        assert len(joinable["networks"]) == 2
        # Verify NEST-PAN-2E89 is marked as current active mesh
        nest_net = next(n for n in joinable["networks"] if n["dataset_id"] == "ds_nest_2e89")
        assert nest_net["is_current"] is True
        apple_net = next(n for n in joinable["networks"] if n["dataset_id"] == "ds_apple_home")
        assert apple_net["is_current"] is False

        # Test HAClient.join_thread_network
        commands_received.clear()
        join_res = loop.run_until_complete(ha.join_thread_network(dataset_id="ds_apple_home", make_preferred=True))
        assert join_res["success"] is True
        assert join_res["dataset_id"] == "ds_apple_home"

        # Verify WebSocket commands sent: otbr/set_network and thread/set_preferred_dataset
        set_net_cmds = [c for c in commands_received if c.get("type") == "otbr/set_network"]
        assert len(set_net_cmds) == 1
        assert set_net_cmds[0] == {
            "type": "otbr/set_network",
            "extended_address": "49f5daf7314f6b62",
            "dataset_id": "ds_apple_home",
        }

        set_pref_cmds = [c for c in commands_received if c.get("type") == "thread/set_preferred_dataset"]
        assert len(set_pref_cmds) == 1
        assert set_pref_cmds[0] == {
            "type": "thread/set_preferred_dataset",
            "dataset_id": "ds_apple_home",
        }
    finally:
        loop.close()




