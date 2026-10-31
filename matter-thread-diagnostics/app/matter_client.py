"""
Matter Server Client for querying python-matter-server WebSocket API directly.
Extracts real Matter Basic Information (Cluster 0x0028), General Diagnostics (Cluster 0x0033),
Thread Network Diagnostics (Cluster 0x0035: NeighborTable, RouteTable, RSSI, LQI, RLOC16,
Extended PAN ID, RoutingRole, error counters), and Wi-Fi Network Diagnostics (Cluster 0x0036).
Also supports active node pinging via `ping_node`.
"""
import asyncio
import base64
import ipaddress
import json
import logging
from typing import Dict, Any, List, Optional
import websockets

logger = logging.getLogger("matter_thread_ai.matter_client")

THREAD_ROUTING_ROLES = {
    0: "Unspecified",
    1: "Unassigned",
    2: "Sleepy End Device (SED/ICD)",
    3: "End Device (MED)",
    4: "REED (Router-Eligible End Device)",
    5: "Router",
    6: "Leader",
}


def _format_ext_uint64(val: Any) -> Optional[str]:
    """Convert uint64 int, hex string, or base64 bytes into a 16-char uppercase hex string."""
    if val is None:
        return None
    if isinstance(val, int):
        if val < 0:
            return None
        return f"{val:016X}"
    if isinstance(val, str):
        s = val.strip().replace(":", "").replace("-", "")
        if s.lower().startswith("0x"):
            s = s[2:]
        if all(c in "0123456789abcdefABCDEF" for c in s) and len(s) in (8, 12, 16):
            return s.upper().zfill(16)
        try:
            raw = base64.b64decode(val)
            if len(raw) == 8:
                return raw.hex().upper()
        except Exception:
            pass
    return None


def _format_rloc16(val: Any) -> Optional[str]:
    """Format uint16 RLOC16 as 0xXXXX."""
    if val is None:
        return None
    try:
        ival = int(val)
        return f"0x{ival:04X}"
    except (ValueError, TypeError):
        return None


def _decode_ipv6_address(raw_val: Any) -> Optional[str]:
    """Decode an IPv6 address from string, hex, or base64-encoded 16-byte buffer."""
    if not raw_val:
        return None
    if isinstance(raw_val, str):
        s = raw_val.strip()
        if ":" in s:
            try:
                return str(ipaddress.IPv6Address(s))
            except ValueError:
                pass
        # Try base64 (python-matter-server serializes bytes as base64 in JSON)
        try:
            b = base64.b64decode(s)
            if len(b) == 16:
                return str(ipaddress.IPv6Address(b))
        except Exception:
            pass
        # Try raw 32-char hex
        if len(s) == 32 and all(c in "0123456789abcdefABCDEF" for c in s):
            try:
                return str(ipaddress.IPv6Address(bytes.fromhex(s)))
            except Exception:
                pass
    elif isinstance(raw_val, (bytes, bytearray)) and len(raw_val) == 16:
        return str(ipaddress.IPv6Address(bytes(raw_val)))
    return None


def _decode_mesh_local_prefix(raw_val: Any) -> Optional[str]:
    """Decode Thread Mesh-Local Prefix (8-byte prefix or 9-byte length+prefix) to fdxx:xxxx:xxxx:xxxx::/64."""
    if not raw_val:
        return None
    if isinstance(raw_val, str):
        s = raw_val.strip()
        if s.lower().startswith("fd") and ":" in s:
            return s if "/" in s else f"{s}/64"
        try:
            b = base64.b64decode(s)
            if len(b) == 9 and b[0] == 64:
                b = b[1:]
            if len(b) >= 8:
                addr_bytes = b[:8] + b"\x00" * 8
                return f"{ipaddress.IPv6Address(addr_bytes)}/64"
        except Exception:
            pass
    return None


class MatterClient:
    def __init__(self, ws_url: str = "ws://core-matter-server:5580/ws"):
        self.ws_url = ws_url
        self._working_url: Optional[str] = None

    def _candidate_urls(self) -> List[str]:
        candidates = []
        if self._working_url:
            candidates.append(self._working_url)
        if self.ws_url:
            candidates.append(self.ws_url)
        for fallback in [
            "ws://core-matter-server:5580/ws",
            "ws://localhost:5580/ws",
            "ws://127.0.0.1:5580/ws",
            "ws://homeassistant.local:5580/ws",
        ]:
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    async def _send_command(self, ws, message_id: str, command: str, args: Optional[Dict[str, Any]] = None, timeout: float = 6.0) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"message_id": message_id, "command": command}
        if args:
            payload["args"] = args
        await ws.send(json.dumps(payload))

        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError(f"Timed out waiting for response to '{command}'")
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            msg = json.loads(raw)
            if isinstance(msg, dict) and msg.get("message_id") == message_id:
                return msg

    async def get_nodes_and_server_info(self, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Connect to python-matter-server WebSocket API, consume the initial ServerInfoMessage
        greeting, and retrieve full node attributes including Thread Network Diagnostics (Cluster 0x0035).
        """
        result: Dict[str, Any] = {
            "connected": False,
            "ws_url_used": None,
            "server_version": None,
            "schema_version": None,
            "fabric_id": None,
            "compressed_fabric_id": None,
            "thread_credentials_set": None,
            "wifi_credentials_set": None,
            "bluetooth_enabled": None,
            "nodes": [],
            "error": None,
        }

        last_err = None
        for url in self._candidate_urls():
            try:
                async with websockets.connect(url, open_timeout=timeout, max_size=16 * 1024 * 1024) as ws:
                    result["connected"] = True
                    result["ws_url_used"] = url
                    self._working_url = url

                    # 1. Read initial unsolicited ServerInfoMessage greeting sent by python-matter-server on connect
                    try:
                        greeting_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                        greeting = json.loads(greeting_raw)
                        if isinstance(greeting, dict) and ("fabric_id" in greeting or "schema_version" in greeting):
                            result["server_version"] = greeting.get("sdk_version") or greeting.get("version")
                            result["schema_version"] = greeting.get("schema_version")
                            result["fabric_id"] = greeting.get("fabric_id")
                            cfid = greeting.get("compressed_fabric_id")
                            result["compressed_fabric_id"] = f"{cfid:016X}" if isinstance(cfid, int) else cfid
                            result["thread_credentials_set"] = greeting.get("thread_credentials_set")
                            result["wifi_credentials_set"] = greeting.get("wifi_credentials_set")
                            result["bluetooth_enabled"] = greeting.get("bluetooth_enabled")
                    except Exception as e:
                        logger.debug("Did not receive standard greeting from %s: %s", url, e)

                    # 2. If server_version was not in greeting, explicitly call server_info
                    if result["schema_version"] is None:
                        try:
                            info_msg = await self._send_command(ws, "srv_info_1", "server_info", timeout=timeout)
                            info_res = info_msg.get("result") or {}
                            if isinstance(info_res, dict):
                                result["server_version"] = info_res.get("sdk_version") or info_res.get("version")
                                result["schema_version"] = info_res.get("schema_version")
                                result["fabric_id"] = info_res.get("fabric_id")
                                cfid = info_res.get("compressed_fabric_id")
                                result["compressed_fabric_id"] = f"{cfid:016X}" if isinstance(cfid, int) else cfid
                                result["thread_credentials_set"] = info_res.get("thread_credentials_set")
                                result["wifi_credentials_set"] = info_res.get("wifi_credentials_set")
                        except Exception as e:
                            logger.debug("server_info command failed: %s", e)

                    # 3. Fetch all commissioned Matter nodes
                    nodes_msg = await self._send_command(ws, "get_nodes_1", "get_nodes", timeout=timeout)
                    raw_nodes = nodes_msg.get("result")
                    if isinstance(raw_nodes, list):
                        result["nodes"] = self._format_nodes(raw_nodes)
                    elif isinstance(raw_nodes, dict):
                        node_vals = [v for v in raw_nodes.values() if isinstance(v, dict)]
                        result["nodes"] = self._format_nodes(node_vals)

                    result["error"] = None
                    return result

            except Exception as e:
                last_err = f"{url}: {type(e).__name__}: {e}"
                logger.debug("Matter Server connection attempt failed (%s)", last_err)

        result["error"] = f"Could not connect to Matter Server ({last_err})"
        return result

    async def ping_node(self, node_id: int, timeout: float = 10.0) -> Dict[str, Any]:
        """Actively ping a Matter node via python-matter-server's `ping_node` command."""
        for url in self._candidate_urls():
            try:
                async with websockets.connect(url, open_timeout=4.0, max_size=8 * 1024 * 1024) as ws:
                    # Consume greeting
                    await asyncio.wait_for(ws.recv(), timeout=3.0)
                    msg = await self._send_command(
                        ws,
                        f"ping_{node_id}",
                        "ping_node",
                        args={"node_id": int(node_id)},
                        timeout=timeout,
                    )
                    if "error_code" in msg:
                        return {"node_id": node_id, "success": False, "error": msg.get("details", "Ping failed")}
                    return {"node_id": node_id, "success": True, "result": msg.get("result", {})}
            except Exception as e:
                logger.debug("ping_node failed on %s: %s", url, e)
        return {"node_id": node_id, "success": False, "error": "Matter Server unreachable"}

    async def remove_node(self, node_id: int, timeout: float = 15.0) -> Dict[str, Any]:
        """
        Decommission and purge a Matter node from the Matter fabric and python-matter-server store
        via the `remove_node` WebSocket command.
        """
        last_err = "Matter Server unreachable"
        for url in self._candidate_urls():
            try:
                async with websockets.connect(url, open_timeout=4.0, max_size=8 * 1024 * 1024) as ws:
                    # Consume greeting
                    await asyncio.wait_for(ws.recv(), timeout=3.0)
                    msg = await self._send_command(
                        ws,
                        f"remove_node_{node_id}",
                        "remove_node",
                        args={"node_id": int(node_id)},
                        timeout=timeout,
                    )
                    if "error_code" in msg:
                        err_detail = msg.get("details") or f"Error code {msg.get('error_code')}"
                        logger.warning("remove_node(%s) returned error from Matter Server: %s", node_id, err_detail)
                        return {"node_id": int(node_id), "success": False, "error": err_detail}
                    logger.info("Successfully purged Matter node #%s via %s", node_id, url)
                    return {"node_id": int(node_id), "success": True, "result": msg.get("result")}
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                logger.debug("remove_node failed on %s: %s", url, e)
        return {"node_id": int(node_id), "success": False, "error": last_err}

    def _format_nodes(self, raw_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parse python-matter-server nodes and extract real Thread Network Diagnostics
        (Cluster 0x0035 / 53), General Diagnostics (Cluster 0x0033 / 51), and Basic Info (Cluster 0x0028 / 40).
        Also cross-references neighbor tables across nodes so Sleepy End Devices get their parent's RSSI/LQI.
        """
        formatted: List[Dict[str, Any]] = []

        for n in raw_nodes:
            if not isinstance(n, dict):
                continue

            node_id = n.get("node_id")
            available = bool(n.get("available", False))
            attrs: Dict[str, Any] = n.get("attributes") if isinstance(n.get("attributes"), dict) else {}

            # --- 1. Basic Information Cluster (40 / 0x0028) ---
            vendor_name = attrs.get("0/40/1") or n.get("vendor_name") or "Unknown Vendor"
            vendor_id = attrs.get("0/40/2")
            product_name = attrs.get("0/40/3") or n.get("product_name") or f"Matter Node {node_id}"
            product_id = attrs.get("0/40/4")
            node_label = attrs.get("0/40/5") or ""
            hw_version = attrs.get("0/40/7")
            sw_version = attrs.get("0/40/8")
            serial_number = attrs.get("0/40/15")

            # Fallback for nested endpoints structure if present in custom test fixtures
            endpoints = n.get("endpoints", {})
            if isinstance(endpoints, dict) and "0/40/1" not in attrs:
                for ep_val in endpoints.values():
                    clusters = ep_val.get("clusters", {}) if isinstance(ep_val, dict) else {}
                    if "40" in clusters:
                        c = clusters["40"].get("attributes", {})
                        vendor_name = c.get("1") or c.get("vendor_name") or vendor_name
                        product_name = c.get("3") or c.get("product_name") or product_name
                        sw_version = c.get("8") or c.get("software_version_string") or sw_version
                        serial_number = c.get("15") or c.get("serial_number") or serial_number
                        break

            # --- 2. General Diagnostics Cluster (51 / 0x0033) ---
            ipv6_addresses: List[str] = []
            ipv4_addresses: List[str] = []
            hw_mac_address: Optional[str] = None
            net_interfaces = attrs.get("0/51/0")
            if isinstance(net_interfaces, list):
                for iface in net_interfaces:
                    if not isinstance(iface, dict):
                        continue
                    hw_raw = iface.get("4") or iface.get("hardwareAddress")
                    if hw_raw and not hw_mac_address:
                        hw_mac_address = _format_ext_uint64(hw_raw)
                    v6_list = iface.get("6") or iface.get("iPv6Addresses") or []
                    if isinstance(v6_list, list):
                        for raw_ip in v6_list:
                            decoded = _decode_ipv6_address(raw_ip)
                            if decoded and decoded not in ipv6_addresses:
                                ipv6_addresses.append(decoded)
            reboot_count = attrs.get("0/51/1")
            uptime_seconds = attrs.get("0/51/2")

            # --- 3. Thread Network Diagnostics Cluster (53 / 0x0035) ---
            thread_channel = attrs.get("0/53/0")
            routing_role_id = attrs.get("0/53/1")
            routing_role_name = THREAD_ROUTING_ROLES.get(routing_role_id, "Unknown") if routing_role_id is not None else None
            thread_network_name = attrs.get("0/53/2")
            pan_id_raw = attrs.get("0/53/3")
            pan_id_hex = f"0x{int(pan_id_raw):04X}" if isinstance(pan_id_raw, int) else (str(pan_id_raw) if pan_id_raw else None)
            extended_pan_id = _format_ext_uint64(attrs.get("0/53/4"))
            mesh_local_prefix = _decode_mesh_local_prefix(attrs.get("0/53/5"))
            overrun_count = attrs.get("0/53/6", 0)

            # Parse NeighborTable (0/53/7)
            raw_neighbors = attrs.get("0/53/7")
            neighbor_table: List[Dict[str, Any]] = []
            if isinstance(raw_neighbors, list):
                for nb in raw_neighbors:
                    if not isinstance(nb, dict):
                        continue
                    nb_ext = _format_ext_uint64(nb.get("0") if "0" in nb else nb.get("extAddress"))
                    nb_age = nb.get("1") if "1" in nb else nb.get("age")
                    nb_rloc = nb.get("2") if "2" in nb else nb.get("rloc16")
                    nb_lqi = nb.get("5") if "5" in nb else nb.get("lqi")
                    nb_avg_rssi = nb.get("6") if "6" in nb else nb.get("averageRssi")
                    nb_last_rssi = nb.get("7") if "7" in nb else nb.get("lastRssi")
                    nb_fer = nb.get("8") if "8" in nb else nb.get("frameErrorRate", 0)
                    nb_mer = nb.get("9") if "9" in nb else nb.get("messageErrorRate", 0)
                    nb_rx_idle = nb.get("10") if "10" in nb else nb.get("rxOnWhenIdle")
                    nb_ftd = nb.get("11") if "11" in nb else nb.get("fullThreadDevice")
                    nb_is_child = bool(nb.get("13") if "13" in nb else nb.get("isChild", False))

                    neighbor_table.append({
                        "ext_address": nb_ext,
                        "rloc16": _format_rloc16(nb_rloc),
                        "rloc16_int": nb_rloc if isinstance(nb_rloc, int) else None,
                        "age_sec": nb_age,
                        "lqi": nb_lqi,
                        "average_rssi": nb_avg_rssi,
                        "last_rssi": nb_last_rssi,
                        "frame_error_rate_pct": round((nb_fer / 255.0) * 100, 1) if isinstance(nb_fer, int) else 0.0,
                        "message_error_rate_pct": round((nb_mer / 255.0) * 100, 1) if isinstance(nb_mer, int) else 0.0,
                        "rx_on_when_idle": nb_rx_idle,
                        "full_thread_device": nb_ftd,
                        "is_child": nb_is_child,
                    })

            # Parse RouteTable (0/53/8)
            raw_routes = attrs.get("0/53/8")
            route_table: List[Dict[str, Any]] = []
            if isinstance(raw_routes, list):
                for rt in raw_routes:
                    if not isinstance(rt, dict):
                        continue
                    rt_ext = _format_ext_uint64(rt.get("0") if "0" in rt else rt.get("extAddress"))
                    rt_rloc = rt.get("1") if "1" in rt else rt.get("rloc16")
                    rt_router_id = rt.get("2") if "2" in rt else rt.get("routerId")
                    rt_next_hop = rt.get("3") if "3" in rt else rt.get("nextHop")
                    rt_cost = rt.get("4") if "4" in rt else rt.get("pathCost")
                    rt_lqi_in = rt.get("5") if "5" in rt else rt.get("lqiIn")
                    rt_lqi_out = rt.get("6") if "6" in rt else rt.get("lqiOut")
                    rt_age = rt.get("7") if "7" in rt else rt.get("age")
                    rt_link = bool(rt.get("9") if "9" in rt else rt.get("linkEstablished", False))
                    if rt_link or rt_ext:
                        route_table.append({
                            "ext_address": rt_ext,
                            "rloc16": _format_rloc16(rt_rloc),
                            "router_id": rt_router_id,
                            "next_hop": rt_next_hop,
                            "path_cost": rt_cost,
                            "lqi_in": rt_lqi_in,
                            "lqi_out": rt_lqi_out,
                            "age": rt_age,
                            "link_established": rt_link,
                        })

            partition_id = attrs.get("0/53/9")
            leader_router_id = attrs.get("0/53/13")
            detached_role_count = attrs.get("0/53/14", 0)
            attach_attempt_count = attrs.get("0/53/18", 0)
            partition_change_count = attrs.get("0/53/19", 0)
            parent_change_count = attrs.get("0/53/21", 0)
            ext_address = _format_ext_uint64(attrs.get("0/53/62")) or hw_mac_address
            rloc16_raw = attrs.get("0/53/63")
            rloc16 = _format_rloc16(rloc16_raw)

            # Determine best RSSI and LQI for this node from its Thread NeighborTable
            # (or direct attribute fallback if provided in unit tests)
            rssi = n.get("rssi")
            lqi = n.get("lqi")
            parent_ext_address = None
            parent_rloc16 = None

            if neighbor_table:
                # Prefer non-child neighbors (i.e. parent router or peer routers) for uplink signal quality
                uplinks = [nb for nb in neighbor_table if not nb.get("is_child")]
                candidates = uplinks if uplinks else neighbor_table
                rssi_vals = [
                    nb["last_rssi"] if nb.get("last_rssi") is not None else nb.get("average_rssi")
                    for nb in candidates
                    if (nb.get("last_rssi") is not None or nb.get("average_rssi") is not None)
                ]
                lqi_vals = [nb["lqi"] for nb in candidates if nb.get("lqi") is not None]
                if rssi_vals and rssi is None:
                    rssi = max(rssi_vals)
                if lqi_vals and lqi is None:
                    lqi = max(lqi_vals)
                if uplinks:
                    best_parent = max(
                        uplinks,
                        key=lambda x: (x.get("last_rssi") or x.get("average_rssi") or -127),
                    )
                    parent_ext_address = best_parent.get("ext_address")
                    parent_rloc16 = best_parent.get("rloc16")

            # --- 4. Wi-Fi Diagnostics Cluster (54 / 0x0036) vs Thread Transport Detection ---
            has_thread_cluster = any(k.startswith("0/53/") for k in attrs.keys()) or bool(thread_channel or extended_pan_id or neighbor_table)
            has_wifi_cluster = any(k.startswith("0/54/") for k in attrs.keys()) and attrs.get("0/54/0") is not None
            wifi_rssi = attrs.get("0/54/4")

            if has_thread_cluster:
                transport = "thread"
            elif has_wifi_cluster:
                transport = "wifi"
                if rssi is None and isinstance(wifi_rssi, int):
                    rssi = wifi_rssi
            else:
                transport = n.get("transport", "thread")

            display_name = f"{product_name} ({node_label})" if node_label and node_label not in product_name else product_name

            formatted.append({
                "node_id": node_id,
                "available": available,
                "transport": transport,
                "vendor_name": vendor_name,
                "vendor_id": vendor_id,
                "product_name": display_name,
                "product_id": product_id,
                "serial_number": serial_number,
                "hardware_version": hw_version,
                "software_version": sw_version,
                "date_commissioned": n.get("date_commissioned"),
                "last_interview": n.get("last_interview"),
                "is_bridge": bool(n.get("is_bridge", False)),
                # Network & IPv6
                "ipv6_addresses": ipv6_addresses,
                "ext_address": ext_address,
                "rloc16": rloc16,
                "rloc16_int": rloc16_raw if isinstance(rloc16_raw, int) else None,
                # Thread Cluster 0x0035 Telemetry
                "thread_channel": thread_channel,
                "routing_role": routing_role_name,
                "routing_role_id": routing_role_id,
                "thread_network_name": thread_network_name,
                "pan_id": pan_id_hex,
                "extended_pan_id": extended_pan_id,
                "mesh_local_prefix": mesh_local_prefix,
                "partition_id": partition_id,
                "leader_router_id": leader_router_id,
                "rssi": rssi,
                "lqi": lqi,
                "parent_ext_address": parent_ext_address,
                "parent_rloc16": parent_rloc16,
                "neighbor_table": neighbor_table,
                "route_table": route_table,
                "telemetry_counters": {
                    "reboot_count": reboot_count,
                    "uptime_seconds": uptime_seconds,
                    "overrun_count": overrun_count,
                    "detached_role_count": detached_role_count,
                    "attach_attempt_count": attach_attempt_count,
                    "partition_change_count": partition_change_count,
                    "parent_change_count": parent_change_count,
                },
                "raw_summary": {
                    "attribute_count": len(attrs),
                    "neighbors_count": len(neighbor_table),
                    "routes_count": len(route_table),
                },
            })

        # Second pass: cross-reference parent Router neighbor tables to fill in RSSI/LQI/Parent for Sleepy End Devices
        ext_map = {node["ext_address"]: node for node in formatted if node.get("ext_address")}
        rloc_map = {node["rloc16"]: node for node in formatted if node.get("rloc16")}

        for router_node in formatted:
            for nb in router_node.get("neighbor_table", []):
                if nb.get("is_child"):
                    child = ext_map.get(nb.get("ext_address")) or rloc_map.get(nb.get("rloc16"))
                    if child:
                        if child.get("rssi") is None:
                            child["rssi"] = nb.get("last_rssi") if nb.get("last_rssi") is not None else nb.get("average_rssi")
                        if child.get("lqi") is None:
                            child["lqi"] = nb.get("lqi")
                        if not child.get("parent_ext_address") and router_node.get("ext_address"):
                            child["parent_ext_address"] = router_node["ext_address"]
                        if not child.get("parent_rloc16") and router_node.get("rloc16"):
                            child["parent_rloc16"] = router_node["rloc16"]

        return formatted
