"""
Unit tests for Matter & Thread AI Diagnostic logic, Thread TLV decoding,
Matter Cluster 0x0035 parsing, and RLOC16/NeighborTable topology resolution.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from thread_analyzer import ThreadAnalyzer
from matter_client import MatterClient
from ha_client import parse_thread_dataset_tlv
from ai_engine import AIDiagnosticEngine


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


def test_ai_diagnostic_engine_key_and_model_validation():
    engine_gemini = AIDiagnosticEngine(provider="gemini", model="gemini-3.8-flash", gemini_key="AIzaSyDummyKeyTest")
    assert engine_gemini.has_valid_key() is True
    # User-selected model is preserved verbatim
    assert engine_gemini.model == "gemini-3.8-flash"

    engine_gemini_25 = AIDiagnosticEngine(provider="gemini", model="gemini-2.5-pro", gemini_key="AIzaSyDummyKeyTest")
    assert engine_gemini_25.model == "gemini-2.5-pro"

    engine_openai = AIDiagnosticEngine(provider="openai", model="o3-mini", openai_key="")
    assert engine_openai.has_valid_key() is False
    assert engine_openai.model == "o3-mini"

    engine_claude = AIDiagnosticEngine(provider="anthropic", model="claude-3-7-sonnet-latest", anthropic_key="sk-ant-validtestkey")
    assert engine_claude.has_valid_key() is True
    assert engine_claude.model == "claude-3-7-sonnet-latest"

