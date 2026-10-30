"""
Thread Mesh and RF Coexistence Analyzer.
Evaluates Thread topology, Border Router synchronization, RF interference,
and routing health according to Thread 1.3/1.4 specifications.
Supports Google Nest Wifi Pro, Apple TV/HomePod, Amazon eero, and HA SkyConnect.
"""
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("matter_thread_ai.thread_analyzer")

# 2.4 GHz Wi-Fi to Thread Channel overlap matrix
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
    26: {"wifi_channel": None, "severity": "MINIMAL", "interference": "Clear of all standard Wi-Fi (Note: reduced Tx power on some hardware)"},
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
    def identify_router_device(raw: Dict[str, Any]) -> Dict[str, str]:
        """Classify and normalize Border Router identity from HA discovery or device registry."""
        model_name = str(raw.get("model_name") or raw.get("model") or "").strip()
        brand_name = str(raw.get("brand_name") or raw.get("manufacturer") or raw.get("vendor") or "").strip()
        server = str(raw.get("server") or raw.get("name") or raw.get("id") or "").strip()

        combined = f"{brand_name} {model_name} {server}".lower()

        # Google Nest Wifi Pro / Nest Hub
        if "wifi pro" in combined or "nest wifi" in combined:
            return {"brand": "Google", "model": "Nest Wifi Pro", "label": "Google Nest Wifi Pro", "type": "nest"}
        elif "nest hub" in combined or "google home hub" in combined:
            return {"brand": "Google", "model": "Nest Hub", "label": "Google Nest Hub (2nd Gen)", "type": "nest"}
        elif "google" in combined and "router" in combined:
            return {"brand": "Google", "model": model_name or "Google Thread Router", "label": "Google Nest Border Router", "type": "nest"}

        # Apple TV / HomePod
        elif "homepod" in combined:
            return {"brand": "Apple", "model": "HomePod", "label": "Apple HomePod (Thread TBR)", "type": "apple"}
        elif "apple tv" in combined or "appletv" in combined:
            return {"brand": "Apple", "model": "Apple TV 4K", "label": "Apple TV 4K (Thread TBR)", "type": "apple"}
        elif "apple" in combined:
            return {"brand": "Apple", "model": model_name or "Apple Border Router", "label": "Apple Thread Border Router", "type": "apple"}

        # Amazon eero
        elif "eero" in combined:
            return {"brand": "Amazon / eero", "model": model_name or "eero Router", "label": "eero Thread Border Router", "type": "eero"}

        # Home Assistant SkyConnect / Connect ZBT-1 / Yellow / OTBR
        elif "skyconnect" in combined or "zbt-1" in combined or "connect" in combined or "yellow" in combined or "otbr" in combined:
            return {"brand": "Nabu Casa", "model": model_name or "SkyConnect / ZBT-1", "label": "HA Green (SkyConnect / ZBT-1)", "type": "ha"}

        # Generic or Fallback
        label = model_name or server or "Thread Border Router"
        return {"brand": brand_name or "Generic", "model": model_name or "TBR", "label": label, "type": "generic"}

    @classmethod
    def detect_split_networks(cls, border_routers: List[Dict[str, Any]],
                               active_datasets: List[Dict[str, Any]],
                               device_registry: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Detect if multiple Thread Border Routers (Nest Wifi Pro, Apple TV, SkyConnect)
        are operating on separate/split Thread networks instead of forming a single mesh.
        """
        networks: Dict[str, List[Dict[str, Any]]] = {}
        all_discovered_routers: List[Dict[str, Any]] = []
        found_nest_wifi_pro = False
        found_ha_router = False

        # 1. Inspect live routers discovered over network (mDNS / HA Thread discovery)
        for router in border_routers:
            info = cls.identify_router_device(router)
            if info["type"] == "nest":
                found_nest_wifi_pro = True
            elif info["type"] == "ha":
                found_ha_router = True

            ext_pan_id = (router.get("extended_pan_id") or router.get("ext_pan_id") or "UNKNOWN").upper().replace(":", "").replace("0X", "")
            net_name = router.get("network_name") or router.get("name") or info["label"]
            
            entry = {
                "name": info["label"],
                "model": info["model"],
                "brand": info["brand"],
                "type": info["type"],
                "server": router.get("server") or router.get("id"),
                "network_name": net_name,
                "extended_pan_id": ext_pan_id,
                "channel": router.get("channel"),
                "pan_id": router.get("pan_id"),
                "border_agent_id": router.get("border_agent_id") or router.get("extended_address"),
                "addresses": router.get("addresses", []),
            }
            all_discovered_routers.append(entry)
            networks.setdefault(ext_pan_id, []).append(entry)

        # 2. Inspect HA device registry for registered Nest Wifi Pro, Apple TV/HomePod, or eero Thread hardware
        if device_registry:
            for d in device_registry:
                model_str = f"{d.get('manufacturer', '')} {d.get('model', '')} {d.get('name', '')}".lower()
                
                # Google Nest Wifi Pro / Nest Hub
                if "wifi pro" in model_str or ("nest" in model_str and ("router" in model_str or "point" in model_str or "hub" in model_str)):
                    found_nest_wifi_pro = True
                    name = d.get("name") or "Google Nest Wifi Pro"
                    if not any(r["name"] == name or "nest wifi" in r["name"].lower() for r in all_discovered_routers):
                        entry = {
                            "name": name,
                            "model": d.get("model") or "Nest Wifi Pro",
                            "brand": "Google",
                            "type": "nest",
                            "server": d.get("id"),
                            "network_name": "Google Nest Thread Mesh",
                            "extended_pan_id": "GOOGLE_THREAD_MESH",
                            "channel": None,
                            "pan_id": None,
                            "border_agent_id": None,
                            "source": "Home Assistant Device Registry",
                        }
                        all_discovered_routers.append(entry)
                        networks.setdefault("GOOGLE_THREAD_MESH", []).append(entry)

                # Apple TV 4K / HomePod / HomePod mini
                elif "apple tv" in model_str or "homepod" in model_str or ("apple" in model_str and ("tv" in model_str or "audio" in model_str or "speaker" in model_str)):
                    name = d.get("name") or ("Apple HomePod" if "homepod" in model_str else "Apple TV 4K")
                    if not any(r["name"] == name or "apple" in r["name"].lower() or "homepod" in r["name"].lower() for r in all_discovered_routers):
                        entry = {
                            "name": name,
                            "model": d.get("model") or ("HomePod mini" if "homepod" in model_str else "Apple TV 4K"),
                            "brand": "Apple",
                            "type": "apple",
                            "server": d.get("id"),
                            "network_name": "Apple Thread Mesh",
                            "extended_pan_id": "APPLE_THREAD_MESH",
                            "channel": None,
                            "pan_id": None,
                            "border_agent_id": None,
                            "source": "Home Assistant Device Registry",
                        }
                        all_discovered_routers.append(entry)
                        networks.setdefault("APPLE_THREAD_MESH", []).append(entry)


        # 3. Inspect active datasets in Home Assistant
        for ds in active_datasets:
            ext_pan_id = (ds.get("extended_pan_id") or "HA_DATASET").upper().replace(":", "").replace("0X", "")
            net_name = ds.get("network_name", "Home Assistant Thread Network")
            is_pref = ds.get("preferred", False)
            source = ds.get("source", "HA Dataset Store")

            dataset_entry = {
                "name": f"Home Assistant Active Mesh ({net_name})",
                "model": "Thread Dataset",
                "brand": "Home Assistant",
                "type": "ha",
                "server": ds.get("dataset_id", "ha_dataset"),
                "network_name": net_name,
                "extended_pan_id": ext_pan_id,
                "channel": ds.get("channel"),
                "pan_id": ds.get("pan_id"),
                "preferred": is_pref,
                "source": source
            }
            if ext_pan_id not in networks:
                networks[ext_pan_id] = []
            networks[ext_pan_id].append(dataset_entry)

        valid_network_keys = [k for k in networks.keys() if k not in ("UNKNOWN", "DATASET_UNKNOWN")]
        num_distinct_networks = len(valid_network_keys)
        is_split = num_distinct_networks > 1

        # Build custom summary and step-by-step guidance
        if is_split:
            if found_nest_wifi_pro:
                summary = (
                    f"CRITICAL SPLIT THREAD MESH: Found {num_distinct_networks} independent Thread networks! "
                    "Your Google Nest Wifi Pro border router(s) and Home Assistant are operating on separate Extended PAN IDs. "
                    "Matter devices paired via Google Home are isolated on Nest's Thread mesh and cannot be controlled reliably by Home Assistant."
                )
                recommendation = (
                    "To unify your Google Nest Wifi Pro with Home Assistant:\n"
                    "1. Open the Home Assistant Companion App on your mobile phone (must be signed in to the same Google account as Google Home).\n"
                    "2. Navigate to Settings -> Companion App -> Troubleshooting -> Sync Thread Credentials.\n"
                    "3. In Home Assistant web UI, go to Settings -> Devices & Services -> Thread.\n"
                    "4. Select the Google Nest network and click 'Make Preferred Network'.\n"
                    "5. Your Nest Wifi Pro and Home Assistant Green will now form one unified Thread 1.3 mesh."
                )
            else:
                summary = (
                    f"CRITICAL SPLIT MESH: Found {num_distinct_networks} independent Thread networks with different Extended PAN IDs! "
                    "Border Routers have not synchronized Thread network credentials."
                )
                recommendation = (
                    "Synchronize your Thread datasets in Home Assistant Settings -> Devices & Services -> Thread -> "
                    "Choose your preferred network and sync credentials so all Border Routers share the same Extended PAN ID and Network Key."
                )
        else:
            if found_nest_wifi_pro:
                summary = "Google Nest Wifi Pro detected and synchronized with your Thread mesh."
                recommendation = "Thread Border Router synchronization is healthy."
            else:
                summary = "Thread Border Routers appear synchronized on a single Extended PAN ID."
                recommendation = "Thread mesh synchronization is healthy."

        return {
            "is_split_network": is_split,
            "distinct_network_count": max(num_distinct_networks, 1),
            "networks": networks,
            "all_discovered_routers": all_discovered_routers,
            "found_nest_wifi_pro": found_nest_wifi_pro,
            "found_ha_router": found_ha_router,
            "summary": summary,
            "recommendation": recommendation
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
            rssi = node.get("rssi")
            lqi = node.get("lqi")

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
            "summary": f"{len(healthy_nodes)}/{total} nodes operational. {len(offline_nodes)} offline, {len(weak_nodes)} weak."
        }
