"""
Thread Mesh and RF Coexistence Analyzer.
Evaluates Thread topology, Border Router synchronization, RF interference,
and routing health according to Thread 1.3/1.4 specifications.
"""
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("matter_thread_ai.thread_analyzer")

# 2.4 GHz Wi-Fi to Thread Channel overlap matrix
# Thread channels 11-26 (2.4 GHz IEEE 802.15.4) vs Wi-Fi 20MHz Channels 1, 6, 11
THREAD_WIFI_OVERLAP_MAP = {
    11: {"wifi_channel": 1, "severity": "HIGH", "interference": "Wi-Fi Ch 1 direct overlap"},
    12: {"wifi_channel": 1, "severity": "HIGH", "interference": "Wi-Fi Ch 1 direct overlap"},
    13: {"wifi_channel": 1, "severity": "HIGH", "interference": "Wi-Fi Ch 1 direct overlap"},
    14: {"wifi_channel": 1, "severity": "MEDIUM", "interference": "Wi-Fi Ch 1 spectral edge"},
    15: {"wifi_channel": None, "severity": "LOW", "interference": "Between Wi-Fi Ch 1 and Ch 6 guard band"},
    16: {"wifi_channel": 6, "severity": "MEDIUM", "interference": "Wi-Fi Ch 6 spectral edge"},
    17: {"wifi_channel": 6, "severity": "HIGH", "interference": "Wi-Fi Ch 6 direct overlap"},
    18: {"wifi_channel": 6, "severity": "HIGH", "interference": "Wi-Fi Ch 6 direct overlap"},
    19: {"wifi_channel": 6, "severity": "HIGH", "interference": "Wi-Fi Ch 6 direct overlap"},
    20: {"wifi_channel": None, "severity": "LOW", "interference": "Between Wi-Fi Ch 6 and Ch 11 guard band"},
    21: {"wifi_channel": 11, "severity": "MEDIUM", "interference": "Wi-Fi Ch 11 spectral edge"},
    22: {"wifi_channel": 11, "severity": "HIGH", "interference": "Wi-Fi Ch 11 direct overlap"},
    23: {"wifi_channel": 11, "severity": "HIGH", "interference": "Wi-Fi Ch 11 direct overlap"},
    24: {"wifi_channel": 11, "severity": "HIGH", "interference": "Wi-Fi Ch 11 direct overlap"},
    25: {"wifi_channel": None, "severity": "MINIMAL", "interference": "Clear from Wi-Fi Ch 11 (Recommended Thread channel)"},
    26: {"wifi_channel": None, "severity": "MINIMAL", "interference": "Clear of all standard Wi-Fi (Note: some devices have reduced Tx power on 26 due to FCC edges)"},
}


class ThreadAnalyzer:
    """Performs deterministic heuristic analysis of Thread datasets and node topologies."""

    @staticmethod
    def analyze_rf_coexistence(thread_channel: Optional[int], detected_wifi_channels: Optional[List[int]] = None) -> Dict[str, Any]:
        """Check RF interference between Thread and 2.4 GHz Wi-Fi."""
        if not thread_channel:
            return {
                "channel": None,
                "status": "UNKNOWN",
                "summary": "Thread channel not configured or undetected",
                "recommendation": "Configure Thread on Channel 25 for optimal coexistence with Wi-Fi."
            }

        overlap_info = THREAD_WIFI_OVERLAP_MAP.get(thread_channel, {
            "wifi_channel": None,
            "severity": "UNKNOWN",
            "interference": "Non-standard 802.15.4 channel"
        })

        conflicts = []
        if detected_wifi_channels:
            for wch in detected_wifi_channels:
                if overlap_info["wifi_channel"] == wch:
                    conflicts.append(wch)

        is_high_risk = overlap_info["severity"] == "HIGH"
        return {
            "thread_channel": thread_channel,
            "severity": overlap_info["severity"],
            "overlapping_wifi_channel": overlap_info["wifi_channel"],
            "interference_description": overlap_info["interference"],
            "detected_conflicts": conflicts,
            "recommendation": (
                f"Thread Channel {thread_channel} has {overlap_info['severity']} overlap with Wi-Fi Channel {overlap_info['wifi_channel']}. "
                f"Consider migrating Thread to Channel 25 (or ensure your 2.4GHz Wi-Fi is strictly locked to Channel 1 or 6 without overlapping 40MHz channel width)."
                if is_high_risk else
                f"Thread Channel {thread_channel} has minimal Wi-Fi interference ({overlap_info['interference']})."
            )
        }

    @staticmethod
    def detect_split_networks(border_routers: List[Dict[str, Any]], active_datasets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detect if multiple Thread Border Routers (Apple TV, HomePod, Google Nest, SkyConnect)
        are operating on separate/split Thread networks instead of forming a single mesh.
        """
        networks: Dict[str, List[Dict[str, Any]]] = {}

        for router in border_routers:
            ext_pan_id = router.get("extended_pan_id") or router.get("ext_pan_id") or "UNKNOWN"
            net_name = router.get("network_name") or router.get("name") or "Unnamed"
            entry = {
                "name": net_name,
                "router_id": router.get("id") or router.get("address"),
                "model": router.get("model") or router.get("vendor", "Generic TBR"),
                "channel": router.get("channel"),
                "pan_id": router.get("pan_id"),
            }
            networks.setdefault(ext_pan_id, []).append(entry)

        # Also inspect datasets
        for ds in active_datasets:
            ext_pan_id = ds.get("extended_pan_id") or "DATASET_UNKNOWN"
            if ext_pan_id not in networks:
                networks[ext_pan_id] = []
            networks[ext_pan_id].append({
                "name": ds.get("network_name", "Dataset Network"),
                "router_id": "Home Assistant Active Dataset",
                "channel": ds.get("channel"),
                "pan_id": ds.get("pan_id")
            })

        num_distinct_networks = len([k for k in networks.keys() if k != "UNKNOWN"])
        is_split = num_distinct_networks > 1

        return {
            "is_split_network": is_split,
            "distinct_network_count": num_distinct_networks,
            "networks": networks,
            "summary": (
                f"CRITICAL: Found {num_distinct_networks} independent Thread networks with different Extended PAN IDs! "
                "Devices commissioned via Apple Home or Google Home cannot route to Home Assistant without credential synchronization."
                if is_split else
                "Thread Border Routers appear synchronized on a single Extended PAN ID."
            ),
            "recommendation": (
                "Synchronize your Thread datasets in Home Assistant Settings -> Devices & Services -> Thread -> "
                "Choose preferred network and import/export credentials so Apple/Google and HA share the exact same Extended PAN ID and Network Key."
                if is_split else "Thread mesh synchronization is healthy."
            )
        }

    @staticmethod
    def evaluate_node_link_quality(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze Matter-over-Thread nodes for link degradation and sleepy device issues."""
        weak_nodes = []
        offline_nodes = []
        healthy_nodes = []

        for node in nodes:
            node_id = node.get("node_id")
            is_avail = node.get("available", False)
            rssi = node.get("rssi")  # dBm if available
            lqi = node.get("lqi")    # 0 to 3 or 0 to 255

            if not is_avail:
                offline_nodes.append({
                    "node_id": node_id,
                    "name": node.get("product_name"),
                    "vendor": node.get("vendor_name"),
                    "reason": "Unreachable / Ping Timeout"
                })
            elif rssi is not None and rssi < -82:
                weak_nodes.append({
                    "node_id": node_id,
                    "name": node.get("product_name"),
                    "vendor": node.get("vendor_name"),
                    "rssi": rssi,
                    "lqi": lqi,
                    "reason": f"Severe RF attenuation ({rssi} dBm < -82 dBm)"
                })
            else:
                healthy_nodes.append(node_id)

        health_percentage = 100
        total = len(nodes)
        if total > 0:
            health_percentage = int(((total - len(offline_nodes) - (len(weak_nodes) * 0.5)) / total) * 100)
            health_percentage = max(0, min(100, health_percentage))

        return {
            "total_nodes": total,
            "healthy_count": len(healthy_nodes),
            "weak_count": len(weak_nodes),
            "offline_count": len(offline_nodes),
            "health_score": health_percentage,
            "weak_nodes": weak_nodes,
            "offline_nodes": offline_nodes,
            "summary": f"{len(healthy_nodes)}/{total} nodes fully operational. {len(offline_nodes)} offline, {len(weak_nodes)} weak."
        }
