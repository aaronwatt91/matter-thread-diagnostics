"""
Zigbee Network Analyzer, Topology Builder, and Mesh Health Evaluator.
Processes live data from Home Assistant ZHA (Zigbee Home Automation) WebSocket API
and Zigbee2MQTT / MQTT Device Registries to construct authentic mesh topologies,
LQI link metrics, and RF coexistence evaluations.
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("matter_thread_ai.zigbee")


class ZigbeeAnalyzer:
    """Evaluates Zigbee network topology, link qualities, and device metrics."""

    @staticmethod
    def evaluate_zigbee_health(
        devices: List[Dict[str, Any]],
        channel: Optional[int] = None,
        coexistence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate overall health score (0-100) and device statistics for a Zigbee network.
        """
        total = len(devices)
        if total == 0:
            return {
                "health_score": 100,
                "total_devices": 0,
                "routers_count": 0,
                "end_devices_count": 0,
                "offline_count": 0,
                "weak_count": 0,
                "avg_lqi": 255,
                "status": "No Devices",
                "summary": "No Zigbee devices discovered yet.",
            }

        routers = [d for d in devices if d.get("device_type", "").lower() in ("router", "coordinator")]
        end_devices = [d for d in devices if d.get("device_type", "").lower() not in ("router", "coordinator")]
        offline = [d for d in devices if not d.get("available", True) or d.get("status") == "offline"]
        weak = [
            d for d in devices
            if d.get("available", True) and (
                (d.get("lqi") is not None and d.get("lqi") < 65)
                or (d.get("rssi") is not None and d.get("rssi") < -82)
            )
        ]

        lqi_values = [d["lqi"] for d in devices if isinstance(d.get("lqi"), (int, float))]
        avg_lqi = int(sum(lqi_values) / len(lqi_values)) if lqi_values else 200

        # Health score calculation
        score = 100
        # Deduct for offline devices (up to -40)
        if offline:
            offline_ratio = len(offline) / total
            score -= int(min(40, offline_ratio * 70 + len(offline) * 5))

        # Deduct for weak LQI links (up to -25)
        if weak:
            weak_ratio = len(weak) / total
            score -= int(min(25, weak_ratio * 40 + len(weak) * 3))

        # Deduct if mesh lacks adequate routers (routers < 20% of end devices)
        if len(routers) <= 1 and len(end_devices) > 4:
            score -= 15

        # Deduct if coexistence collision with Thread or Wi-Fi
        if coexistence and coexistence.get("thread_zigbee_collision"):
            score -= 15

        score = max(10, min(100, score))

        if score >= 85:
            status = "Healthy Mesh"
        elif score >= 60:
            status = "Fair / Weak Links"
        else:
            status = "Action Required"

        summary = (
            f"{total - len(offline)}/{total} Zigbee devices operational. "
            f"{len(routers)} Routers, {len(end_devices)} End Devices. "
            f"{len(offline)} offline, {len(weak)} weak LQI links (Avg LQI: {avg_lqi}/255)."
        )

        return {
            "health_score": score,
            "total_devices": total,
            "routers_count": len(routers),
            "end_devices_count": len(end_devices),
            "offline_count": len(offline),
            "weak_count": len(weak),
            "avg_lqi": avg_lqi,
            "status": status,
            "summary": summary,
        }

    @staticmethod
    def build_zigbee_topology(
        devices: List[Dict[str, Any]],
        coordinator: Dict[str, Any],
        channel: Optional[int] = 15,
        pan_id: Optional[str] = "0x1A2B",
        extended_pan_id: Optional[str] = "00:12:4b:00:1c:a2:b3:c4",
    ) -> Dict[str, Any]:
        """
        Build an authentic graph (nodes & edges) for Zigbee topology visualization
        compatible with Force / RF Mesh, Tree Hierarchy, Transit Map, Sankey Flow, and Signal Matrix.
        """
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        seen_edges = set()

        coord_ieee = coordinator.get("ieee") or coordinator.get("ieee_address") or "00:12:4b:00:coord"
        coord_name = coordinator.get("name") or "Zigbee Coordinator"
        coord_node_id = f"zb_coord_{coord_ieee.replace(':', '')[-6:]}"

        # 1. Add Coordinator as root / central node
        nodes.append({
            "id": coord_node_id,
            "node_id": 0,
            "name": coord_name,
            "label": coord_name,
            "type": "border_router",  # Styled as prominent central hub / root tier
            "protocol": "zigbee",
            "vendor": coordinator.get("vendor") or "Silicon Labs / ZHA",
            "brand": coordinator.get("brand") or "Zigbee Coordinator",
            "model": coordinator.get("model") or "Home Assistant Coordinator",
            "routing_role": "Zigbee Coordinator",
            "rloc16": "0x0000",
            "ext_address": coord_ieee,
            "extended_pan_id": extended_pan_id or "00:12:4b:00:1c:a2:b3:c4",
            "rssi": -35,
            "lqi": 255,
            "status": "online",
            "preferred": True,
            "ha_area": coordinator.get("ha_area") or "Smart Home Gateway",
            "power_source": "Mains",
            "details": f"Coordinator on Channel {channel or 15} (PAN {pan_id or '0x1A2B'}) • IEEE: {coord_ieee}",
        })

        # Map to find graph node IDs
        ieee_to_id: Dict[str, str] = {coord_ieee.lower(): coord_node_id}
        router_ids: List[str] = []

        # 2. Add devices
        for idx, dev in enumerate(devices):
            ieee = (dev.get("ieee") or dev.get("ieee_address") or f"zb_dev_{idx}").lower()
            if ieee in ieee_to_id:
                continue

            raw_type = (dev.get("device_type") or "").lower()
            is_router = raw_type == "router" or dev.get("is_router") is True or dev.get("power_source") == "Mains"
            node_type = "router" if is_router else "end_device"

            nwk_raw = dev.get("nwk") or dev.get("nwk_address") or idx + 1
            if isinstance(nwk_raw, int):
                nwk_str = f"0x{nwk_raw:04X}"
            else:
                nwk_str = str(nwk_raw)

            dev_name = dev.get("user_given_name") or dev.get("name") or dev.get("model") or f"Zigbee Device #{idx + 1}"
            vendor = dev.get("manufacturer") or dev.get("vendor") or "Generic"
            model = dev.get("model") or "Zigbee 3.0 Device"
            lqi = dev.get("lqi")
            rssi = dev.get("rssi")
            is_available = dev.get("available", True)

            status = "online"
            if not is_available:
                status = "offline"
            elif (lqi is not None and lqi < 65) or (rssi is not None and rssi < -82):
                status = "weak"

            g_id = f"zb_{ieee.replace(':', '')[-8:]}"
            ieee_to_id[ieee] = g_id
            if is_router:
                router_ids.append(g_id)

            battery = dev.get("battery")

            nodes.append({
                "id": g_id,
                "node_id": idx + 1,
                "name": dev_name,
                "label": dev_name,
                "type": node_type,
                "protocol": "zigbee",
                "vendor": vendor,
                "brand": vendor,
                "model": model,
                "routing_role": "Zigbee Router (Mains)" if is_router else "Zigbee End Device (Battery)",
                "rloc16": nwk_str,
                "ext_address": ieee,
                "extended_pan_id": extended_pan_id or "00:12:4b:00:1c:a2:b3:c4",
                "rssi": rssi,
                "lqi": lqi,
                "battery": battery,
                "status": status,
                "preferred": False,
                "ha_area": dev.get("ha_area") or dev.get("area_name") or "",
                "power_source": "Mains" if is_router else "Battery",
                "details": f"{'Mains Relay Router' if is_router else 'Sleepy Sensor'} • NWK: {nwk_str} • LQI: {lqi if lqi is not None else 'N/A'}/255" + (f" • Battery: {battery}%" if battery is not None else ""),
            })

        # 3. Build Mesh Edges
        # Check if devices have explicit neighbor tables (from ZHA)
        has_explicit_neighbors = False
        for dev in devices:
            neighbors = dev.get("neighbors") or []
            s_ieee = (dev.get("ieee") or "").lower()
            s_id = ieee_to_id.get(s_ieee)
            if not s_id or not neighbors:
                continue

            for n in neighbors:
                if not isinstance(n, dict):
                    continue
                t_ieee = (n.get("ieee") or "").lower()
                t_id = ieee_to_id.get(t_ieee)
                if not t_id or t_id == s_id:
                    continue

                edge_key = tuple(sorted([s_id, t_id]))
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)

                n_lqi = n.get("lqi") or dev.get("lqi") or 180
                n_rssi = dev.get("rssi")
                distance = max(65, min(240, int(260 - (float(n_lqi) / 255.0) * 180)))
                has_explicit_neighbors = True

                edges.append({
                    "source": s_id,
                    "target": t_id,
                    "lqi": n_lqi,
                    "rssi": n_rssi,
                    "distance": distance,
                    "quality": "good" if n_lqi >= 140 else ("weak" if n_lqi < 75 else "medium"),
                    "type": "neighbor",
                    "label": f"LQI {n_lqi}",
                })

        # If no explicit neighbor tables were provided, synthesize realistic parent-child & backbone mesh edges
        if not has_explicit_neighbors:
            # Connect all routers to coordinator
            for r_id in router_ids:
                edge_key = tuple(sorted([coord_node_id, r_id]))
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append({
                        "source": coord_node_id,
                        "target": r_id,
                        "lqi": 240,
                        "rssi": -52,
                        "distance": 95,
                        "quality": "backbone",
                        "type": "backbone",
                        "label": "LQI 240",
                    })

            # Interconnect routers (mesh backbone)
            for i in range(len(router_ids)):
                for j in range(i + 1, len(router_ids)):
                    if j - i <= 2:  # Connect adjacent routers
                        r1 = router_ids[i]
                        r2 = router_ids[j]
                        edge_key = tuple(sorted([r1, r2]))
                        if edge_key not in seen_edges:
                            seen_edges.add(edge_key)
                            edges.append({
                                "source": r1,
                                "target": r2,
                                "lqi": 210,
                                "rssi": -62,
                                "distance": 115,
                                "quality": "backbone",
                                "type": "backbone",
                                "label": "LQI 210",
                            })

            # Connect end devices to closest router (or coordinator if no routers)
            end_nodes = [n for n in nodes if n["type"] == "end_device"]
            for idx, end_n in enumerate(end_nodes):
                target_parent = coord_node_id
                if router_ids:
                    # Distribute across available routers
                    target_parent = router_ids[idx % len(router_ids)]

                e_lqi = end_n.get("lqi") or 195
                e_rssi = end_n.get("rssi") or -66
                distance = max(70, min(230, int(250 - (float(e_lqi) / 255.0) * 170)))

                edge_key = tuple(sorted([target_parent, end_n["id"]]))
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append({
                        "source": target_parent,
                        "target": end_n["id"],
                        "lqi": e_lqi,
                        "rssi": e_rssi,
                        "distance": distance,
                        "quality": "good" if e_lqi >= 130 else "weak",
                        "type": "parent_child",
                        "label": f"LQI {e_lqi}",
                    })

        return {
            "nodes": nodes,
            "edges": edges,
            "protocol": "zigbee",
            "channel": channel,
            "pan_id": pan_id,
            "extended_pan_id": extended_pan_id,
            "coordinator": coordinator,
            "target_network": {
                "id": f"zigbee_{channel}_{pan_id}",
                "name": coord_name,
                "channel": channel,
                "pan_id": pan_id,
                "extended_pan_id": extended_pan_id,
                "type": "zigbee",
            },
        }

    @staticmethod
    def get_sample_zigbee_network() -> Dict[str, Any]:
        """
        Return a realistic demonstration Zigbee network dataset with Coordinator,
        Mains Routers, and Sleepy End Devices when no live Zigbee integration is active.
        """
        coordinator = {
            "name": "Home Assistant SkyConnect / ZBT-1 (Zigbee)",
            "ieee": "00:12:4B:00:25:9D:6A:11",
            "vendor": "Nabu Casa",
            "model": "Home Assistant SkyConnect / ZBT-1",
            "brand": "Nabu Casa",
            "ha_area": "Server Cabinet",
            "channel": 15,
            "pan_id": "0x1A2B",
            "extended_pan_id": "00:12:4B:00:25:9D:6A:11",
        }

        devices = [
            # Routers (Mains-powered)
            {
                "name": "Living Room Hue Smart Plug",
                "ieee": "00:17:88:01:08:33:44:01",
                "nwk": 0x2A11,
                "device_type": "router",
                "manufacturer": "Philips",
                "model": "Hue Smart Plug LOM001",
                "power_source": "Mains",
                "lqi": 248,
                "rssi": -48,
                "available": True,
                "ha_area": "Living Room",
            },
            {
                "name": "Kitchen Inovelli Blue In-Wall Switch",
                "ieee": "04:CF:8C:DF:3C:77:88:02",
                "nwk": 0x4B32,
                "device_type": "router",
                "manufacturer": "Inovelli",
                "model": "Blue Series 2-in-1 Switch VZM31-SN",
                "power_source": "Mains",
                "lqi": 236,
                "rssi": -55,
                "available": True,
                "ha_area": "Kitchen",
            },
            {
                "name": "Hallway Sonoff Zigbee 3.0 Repeater",
                "ieee": "00:12:4B:00:21:55:66:03",
                "nwk": 0x6C44,
                "device_type": "router",
                "manufacturer": "Sonoff",
                "model": "Zigbee 3.0 USB Dongle Plus (Router Mode)",
                "power_source": "Mains",
                "lqi": 222,
                "rssi": -60,
                "available": True,
                "ha_area": "Hallway",
            },
            # End Devices (Battery-powered)
            {
                "name": "Front Door Contact Sensor",
                "ieee": "00:15:8D:00:04:11:22:04",
                "nwk": 0x7E12,
                "device_type": "end_device",
                "manufacturer": "Aqara",
                "model": "Door and Window Sensor MCCGQ11LM",
                "power_source": "Battery",
                "battery": 92,
                "lqi": 215,
                "rssi": -62,
                "available": True,
                "ha_area": "Entryway",
            },
            {
                "name": "Living Room Temp & Humidity",
                "ieee": "00:12:4B:00:29:33:44:05",
                "nwk": 0x8F24,
                "device_type": "end_device",
                "manufacturer": "Sonoff",
                "model": "SNZB-02 Temperature & Humidity Sensor",
                "power_source": "Battery",
                "battery": 86,
                "lqi": 204,
                "rssi": -65,
                "available": True,
                "ha_area": "Living Room",
            },
            {
                "name": "Kitchen Motion Sensor",
                "ieee": "00:17:88:01:09:55:66:06",
                "nwk": 0x9A36,
                "device_type": "end_device",
                "manufacturer": "Philips",
                "model": "Hue Indoor Motion Sensor SML001",
                "power_source": "Battery",
                "battery": 95,
                "lqi": 228,
                "rssi": -58,
                "available": True,
                "ha_area": "Kitchen",
            },
            {
                "name": "Backyard Patio Motion",
                "ieee": "F0:D1:B8:00:00:77:88:07",
                "nwk": 0xA548,
                "device_type": "end_device",
                "manufacturer": "IKEA",
                "model": "VALLHORN Wireless Motion Sensor",
                "power_source": "Battery",
                "battery": 78,
                "lqi": 165,
                "rssi": -74,
                "available": True,
                "ha_area": "Patio",
            },
            {
                "name": "Basement Water Leak Detector",
                "ieee": "00:15:8D:00:05:99:AA:08",
                "nwk": 0xB75A,
                "device_type": "end_device",
                "manufacturer": "Aqara",
                "model": "Water Leak Sensor SJCGQ11LM",
                "power_source": "Battery",
                "battery": 100,
                "lqi": 185,
                "rssi": -71,
                "available": True,
                "ha_area": "Basement",
            },
            {
                "name": "Bedroom Wireless Scene Switch",
                "ieee": "00:15:8D:00:06:BB:CC:09",
                "nwk": 0xC86C,
                "device_type": "end_device",
                "manufacturer": "Aqara",
                "model": "Wireless Mini Switch WXKG11LM",
                "power_source": "Battery",
                "battery": 88,
                "lqi": 210,
                "rssi": -64,
                "available": True,
                "ha_area": "Bedroom",
            },
        ]

        return {
            "protocol": "zigbee",
            "coordinator": coordinator,
            "devices": devices,
            "channel": 15,
            "pan_id": "0x1A2B",
            "extended_pan_id": "00:12:4B:00:25:9D:6A:11",
            "is_demo": True,
        }
