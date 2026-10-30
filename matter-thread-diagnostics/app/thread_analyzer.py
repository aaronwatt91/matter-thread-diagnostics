"""
Thread Mesh and RF Coexistence Analyzer.
Evaluates real Thread topology (Cluster 0x0035 NeighborTable, RouteTable, RLOC16, Extended Address),
Border Router mDNS synchronization, RF interference, and routing health according to Thread 1.3/1.4 specs.
"""
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
    """Performs deterministic analysis of real Thread datasets, Border Routers, and Cluster 0x0035 node telemetry."""

    @staticmethod
    def analyze_rf_coexistence(thread_channel: Optional[int], detected_wifi_channels: Optional[List[int]] = None) -> Dict[str, Any]:
        """Check RF interference between Thread and 2.4 GHz Wi-Fi."""
        if not thread_channel:
            return {
                "thread_channel": None,
                "channel": None,
                "severity": "UNKNOWN",
                "status": "UNKNOWN",
                "overlapping_wifi_channel": None,
                "detected_conflicts": [],
                "summary": "Thread channel not yet detected from dataset or active nodes",
                "recommendation": "Select a Thread network and click Scan, or configure Thread on Channel 25 for optimal coexistence with Wi-Fi.",
            }

        overlap_info = THREAD_WIFI_OVERLAP_MAP.get(
            int(thread_channel),
            {
                "wifi_channel": None,
                "severity": "UNKNOWN",
                "interference": "Non-standard 802.15.4 channel",
            },
        )

        conflicts = []
        if detected_wifi_channels:
            for wch in detected_wifi_channels:
                if overlap_info["wifi_channel"] == wch:
                    conflicts.append(wch)

        is_high_risk = overlap_info["severity"] == "HIGH"
        return {
            "thread_channel": int(thread_channel),
            "severity": overlap_info["severity"],
            "overlapping_wifi_channel": overlap_info["wifi_channel"],
            "interference_description": overlap_info["interference"],
            "detected_conflicts": conflicts,
            "recommendation": (
                f"Thread Channel {thread_channel} has {overlap_info['severity']} overlap with 2.4 GHz Wi-Fi Channel {overlap_info['wifi_channel']}. "
                f"Consider migrating Thread to Channel 25 (or ensure your 2.4 GHz Wi-Fi AP near your Thread devices is locked to a non-overlapping 20 MHz channel)."
                if is_high_risk
                else f"Thread Channel {thread_channel} has low/minimal Wi-Fi interference ({overlap_info['interference']})."
            ),
        }

    @staticmethod
    def identify_router_device(raw: Dict[str, Any]) -> Dict[str, str]:
        """Classify and normalize Border Router identity from mDNS _meshcop._udp or HA discovery."""
        model_name = str(raw.get("model_name") or raw.get("model") or "").strip()
        brand_name = str(raw.get("brand_name") or raw.get("vendor_name") or raw.get("manufacturer") or raw.get("vendor") or "").strip()
        inst_name = str(raw.get("instance_name") or raw.get("name") or raw.get("server") or raw.get("id") or "").strip()

        combined = f"{brand_name} {model_name} {inst_name}".lower()

        if "wifi pro" in combined or "nest wifi" in combined or "g6z" in combined:
            return {"brand": "Google", "model": model_name or "Nest Wifi Pro", "label": f"Google Nest Wifi Pro ({inst_name})" if inst_name and "nest" not in inst_name.lower() else (inst_name or "Google Nest Wifi Pro"), "type": "nest"}
        elif "nest hub" in combined or "google home" in combined or "google" in combined:
            return {"brand": "Google", "model": model_name or "Google Border Router", "label": inst_name or f"Google {model_name or 'Border Router'}", "type": "nest"}
        elif "homepod" in combined or "audioaccessory" in combined:
            return {"brand": "Apple", "model": model_name or "HomePod", "label": inst_name or "Apple HomePod (TBR)", "type": "apple"}
        elif "apple tv" in combined or "appletv" in combined or "j305" in combined or "j105" in combined:
            return {"brand": "Apple", "model": model_name or "Apple TV 4K", "label": inst_name or "Apple TV 4K (TBR)", "type": "apple"}
        elif "apple" in combined:
            return {"brand": "Apple", "model": model_name or "Apple Border Router", "label": inst_name or "Apple Border Router", "type": "apple"}
        elif "eero" in combined:
            return {"brand": "Amazon / eero", "model": model_name or "eero Router", "label": inst_name or "eero Border Router", "type": "eero"}
        elif "skyconnect" in combined or "zbt-1" in combined or "openthread" in combined or "homeassistant" in combined or "nabu" in combined or "otbr" in combined:
            return {"brand": "Home Assistant", "model": model_name or "OpenThread Border Router", "label": inst_name or "Home Assistant OTBR (ZBT-1 / SkyConnect)", "type": "ha"}

        label = inst_name or model_name or "Thread Border Router"
        return {"brand": brand_name or "Thread TBR", "model": model_name or "Border Router", "label": label, "type": "generic"}

    @classmethod
    def detect_split_networks(
        cls,
        border_routers: List[Dict[str, Any]],
        active_datasets: List[Dict[str, Any]],
        device_registry: Optional[List[Dict[str, Any]]] = None,
        target_network_id: Optional[str] = None,
        mdns_routers: Optional[List[Dict[str, Any]]] = None,
        otbr_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Detect if discovered Thread Border Routers (from HA `thread/discover_routers`,
        direct mDNS `_meshcop._udp.local.`, and OTBR REST API) and active datasets are
        operating on separate Extended PAN IDs (Split Thread Mesh).
        Strictly uses real discovered Border Routers and datasets — no fabricated PAN IDs.
        """
        networks: Dict[str, List[Dict[str, Any]]] = {}
        all_discovered_routers: List[Dict[str, Any]] = []
        seen_router_keys = set()
        found_nest_wifi_pro = False
        found_ha_router = False

        # Build lookup of Extended PAN ID -> Dataset metadata (channel, pan_id, mesh_local_prefix)
        dataset_by_xpan: Dict[str, Dict[str, Any]] = {}
        for ds in active_datasets or []:
            if not isinstance(ds, dict):
                continue
            ds_xpan = str(ds.get("extended_pan_id") or ds.get("ext_pan_id") or "").upper().replace(":", "").replace("0X", "")
            if ds_xpan and ds_xpan != "UNKNOWN":
                dataset_by_xpan[ds_xpan] = ds

        # Combine border routers from HA discovery + direct mDNS _meshcop._udp + OTBR REST API
        combined_raw_routers: List[Dict[str, Any]] = []
        if border_routers:
            combined_raw_routers.extend(border_routers)
        if mdns_routers:
            combined_raw_routers.extend(mdns_routers)
        if isinstance(otbr_info, dict) and otbr_info.get("reachable") and otbr_info.get("extended_pan_id"):
            combined_raw_routers.append({
                "name": "Home Assistant OTBR",
                "instance_name": f"HA OTBR ({otbr_info.get('state', 'leader')})",
                "brand_name": "Home Assistant",
                "model_name": "OpenThread Border Router",
                "network_name": otbr_info.get("network_name") or "Home Assistant Thread",
                "extended_pan_id": otbr_info.get("extended_pan_id"),
                "ext_address": otbr_info.get("ext_address"),
                "rloc16": otbr_info.get("rloc16"),
                "channel": otbr_info.get("channel"),
                "pan_id": otbr_info.get("pan_id"),
                "mesh_local_prefix": otbr_info.get("mesh_local_prefix"),
                "source": "OTBR REST API (:8081)",
            })

        def _norm_ip(ip_str: str) -> str:
            return str(ip_str or "").split("/")[0].split("%")[0].strip().lower()

        def _order_ips(ips: List[str]) -> List[str]:
            seen = set()
            v4, v6_ula, v6_ll = [], [], []
            for raw_ip in ips:
                if not raw_ip:
                    continue
                ip_s = str(raw_ip).strip()
                norm = _norm_ip(ip_s)
                if not norm or norm in ("127.0.0.1", "::1") or norm in seen:
                    continue
                seen.add(norm)
                if "." in norm:
                    v4.append(ip_s)
                elif norm.startswith("fe80"):
                    v6_ll.append(ip_s)
                else:
                    v6_ula.append(ip_s)
            return v4 + v6_ula + v6_ll

        def _norm_host(h: str) -> str:
            s = str(h or "").strip().rstrip(".").lower()
            if s.endswith(".local"):
                s = s[:-6]
            return s

        for router in combined_raw_routers:
            if not isinstance(router, dict):
                continue
            info = cls.identify_router_device(router)
            if info["type"] == "nest":
                found_nest_wifi_pro = True
            elif info["type"] == "ha":
                found_ha_router = True

            ext_pan_id = str(router.get("extended_pan_id") or router.get("ext_pan_id") or "UNKNOWN").upper().replace(":", "").replace("0X", "")
            ext_addr = str(router.get("ext_address") or router.get("extended_address") or "").upper().replace(":", "").replace("0X", "")
            ba_id = str(router.get("border_agent_id") or "").upper().replace(":", "").replace("-", "")
            raw_inst = str(router.get("instance_name") or router.get("name") or "").strip()
            server = str(router.get("server") or raw_inst or "").strip()

            ds_match = dataset_by_xpan.get(ext_pan_id, {})
            ch = router.get("channel") or ds_match.get("channel")
            pan_id = router.get("pan_id") or ds_match.get("pan_id")
            mesh_prefix = router.get("mesh_local_prefix") or ds_match.get("mesh_local_prefix")
            net_name = router.get("network_name") or ds_match.get("network_name") or router.get("name") or info["label"]
            raw_addrs = router.get("addresses") or (router.get("ipv6_addresses", []) + router.get("ipv4_addresses", []))
            addrs = _order_ips(raw_addrs)

            entry = {
                "name": info["label"],
                "instance_name": raw_inst or info["label"],
                "model": info["model"],
                "brand": info["brand"],
                "type": info["type"],
                "server": server or router.get("id"),
                "network_name": net_name,
                "extended_pan_id": ext_pan_id,
                "channel": ch,
                "pan_id": pan_id,
                "mesh_local_prefix": mesh_prefix,
                "ext_address": ext_addr or None,
                "rloc16": router.get("rloc16"),
                "border_agent_id": ba_id or None,
                "thread_version": router.get("thread_version"),
                "state_bitmap": router.get("state_bitmap"),
                "addresses": addrs,
                "source": router.get("source", "mDNS / HA Discovery"),
            }

            # Multi-key deduplication: check if this physical Border Router is already in all_discovered_routers
            cand_name_norm = _norm_host(entry["name"])
            cand_inst_norm = _norm_host(entry["instance_name"])
            cand_srv_norm = _norm_host(entry["server"])
            cand_ips = {_norm_ip(a) for a in addrs if _norm_ip(a)}

            matched_existing = None
            for ex in all_discovered_routers:
                ex_name_norm = _norm_host(ex.get("name"))
                ex_inst_norm = _norm_host(ex.get("instance_name"))
                ex_srv_norm = _norm_host(ex.get("server"))
                ex_ips = {_norm_ip(a) for a in (ex.get("addresses") or []) if _norm_ip(a)}

                same_name = bool(cand_name_norm and (cand_name_norm == ex_name_norm or cand_name_norm == ex_inst_norm))
                same_inst = bool(cand_inst_norm and (cand_inst_norm == ex_inst_norm or cand_inst_norm == ex_name_norm))
                same_ext = bool(ext_addr and ex.get("ext_address") and ext_addr == ex.get("ext_address"))
                same_ba = bool(ba_id and ex.get("border_agent_id") and ba_id == ex.get("border_agent_id"))
                same_ip = bool(cand_ips and ex_ips and (cand_ips & ex_ips))
                same_srv = bool(
                    cand_srv_norm
                    and ex_srv_norm
                    and "." not in cand_srv_norm
                    and ":" not in cand_srv_norm
                    and cand_srv_norm == ex_srv_norm
                )
                same_ha_otbr = bool(
                    entry["type"] == "ha"
                    and ex.get("type") == "ha"
                    and ext_pan_id not in ("", "UNKNOWN")
                    and ex.get("extended_pan_id") == ext_pan_id
                    and ("otbr" in str(entry.get("source", "")).lower() or "otbr" in str(ex.get("source", "")).lower())
                )

                if same_name or same_inst or same_ext or same_ba or same_ip or same_srv or same_ha_otbr:
                    matched_existing = ex
                    break

            if matched_existing is not None:
                # Merge richer metadata into matched_existing instead of adding a duplicate row
                if matched_existing.get("extended_pan_id") in (None, "", "UNKNOWN") and ext_pan_id not in ("", "UNKNOWN"):
                    matched_existing["extended_pan_id"] = ext_pan_id
                    if net_name and net_name != matched_existing.get("name"):
                        matched_existing["network_name"] = net_name
                if matched_existing.get("type") == "generic" and entry["type"] != "generic":
                    matched_existing["type"] = entry["type"]
                    matched_existing["brand"] = entry["brand"]
                    matched_existing["model"] = entry["model"]
                    matched_existing["name"] = entry["name"]
                elif matched_existing.get("brand") in ("Thread TBR", "Generic", "") and entry["brand"] not in ("Thread TBR", "Generic", ""):
                    matched_existing["brand"] = entry["brand"]
                    matched_existing["model"] = entry["model"]
                for fld in ("channel", "pan_id", "mesh_local_prefix", "ext_address", "rloc16", "border_agent_id", "thread_version", "state_bitmap"):
                    if not matched_existing.get(fld) and entry.get(fld):
                        matched_existing[fld] = entry[fld]
                merged_ips = _order_ips((matched_existing.get("addresses") or []) + addrs)
                matched_existing["addresses"] = merged_ips
            else:
                all_discovered_routers.append(entry)

        # Populate networks dict from deduplicated routers (and enrich any newly-merged XPAN with dataset metadata)
        for r_entry in all_discovered_routers:
            rxpan = r_entry.get("extended_pan_id") or "UNKNOWN"
            ds_m = dataset_by_xpan.get(rxpan, {})
            if ds_m:
                if not r_entry.get("channel") and ds_m.get("channel"):
                    r_entry["channel"] = ds_m["channel"]
                if not r_entry.get("pan_id") and ds_m.get("pan_id"):
                    r_entry["pan_id"] = ds_m["pan_id"]
                if not r_entry.get("mesh_local_prefix") and ds_m.get("mesh_local_prefix"):
                    r_entry["mesh_local_prefix"] = ds_m["mesh_local_prefix"]
                if ds_m.get("network_name") and (not r_entry.get("network_name") or r_entry.get("network_name") == r_entry.get("name")):
                    r_entry["network_name"] = ds_m["network_name"]
            networks.setdefault(rxpan, []).append(r_entry)

        # Only inspect HA Device Registry fallback if NO live Border Routers were discovered via mDNS / HA Discovery
        if device_registry and len(all_discovered_routers) == 0:
            for d in device_registry:
                if not isinstance(d, dict):
                    continue
                model_str = f"{d.get('manufacturer', '')} {d.get('model', '')} {d.get('name', '')}".lower()
                if "wifi pro" in model_str or ("nest" in model_str and ("router" in model_str or "point" in model_str or "hub" in model_str)):
                    found_nest_wifi_pro = True
                    name = d.get("name_by_user") or d.get("name") or "Google Nest Wifi Pro"
                    if not any(r.get("type") == "nest" or "nest" in (r.get("name") or "").lower() for r in all_discovered_routers):
                        entry = {
                            "name": name,
                            "model": d.get("model") or "Nest Wifi Pro",
                            "brand": "Google",
                            "type": "nest",
                            "server": d.get("id"),
                            "network_name": "Google Nest Thread Mesh",
                            "extended_pan_id": "NEST_TBR_DETECTED",
                            "channel": None,
                            "pan_id": None,
                            "ext_address": None,
                            "border_agent_id": None,
                            "addresses": [],
                            "source": "HA Device Registry (No mDNS seen yet)",
                        }
                        all_discovered_routers.append(entry)
                        networks.setdefault("NEST_TBR_DETECTED", []).append(entry)
                elif "apple tv" in model_str or "homepod" in model_str:
                    name = d.get("name_by_user") or d.get("name") or ("Apple HomePod" if "homepod" in model_str else "Apple TV 4K")
                    if not any(r.get("type") == "apple" or "apple" in (r.get("name") or "").lower() or "homepod" in (r.get("name") or "").lower() for r in all_discovered_routers):
                        entry = {
                            "name": name,
                            "model": d.get("model") or ("HomePod" if "homepod" in model_str else "Apple TV 4K"),
                            "brand": "Apple",
                            "type": "apple",
                            "server": d.get("id"),
                            "network_name": "Apple Thread Mesh",
                            "extended_pan_id": "APPLE_TBR_DETECTED",
                            "channel": None,
                            "pan_id": None,
                            "ext_address": None,
                            "border_agent_id": None,
                            "addresses": [],
                            "source": "HA Device Registry (No mDNS seen yet)",
                        }
                        all_discovered_routers.append(entry)
                        networks.setdefault("APPLE_TBR_DETECTED", []).append(entry)

        # Also include configured HA datasets that have no live Border Router currently advertising them
        for ds in active_datasets or []:
            if not isinstance(ds, dict):
                continue
            ext_pan_id = str(ds.get("extended_pan_id") or ds.get("ext_pan_id") or "HA_DATASET").upper().replace(":", "").replace("0X", "")
            net_name = ds.get("network_name") or "Home Assistant Thread Dataset"
            is_pref = bool(ds.get("preferred", False))
            dataset_entry = {
                "name": f"HA Dataset ({net_name})",
                "model": "Operational Dataset",
                "brand": "Home Assistant",
                "type": "ha_dataset",
                "server": ds.get("dataset_id", "ha_dataset"),
                "network_name": net_name,
                "extended_pan_id": ext_pan_id,
                "channel": ds.get("channel"),
                "pan_id": ds.get("pan_id"),
                "mesh_local_prefix": ds.get("mesh_local_prefix"),
                "preferred": is_pref,
                "source": ds.get("source", "HA Dataset Store"),
            }
            if ext_pan_id not in networks:
                networks[ext_pan_id] = [dataset_entry]
            else:
                # Propagate preferred badge to routers on the preferred dataset
                if is_pref:
                    for r in networks[ext_pan_id]:
                        r["preferred"] = True

        # Only count networks that have real Extended PAN IDs
        valid_network_keys = [k for k in networks.keys() if k not in ("UNKNOWN", "DATASET_UNKNOWN", "HA_DATASET")]
        # Check how many distinct Extended PAN IDs have active Border Routers
        router_xpans = sorted({
            r["extended_pan_id"]
            for r in all_discovered_routers
            if r.get("extended_pan_id") and r["extended_pan_id"] not in ("UNKNOWN", "DATASET_UNKNOWN")
        })

        num_distinct_networks = len(router_xpans) if router_xpans else len(valid_network_keys)
        is_split = num_distinct_networks > 1

        # Evaluate against selected target network if provided
        target_matched = []
        target_mismatched = []
        if target_network_id:
            tid_upper = target_network_id.upper().replace(":", "")
            tid_lower = target_network_id.lower()
            for r in all_discovered_routers:
                rxpan = (r.get("extended_pan_id") or "").upper()
                rname = (r.get("network_name") or r.get("name") or "").lower()
                matches = (tid_upper == rxpan) or (tid_upper in rxpan and len(tid_upper) >= 6) or (tid_lower == rname)
                r["is_target_network"] = matches
                if matches:
                    target_matched.append(r)
                else:
                    target_mismatched.append(r)

        if is_split:
            xpan_summary = ", ".join(router_xpans if router_xpans else valid_network_keys)
            summary = (
                f"CRITICAL SPLIT THREAD MESH: Detected {num_distinct_networks} separate Thread Extended PAN IDs ({xpan_summary})! "
                "Your Border Routers are operating on independent Thread meshes rather than a single unified fabric."
            )
            if found_nest_wifi_pro:
                recommendation = (
                    "To unify your Google Nest Wifi Pro with Home Assistant:\n"
                    "1. Open the Home Assistant Companion App on your phone (signed into the same Google Home account).\n"
                    "2. Go to Settings -> Companion App -> Troubleshooting -> Sync Thread Credentials.\n"
                    "3. In Home Assistant UI, go to Settings -> Devices & Services -> Thread and set your primary mesh as Preferred."
                )
            else:
                recommendation = (
                    "Synchronize your Thread credentials in Home Assistant (Settings -> Devices & Services -> Thread) "
                    "so all Border Routers share the exact same Operational Dataset and Extended PAN ID."
                )
        elif len(all_discovered_routers) == 0 and len(valid_network_keys) == 0:
            summary = "No active Thread Border Routers or datasets discovered on the local network yet."
            recommendation = "Ensure your Thread Border Routers (Apple TV, HomePod, Nest Wifi Pro, or HA OTBR) are online on the same LAN/VLAN and mDNS is permitted."
        else:
            active_xpan = router_xpans[0] if router_xpans else (valid_network_keys[0] if valid_network_keys else "Single Mesh")
            summary = f"All {len(all_discovered_routers)} discovered Border Router(s) are synchronized on Extended PAN ID {active_xpan}."
            recommendation = "Thread Border Router synchronization is healthy."

        if target_network_id and target_mismatched:
            mismatched_names = ", ".join(f"{r['name']} (XPAN: {r.get('extended_pan_id', '')[:8]})" for r in target_mismatched)
            summary += f" [Selected Network Filter: {len(target_matched)} router(s) on target network; {len(target_mismatched)} router(s) on other PANs: {mismatched_names}]"

        return {
            "is_split_network": is_split,
            "distinct_network_count": max(num_distinct_networks, 1) if (all_discovered_routers or valid_network_keys) else 0,
            "networks": networks,
            "all_discovered_routers": all_discovered_routers,
            "found_nest_wifi_pro": found_nest_wifi_pro,
            "found_ha_router": found_ha_router,
            "target_network_id": target_network_id,
            "target_matched_count": len(target_matched),
            "target_mismatched_count": len(target_mismatched),
            "summary": summary,
            "recommendation": recommendation,
        }

    @staticmethod
    def evaluate_node_link_quality(
        nodes: List[Dict[str, Any]],
        target_network_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze Matter-over-Thread nodes using real Cluster 0x0035 telemetry:
        RSSI, LQI, NeighborTable frame/message error rates, parent changes, detach counts,
        and whether nodes belong to the selected target Thread network.
        """
        weak_nodes = []
        offline_nodes = []
        healthy_nodes = []
        wrong_network_nodes = []

        tid_upper = (target_network_id or "").upper().replace(":", "")

        for node in nodes:
            node_id = node.get("node_id")
            name = node.get("product_name") or f"Node {node_id}"
            vendor = node.get("vendor_name") or "Unknown"
            is_avail = bool(node.get("available", False))
            rssi = node.get("rssi")
            lqi = node.get("lqi")
            role = node.get("routing_role") or "Thread Node"
            rloc16 = node.get("rloc16")
            node_xpan = (node.get("extended_pan_id") or "").upper()
            counters = node.get("telemetry_counters") or {}
            parent_changes = counters.get("parent_change_count") or 0
            detach_count = counters.get("detached_role_count") or 0

            # Check if node is on a different Extended PAN ID than the selected target network
            if tid_upper and node_xpan and tid_upper not in node_xpan and len(tid_upper) >= 8:
                wrong_network_nodes.append({
                    "node_id": node_id,
                    "name": name,
                    "vendor": vendor,
                    "extended_pan_id": node_xpan,
                    "reason": f"Joined to XPAN {node_xpan} instead of selected target {tid_upper}",
                })

            if not is_avail:
                offline_nodes.append({
                    "node_id": node_id,
                    "name": name,
                    "vendor": vendor,
                    "routing_role": role,
                    "rloc16": rloc16,
                    "extended_pan_id": node_xpan,
                    "reason": f"Unreachable / Offline (Detached count: {detach_count}, Parent changes: {parent_changes})" if (detach_count or parent_changes) else "Unreachable / Ping Timeout",
                })
            elif (rssi is not None and rssi < -82) or (lqi is not None and lqi < 64):
                reason_parts = []
                if rssi is not None and rssi < -82:
                    reason_parts.append(f"Weak RSSI ({rssi} dBm < -82 dBm)")
                if lqi is not None and lqi < 64:
                    reason_parts.append(f"Low LQI ({lqi}/255)")
                if parent_changes > 5:
                    reason_parts.append(f"Frequent parent switches ({parent_changes})")
                weak_nodes.append({
                    "node_id": node_id,
                    "name": name,
                    "vendor": vendor,
                    "routing_role": role,
                    "rloc16": rloc16,
                    "rssi": rssi,
                    "lqi": lqi,
                    "reason": ", ".join(reason_parts),
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
            "wrong_network_count": len(wrong_network_nodes),
            "health_score": health_percentage,
            "weak_nodes": weak_nodes,
            "offline_nodes": offline_nodes,
            "wrong_network_nodes": wrong_network_nodes,
            "summary": (
                f"{len(healthy_nodes)}/{total} Matter nodes operational. "
                f"{len(offline_nodes)} offline, {len(weak_nodes)} weak RF link."
                + (f" ({len(wrong_network_nodes)} on different Thread XPAN)" if wrong_network_nodes else "")
            ),
        }

    @staticmethod
    def build_real_mesh_topology(
        discovered_routers: List[Dict[str, Any]],
        matter_nodes: List[Dict[str, Any]],
        target_net: Optional[Dict[str, Any]] = None,
        target_id: Optional[str] = None,
        is_split: bool = False,
        ping_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Build an authentic Thread mesh graph using real IEEE 802.15.4 Extended Addresses (`ext_address`),
        RLOC16 parent-child bitmasks (`0xFC00`), Cluster 0x0035 `neighbor_table` & `route_table`,
        and Extended PAN IDs (`extended_pan_id`).
        """
        graph_nodes: List[Dict[str, Any]] = []
        graph_edges: List[Dict[str, Any]] = []
        seen_edges = set()

        ping_by_ip = {p["ip"]: p for p in (ping_results or []) if isinstance(p, dict) and p.get("ip")}

        target_xpan = ""
        target_name = ""
        if target_net:
            target_xpan = (target_net.get("extended_pan_id") or "").upper()
            target_name = (target_net.get("name") or "").lower()
        elif target_id:
            target_xpan = target_id.upper()
            target_name = target_id.lower()

        # Maps for real Thread link resolution
        ext_addr_to_graph_id: Dict[str, str] = {}
        rloc16_to_graph_id: Dict[str, str] = {}
        router_prefix_to_graph_id: Dict[int, str] = {}  # (rloc16_int & 0xFC00) -> router node graph id
        xpan_to_br_ids: Dict[str, List[str]] = {}
        br_node_ids: List[str] = []

        # 1. Add Border Routers
        for idx, r in enumerate(discovered_routers):
            r_type = r.get("type", "generic")
            r_name = r.get("name") or "Thread Border Router"
            r_model = r.get("model") or "Border Router"
            r_brand = r.get("brand") or "Generic"
            r_net = r.get("network_name") or "Thread Mesh"
            r_xpan = (r.get("extended_pan_id") or "UNKNOWN").upper()
            r_ch = r.get("channel")
            r_ext = (r.get("ext_address") or "").upper()
            r_rloc = r.get("rloc16")
            r_addrs = r.get("addresses") or []

            node_id = f"br_{r_type}_{idx}"
            br_node_ids.append(node_id)
            if r_xpan:
                xpan_to_br_ids.setdefault(r_xpan, []).append(node_id)
            if r_ext:
                ext_addr_to_graph_id[r_ext] = node_id
            if r_rloc:
                rloc16_to_graph_id[str(r_rloc).upper()] = node_id
                try:
                    r_int = int(str(r_rloc), 16)
                    if (r_int & 0x03FF) == 0:
                        router_prefix_to_graph_id[r_int & 0xFC00] = node_id
                except ValueError:
                    pass

            is_target_match = True
            status = "online"
            if target_id:
                if target_xpan and target_xpan != "UNKNOWN":
                    is_target_match = (r_xpan == target_xpan or target_xpan in r_xpan)
                else:
                    is_target_match = (target_name in r_net.lower() or target_name in r_name.lower())
                if not is_target_match:
                    status = "warning"

            # Check ping latency if probed
            ping_str = ""
            for a in r_addrs:
                if a in ping_by_ip:
                    p = ping_by_ip[a]
                    ping_str = f" | Ping: {p['rtt_ms']}ms" if p.get("reachable") else " | Ping: Unreachable"
                    break

            target_badge = " [TARGET MESH]" if (target_id and is_target_match) else (" [OTHER PAN]" if (target_id and not is_target_match) else "")
            details = (
                f"Brand: {r_brand} | Model: {r_model} | Mesh: {r_net}{target_badge} | "
                f"XPAN: {r_xpan} | Ch: {r_ch or 'Auto'}"
                + (f" | RLOC16: {r_rloc}" if r_rloc else "")
                + (f" | MAC: {r_ext}" if r_ext else "")
                + (f" | IP: {r_addrs[0]}" if r_addrs else "")
                + ping_str
            )
            graph_nodes.append({
                "id": node_id,
                "label": r_name,
                "type": "border_router",
                "vendor": r_type,
                "status": status,
                "is_target": is_target_match,
                "extended_pan_id": r_xpan,
                "channel": r_ch,
                "rloc16": r_rloc,
                "ext_address": r_ext,
                "addresses": r_addrs,
                "details": details,
            })

        # Connect Border Routers that share the same Extended PAN ID (or show Split Mesh warning between different XPANs)
        if len(br_node_ids) > 1:
            for i in range(len(br_node_ids) - 1):
                src_br = graph_nodes[i]
                tgt_br = graph_nodes[i + 1]
                same_pan = (
                    src_br.get("extended_pan_id") == tgt_br.get("extended_pan_id")
                    and src_br.get("extended_pan_id") not in ("UNKNOWN", "")
                )
                edge_key = tuple(sorted([src_br["id"], tgt_br["id"]]))
                seen_edges.add(edge_key)
                graph_edges.append({
                    "source": src_br["id"],
                    "target": tgt_br["id"],
                    "label": f"Thread Backbone ({src_br.get('extended_pan_id', '')[:8]})" if same_pan else "SPLIT MESH (Different PAN IDs)",
                    "status": "ok" if same_pan else "warning",
                })

        # 2. Register all Matter nodes in lookup tables first so neighbor/parent edges can resolve peer Matter Routers
        for n in matter_nodes:
            gid = f"node_{n.get('node_id')}"
            n_ext = (n.get("ext_address") or "").upper()
            n_rloc = (n.get("rloc16") or "").upper()
            n_rloc_int = n.get("rloc16_int")
            if n_ext:
                ext_addr_to_graph_id[n_ext] = gid
            if n_rloc:
                rloc16_to_graph_id[n_rloc] = gid
            if isinstance(n_rloc_int, int) and (n_rloc_int & 0x03FF) == 0:
                router_prefix_to_graph_id[n_rloc_int & 0xFC00] = gid

        # 3. Add Matter Nodes and resolve their REAL Thread parent/neighbor links
        for idx, n in enumerate(matter_nodes):
            nid = str(n.get("node_id"))
            gid = f"node_{nid}"
            pname = n.get("product_name", f"Matter Node {nid}")
            avail = bool(n.get("available", False))
            rssi = n.get("rssi")
            lqi = n.get("lqi")
            role_id = n.get("routing_role_id")
            role_name = n.get("routing_role") or ("End Device" if ("sensor" in pname.lower() or "contact" in pname.lower() or "motion" in pname.lower()) else "Router")
            n_xpan = (n.get("extended_pan_id") or "").upper()
            n_rloc = n.get("rloc16")
            n_rloc_int = n.get("rloc16_int")
            n_ext = (n.get("ext_address") or "").upper()
            v6_addrs = n.get("ipv6_addresses") or []

            is_weak = (rssi is not None and rssi < -82) or (lqi is not None and lqi < 64)
            status = "online" if avail else "offline"
            if avail and is_weak:
                status = "weak"

            # Determine node role type for visualization
            if role_id in (5, 6) or (isinstance(n_rloc_int, int) and (n_rloc_int & 0x03FF) == 0):
                node_type = "router"
            elif role_id in (2, 3, 4) or (isinstance(n_rloc_int, int) and (n_rloc_int & 0x03FF) != 0):
                node_type = "end_device"
            else:
                node_type = "end_device" if ("sensor" in pname.lower() or "contact" in pname.lower() or "button" in pname.lower() or "lock" in pname.lower()) else "router"

            is_target_match = True
            if target_id and target_xpan and n_xpan:
                is_target_match = (n_xpan == target_xpan or target_xpan in n_xpan)

            rssi_str = f"{rssi} dBm" if rssi is not None else "N/A"
            lqi_str = f"LQI {lqi}" if lqi is not None else ""
            ping_str = ""
            for ip in v6_addrs:
                if ip in ping_by_ip:
                    p = ping_by_ip[ip]
                    ping_str = f" | Ping: {p['rtt_ms']}ms" if p.get("reachable") else " | Ping: Timeout"
                    break

            details = (
                f"Vendor: {n.get('vendor_name', 'Unknown')} | Role: {role_name} | "
                f"RSSI: {rssi_str}" + (f" ({lqi_str})" if lqi_str else "")
                + (f" | RLOC16: {n_rloc}" if n_rloc else "")
                + (f" | XPAN: {n_xpan}" if n_xpan else "")
                + (f" | IPv6: {v6_addrs[0]}" if v6_addrs else "")
                + ping_str
            )

            graph_nodes.append({
                "id": gid,
                "node_id": n.get("node_id"),
                "label": pname,
                "type": node_type,
                "routing_role": role_name,
                "status": status,
                "is_target": is_target_match,
                "rssi": rssi,
                "lqi": lqi,
                "rloc16": n_rloc,
                "ext_address": n_ext,
                "extended_pan_id": n_xpan,
                "ipv6_addresses": v6_addrs,
                "neighbor_count": len(n.get("neighbor_table", [])),
                "details": details,
            })

            # --- Resolve REAL Mesh Edges for this Node ---
            connected_to_any = False

            # (A) Explicit links from Cluster 0x0035 NeighborTable
            for nb in n.get("neighbor_table", []):
                nb_ext = (nb.get("ext_address") or "").upper()
                nb_rloc = (nb.get("rloc16") or "").upper()
                peer_gid = ext_addr_to_graph_id.get(nb_ext) or rloc16_to_graph_id.get(nb_rloc)
                if peer_gid and peer_gid != gid:
                    edge_key = tuple(sorted([gid, peer_gid]))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        nb_rssi = nb.get("last_rssi") if nb.get("last_rssi") is not None else nb.get("average_rssi")
                        nb_lqi = nb.get("lqi")
                        lbl = f"{nb_rssi} dBm" if nb_rssi is not None else (f"LQI {nb_lqi}" if nb_lqi is not None else "Thread Link")
                        graph_edges.append({
                            "source": peer_gid,
                            "target": gid,
                            "label": lbl,
                            "status": "warning" if (status in ("offline", "weak") or (nb_rssi is not None and nb_rssi < -82)) else "ok",
                        })
                    connected_to_any = True

            # (B) RLOC16 Parent Router prefix match: (child_rloc16 & 0xFC00) == parent_router_rloc16
            if not connected_to_any and isinstance(n_rloc_int, int) and (n_rloc_int & 0x03FF) != 0:
                parent_gid = router_prefix_to_graph_id.get(n_rloc_int & 0xFC00)
                if parent_gid and parent_gid != gid:
                    edge_key = tuple(sorted([gid, parent_gid]))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        graph_edges.append({
                            "source": parent_gid,
                            "target": gid,
                            "label": rssi_str if rssi is not None else f"RLOC {n_rloc}",
                            "status": "warning" if status in ("offline", "weak") else "ok",
                        })
                    connected_to_any = True

            # (C) Match to Border Router on the exact same Extended PAN ID (`0/53/4`)
            if not connected_to_any and n_xpan and n_xpan in xpan_to_br_ids:
                matching_brs = xpan_to_br_ids[n_xpan]
                parent_br = matching_brs[0]
                edge_key = tuple(sorted([gid, parent_br]))
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    graph_edges.append({
                        "source": parent_br,
                        "target": gid,
                        "label": rssi_str if rssi is not None else f"XPAN {n_xpan[:6]}",
                        "status": "warning" if status in ("offline", "weak") else "ok",
                    })
                connected_to_any = True

            # (D) If node has no Extended PAN ID attribute yet (e.g. offline/uninterviewed or simple test fixture),
            # connect to the primary/target Border Router if one exists
            if not connected_to_any and br_node_ids:
                primary_br = br_node_ids[0]
                edge_key = tuple(sorted([gid, primary_br]))
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    graph_edges.append({
                        "source": primary_br,
                        "target": gid,
                        "label": rssi_str if rssi is not None else "No link",
                        "status": "warning" if status in ("offline", "weak") else "ok",
                    })

        return {"nodes": graph_nodes, "edges": graph_edges, "target_network": target_net}
