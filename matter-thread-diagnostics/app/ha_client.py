"""
Home Assistant & Supervisor Client for Matter & Thread diagnostics.
Interacts with Home Assistant Core, Supervisor, and WebSocket endpoints.
Supports real streaming `thread/discover_routers` subscriptions and Thread Operational Dataset TLV decoding.
"""
import asyncio
import ipaddress
import json
import logging
import struct
from typing import Dict, Any, List, Optional
import httpx
import websockets

from network_checker import NetworkChecker

logger = logging.getLogger("matter_thread_ai.ha_client")


def parse_thread_dataset_tlv(tlv_hex: str) -> Dict[str, Any]:
    """
    Decode a raw Thread 1.3/1.4 Operational Dataset TLV hex string into structured fields:
      - 0x00: Channel (page + uint16 channel)
      - 0x01: PAN ID (uint16)
      - 0x02: Extended PAN ID (8 bytes)
      - 0x03: Network Name (UTF-8 string)
      - 0x07: Mesh-Local Prefix (8 bytes -> fdxx:xxxx:xxxx:xxxx::/64)
      - 0x0e: Active Timestamp
    """
    parsed: Dict[str, Any] = {}
    if not tlv_hex or not isinstance(tlv_hex, str):
        return parsed
    clean = tlv_hex.strip().replace(" ", "").replace("0x", "")
    try:
        data = bytes.fromhex(clean)
    except ValueError:
        return parsed

    idx = 0
    n = len(data)
    while idx + 2 <= n:
        tlv_type = data[idx]
        tlv_len = data[idx + 1]
        idx += 2
        if idx + tlv_len > n:
            break
        val = data[idx : idx + tlv_len]
        idx += tlv_len

        if tlv_type == 0x00 and len(val) == 3:
            # Channel TLV: 1 byte channel page, 2 bytes channel number
            channel_page = val[0]
            channel_num = struct.unpack(">H", val[1:3])[0]
            parsed["channel_page"] = channel_page
            parsed["channel"] = channel_num
        elif tlv_type == 0x01 and len(val) == 2:
            pan_id = struct.unpack(">H", val)[0]
            parsed["pan_id"] = f"0x{pan_id:04X}"
            parsed["pan_id_int"] = pan_id
        elif tlv_type == 0x02 and len(val) == 8:
            parsed["extended_pan_id"] = val.hex().upper()
        elif tlv_type == 0x03:
            parsed["network_name"] = val.decode("utf-8", errors="ignore")
        elif tlv_type == 0x04 and len(val) == 16:
            parsed["has_pskc"] = True
        elif tlv_type == 0x05 and len(val) == 16:
            parsed["has_network_key"] = True
        elif tlv_type == 0x07 and len(val) >= 8:
            prefix_bytes = val[:8] + b"\x00" * 8
            try:
                parsed["mesh_local_prefix"] = f"{ipaddress.IPv6Address(prefix_bytes)}/64"
            except Exception:
                pass
        elif tlv_type == 0x0E and len(val) == 8:
            ts_u64 = struct.unpack(">Q", val)[0]
            parsed["active_timestamp_seconds"] = ts_u64 >> 16

    return parsed


class HAClient:
    def __init__(
        self,
        supervisor_token: Optional[str] = None,
        ha_url: str = "http://supervisor/core",
        supervisor_url: str = "http://supervisor",
    ):
        self.supervisor_token = supervisor_token
        self.ha_url = ha_url.rstrip("/")
        self.supervisor_url = supervisor_url.rstrip("/")
        self._working_ws_url: Optional[str] = None

    @property
    def is_available(self) -> bool:
        return bool(self.supervisor_token)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.supervisor_token:
            headers["Authorization"] = f"Bearer {self.supervisor_token}"
        return headers

    def _candidate_ws_urls(self) -> List[str]:
        candidate_urls = []
        if self._working_ws_url:
            candidate_urls.append(self._working_ws_url)
        candidate_urls.append("ws://supervisor/core/websocket")
        candidate_urls.append("ws://172.30.32.2/core/websocket")
        candidate_urls.append("ws://homeassistant:8123/api/websocket")
        candidate_urls.append("ws://localhost:8123/api/websocket")
        candidate_urls.append("ws://127.0.0.1:8123/api/websocket")
        ha_ws = self.ha_url.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
        candidate_urls.append(f"{ha_ws}/websocket")
        candidate_urls.append(f"{ha_ws}/api/websocket")

        deduped = []
        seen = set()
        for u in candidate_urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    async def get_supervisor_info(self) -> Dict[str, Any]:
        """Fetch supervisor and host information (HAOS on Green)."""
        if not self.is_available:
            return {"status": "offline", "reason": "No SUPERVISOR_TOKEN (running outside HAOS)"}

        async with httpx.AsyncClient(timeout=8.0) as client:
            res: Dict[str, Any] = {}
            for key, path in [("supervisor", "/info"), ("host", "/host/info"), ("network", "/network/info")]:
                try:
                    r = await client.get(f"{self.supervisor_url}{path}", headers=self._headers())
                    if r.status_code == 200:
                        res[key] = r.json().get("data", {})
                except Exception as e:
                    res[f"{key}_error"] = str(e)
            return res

    async def get_addon_info(self, addon_slug: str) -> Dict[str, Any]:
        """Fetch add-on details (e.g. core_matter_server or core_openthread_border_router)."""
        if not self.is_available:
            return {}
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
                r = await client.get(f"{self.supervisor_url}/addons/{addon_slug}/info", headers=self._headers())
                if r.status_code == 200:
                    return r.json().get("data", {})
            except Exception as e:
                logger.debug("Could not fetch addon info for %s: %s", addon_slug, e)
        return {}

    async def get_addon_logs(self, addon_slug: str, lines: int = 150) -> str:
        """Fetch recent logs for a specific add-on."""
        if not self.is_available:
            return ""
        async with httpx.AsyncClient(timeout=8.0) as client:
            for base in [self.supervisor_url, "http://172.30.32.2"]:
                try:
                    r = await client.get(f"{base}/addons/{addon_slug}/logs", headers=self._headers())
                    if r.status_code == 200:
                        text = r.text
                        lines_list = text.strip().split("\n")
                        return "\n".join(lines_list[-lines:])
                except Exception as e:
                    logger.debug("Could not fetch addon logs for %s from %s: %s", addon_slug, base, e)
        return ""

    async def get_matter_nodes_via_ha(self) -> List[Dict[str, Any]]:
        """Fetch Matter and Thread entities and states from Home Assistant Core."""
        if not self.is_available:
            return []
        async with httpx.AsyncClient(timeout=8.0) as client:
            for base in [self.ha_url, "http://172.30.32.2/core", "http://localhost:8123"]:
                try:
                    r = await client.get(f"{base}/api/states", headers=self._headers())
                    if r.status_code == 200:
                        states = r.json()
                        return [
                            s
                            for s in states
                            if "matter" in s.get("entity_id", "")
                            or "thread" in s.get("entity_id", "")
                            or s.get("attributes", {}).get("integration") == "matter"
                        ]
                except Exception as e:
                    logger.debug("Could not query HA states at %s: %s", base, e)
        return []

    async def query_ha_websocket(self, command: Dict[str, Any], timeout: float = 8.0) -> Dict[str, Any]:
        """Send a single request/response command over HA WebSocket API."""
        if not self.is_available:
            return {"error": "No supervisor token"}

        last_err = None
        for ws_url in self._candidate_ws_urls():
            try:
                async with websockets.connect(ws_url, open_timeout=timeout, max_size=16 * 1024 * 1024) as ws:
                    auth_req = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                    if auth_req.get("type") != "auth_required":
                        continue

                    await ws.send(json.dumps({"type": "auth", "access_token": self.supervisor_token}))
                    auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                    if auth_res.get("type") != "auth_ok":
                        last_err = f"Auth failed on {ws_url}: {auth_res}"
                        continue

                    self._working_ws_url = ws_url

                    msg_id = 1
                    command_copy = dict(command)
                    command_copy["id"] = msg_id
                    await ws.send(json.dumps(command_copy))

                    response = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                    return response
            except Exception as e:
                last_err = str(e)
                logger.debug("Attempt to connect HA websocket at %s failed: %s", ws_url, e)

        return {"error": last_err or "All WebSocket candidate URLs failed"}

    async def get_thread_datasets(self) -> Dict[str, Any]:
        """
        Fetch all Thread datasets configured in Home Assistant (`thread/list_datasets`)
        AND fetch + decode each dataset's raw Thread Operational Dataset TLV (`thread/get_dataset_tlv`)
        so we know the exact Channel, PAN ID, Extended PAN ID, and Mesh-Local Prefix (fd00::/64)!
        """
        if not self.is_available:
            return {"result": {"datasets": []}}

        for ws_url in self._candidate_ws_urls():
            try:
                async with websockets.connect(ws_url, open_timeout=6.0, max_size=8 * 1024 * 1024) as ws:
                    auth_req = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                    if auth_req.get("type") != "auth_required":
                        continue
                    await ws.send(json.dumps({"type": "auth", "access_token": self.supervisor_token}))
                    auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                    if auth_res.get("type") != "auth_ok":
                        continue

                    self._working_ws_url = ws_url

                    # 1. List datasets
                    msg_id = 1
                    await ws.send(json.dumps({"id": msg_id, "type": "thread/list_datasets"}))
                    list_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=6.0))
                    if not list_res.get("success"):
                        # Fallback to older thread/get_dataset
                        msg_id += 1
                        await ws.send(json.dumps({"id": msg_id, "type": "thread/get_dataset"}))
                        return json.loads(await asyncio.wait_for(ws.recv(), timeout=6.0))

                    res_data = list_res.get("result") or {}
                    datasets = res_data.get("datasets", []) if isinstance(res_data, dict) else (res_data if isinstance(res_data, list) else [])

                    # 2. Fetch and decode TLV for each dataset to enrich with Channel, PAN ID, Mesh-Local Prefix
                    for ds in datasets:
                        if not isinstance(ds, dict):
                            continue
                        ds_id = ds.get("dataset_id")
                        if not ds_id:
                            continue
                        try:
                            msg_id += 1
                            await ws.send(json.dumps({
                                "id": msg_id,
                                "type": "thread/get_dataset_tlv",
                                "dataset_id": ds_id,
                            }))
                            tlv_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
                            if tlv_res.get("success") and isinstance(tlv_res.get("result"), dict):
                                tlv_hex = tlv_res["result"].get("tlv")
                                if tlv_hex:
                                    decoded = parse_thread_dataset_tlv(tlv_hex)
                                    for k, v in decoded.items():
                                        if v is not None and not ds.get(k):
                                            ds[k] = v
                        except Exception as e:
                            logger.debug("Could not fetch TLV for dataset %s: %s", ds_id, e)

                    return {"success": True, "result": {"datasets": datasets}}
            except Exception as e:
                logger.debug("get_thread_datasets failed on %s: %s", ws_url, e)

        return {"result": {"datasets": []}}

    async def get_thread_routers(self, listen_timeout: float = 1.8) -> Dict[str, Any]:
        """
        Discover live Thread Border Routers via Home Assistant's `thread/discover_routers`
        WebSocket subscription stream.
        Note: In Home Assistant Core, `thread/discover_routers` first returns a `result: null` ACK
        and then streams `event` messages of type `router_discovered` as mDNS responses arrive.
        """
        if not self.is_available:
            return {"result": {"routers": []}}

        for ws_url in self._candidate_ws_urls():
            try:
                async with websockets.connect(ws_url, open_timeout=6.0, max_size=8 * 1024 * 1024) as ws:
                    auth_req = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                    if auth_req.get("type") != "auth_required":
                        continue
                    await ws.send(json.dumps({"type": "auth", "access_token": self.supervisor_token}))
                    auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                    if auth_res.get("type") != "auth_ok":
                        continue

                    self._working_ws_url = ws_url

                    sub_id = 10
                    await ws.send(json.dumps({"id": sub_id, "type": "thread/discover_routers"}))

                    routers_by_key: Dict[str, Dict[str, Any]] = {}
                    loop = asyncio.get_event_loop()
                    deadline = loop.time() + listen_timeout

                    while True:
                        remaining = deadline - loop.time()
                        if remaining <= 0:
                            break
                        try:
                            # Use short idle timeout once at least one router has been received
                            wait_t = min(remaining, 0.5 if routers_by_key else remaining)
                            raw_msg = await asyncio.wait_for(ws.recv(), timeout=wait_t)
                            msg = json.loads(raw_msg)
                        except asyncio.TimeoutError:
                            break

                        if not isinstance(msg, dict):
                            continue

                        # Handle legacy non-streaming response if a list/dict of routers is directly in result
                        if msg.get("id") == sub_id and msg.get("type") == "result":
                            if not msg.get("success"):
                                break
                            res_payload = msg.get("result")
                            if isinstance(res_payload, dict) and "routers" in res_payload:
                                for r in res_payload["routers"]:
                                    k = r.get("instance_name") or r.get("server") or str(len(routers_by_key))
                                    routers_by_key[k] = r
                                break
                            elif isinstance(res_payload, list):
                                for r in res_payload:
                                    k = r.get("instance_name") or r.get("server") or str(len(routers_by_key))
                                    routers_by_key[k] = r
                                break

                        # Handle streaming `event` messages from HA `thread/discover_routers`
                        elif msg.get("id") == sub_id and msg.get("type") == "event":
                            ev = msg.get("event") or {}
                            ev_type = ev.get("type")
                            key = ev.get("key") or str(len(routers_by_key))
                            data = ev.get("data")
                            if ev_type == "router_discovered" and isinstance(data, dict):
                                routers_by_key[key] = data
                            elif ev_type == "router_removed" and key in routers_by_key:
                                routers_by_key.pop(key, None)

                    return {"success": True, "result": {"routers": list(routers_by_key.values())}}
            except Exception as e:
                logger.debug("thread/discover_routers failed on %s: %s", ws_url, e)

        return {"result": {"routers": []}}

    async def get_device_registry(self) -> List[Dict[str, Any]]:
        """Fetch Home Assistant Device Registry."""
        res = await self.query_ha_websocket({"type": "config/device_registry/list"})
        if isinstance(res, dict) and res.get("success") and isinstance(res.get("result"), list):
            return res["result"]
        return []

    async def get_matter_diagnostics(self) -> Dict[str, Any]:
        """Fetch matter integration diagnostics if available."""
        return await self.query_ha_websocket({"type": "matter/diagnostics"})

    async def get_all_available_thread_networks(
        self,
        otbr_url: str = "http://core-openthread-border-router:8081",
        matter_nodes: Optional[List[Dict[str, Any]]] = None,
        mdns_info: Optional[Dict[str, Any]] = None,
        otbr_info: Optional[Dict[str, Any]] = None,
        datasets_res: Optional[Dict[str, Any]] = None,
        routers_res: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate and normalize 100% REAL Thread networks discovered across:
          1. Home Assistant Thread Datasets + decoded Operational Dataset TLVs (`thread/list_datasets` + `thread/get_dataset_tlv`)
          2. Home Assistant Border Router mDNS discovery stream (`thread/discover_routers`)
          3. Direct LAN mDNS `_meshcop._udp.local.` scan (`NetworkChecker.inspect_mdns_discovery`)
          4. OpenThread Border Router REST API (`NetworkChecker.inspect_otbr_rest_api`)
          5. Commissioned Matter-over-Thread nodes' live Cluster 0x0035 attributes (`extended_pan_id`, `thread_network_name`, `thread_channel`)
        """
        networks_map: Dict[str, Dict[str, Any]] = {}

        if datasets_res is None:
            datasets_res = await self.get_thread_datasets()
        if routers_res is None:
            routers_res = await self.get_thread_routers()
        if mdns_info is None:
            mdns_info = await NetworkChecker.inspect_mdns_discovery(scan_duration=1.5)
        if otbr_info is None:
            otbr_info = await NetworkChecker.inspect_otbr_rest_api(otbr_url=otbr_url)

        # 1. Process HA Datasets (with decoded TLV data)
        datasets_list = []
        if isinstance(datasets_res, dict):
            res_data = datasets_res.get("result", {})
            if isinstance(res_data, dict) and "datasets" in res_data:
                d_items = res_data["datasets"]
                datasets_list = d_items if isinstance(d_items, list) else list(d_items.values())
            elif isinstance(res_data, list):
                datasets_list = res_data
            elif isinstance(res_data, dict) and ("dataset_id" in res_data or "extended_pan_id" in res_data):
                datasets_list = [res_data]

        for ds in datasets_list:
            if not isinstance(ds, dict):
                continue
            ds_id = str(ds.get("dataset_id") or "")
            xpan = str(ds.get("extended_pan_id") or ds.get("ext_pan_id") or "").upper().replace(":", "").replace("0X", "")
            net_name = ds.get("network_name") or ds.get("name") or (f"Thread Mesh ({xpan[:8]})" if xpan else "HA Thread Dataset")
            is_pref = bool(ds.get("preferred", False))
            ch = ds.get("channel")
            pan_id = ds.get("pan_id")
            pan_str = f"0x{pan_id:04X}" if isinstance(pan_id, int) else str(pan_id or "")
            mesh_prefix = ds.get("mesh_local_prefix") or ""

            key = xpan if (xpan and xpan != "UNKNOWN") else (ds_id or net_name)
            networks_map[key] = {
                "id": key,
                "dataset_id": ds_id,
                "name": net_name,
                "extended_pan_id": xpan or key,
                "pan_id": pan_str,
                "channel": ch,
                "mesh_local_prefix": mesh_prefix,
                "preferred": is_pref,
                "source": "HA Thread Dataset" + (" ★ Preferred" if is_pref else ""),
                "routers": [],
                "router_details": [],
                "matter_node_count": 0,
            }

        # Helper to merge a discovered border router into networks_map
        def _merge_router(r_dict: Dict[str, Any], default_source: str):
            xpan = str(r_dict.get("extended_pan_id") or r_dict.get("ext_pan_id") or "").upper().replace(":", "").replace("0X", "")
            net_name = r_dict.get("network_name") or r_dict.get("instance_name") or (f"Thread Mesh ({xpan[:8]})" if xpan else "Discovered Thread Mesh")
            brand = r_dict.get("brand_name") or r_dict.get("vendor_name") or ""
            model = r_dict.get("model_name") or r_dict.get("model") or ""
            inst = r_dict.get("instance_name") or r_dict.get("server") or "Border Router"
            r_label = f"{brand} {model}".strip() if (brand or model) else inst
            ch = r_dict.get("channel")
            pan_id = r_dict.get("pan_id")
            pan_str = f"0x{pan_id:04X}" if isinstance(pan_id, int) else str(pan_id or "")
            addrs = r_dict.get("addresses") or (r_dict.get("ipv6_addresses", []) + r_dict.get("ipv4_addresses", []))

            key = xpan if (xpan and xpan != "UNKNOWN") else net_name
            if key not in networks_map:
                networks_map[key] = {
                    "id": key,
                    "dataset_id": "",
                    "name": net_name,
                    "extended_pan_id": xpan,
                    "pan_id": pan_str,
                    "channel": ch,
                    "mesh_local_prefix": r_dict.get("mesh_local_prefix") or "",
                    "preferred": False,
                    "source": default_source,
                    "routers": [r_label],
                    "router_details": [{
                        "name": r_label,
                        "server": r_dict.get("server"),
                        "ext_address": r_dict.get("ext_address") or r_dict.get("extended_address"),
                        "thread_version": r_dict.get("thread_version"),
                        "addresses": addrs,
                    }],
                    "matter_node_count": 0,
                }
            else:
                entry = networks_map[key]
                if r_label not in entry["routers"]:
                    entry["routers"].append(r_label)
                entry["router_details"].append({
                    "name": r_label,
                    "server": r_dict.get("server"),
                    "ext_address": r_dict.get("ext_address") or r_dict.get("extended_address"),
                    "thread_version": r_dict.get("thread_version"),
                    "addresses": addrs,
                })
                if not entry.get("channel") and ch:
                    entry["channel"] = ch
                if not entry.get("pan_id") and pan_str:
                    entry["pan_id"] = pan_str
                if not entry.get("mesh_local_prefix") and r_dict.get("mesh_local_prefix"):
                    entry["mesh_local_prefix"] = r_dict["mesh_local_prefix"]

        # 2. Merge HA discovered routers (`thread/discover_routers`)
        if isinstance(routers_res, dict):
            r_data = routers_res.get("result", {})
            r_list = r_data.get("routers", []) if isinstance(r_data, dict) else (r_data if isinstance(r_data, list) else [])
            for r in r_list:
                if isinstance(r, dict):
                    _merge_router(r, "HA Border Router Discovery")

        # 3. Merge direct mDNS `_meshcop._udp.local.` Border Routers
        if isinstance(mdns_info, dict):
            for mr in mdns_info.get("meshcop_border_routers", []):
                if isinstance(mr, dict):
                    _merge_router(mr, "Live mDNS (_meshcop._udp)")

        # 4. Merge OpenThread Border Router REST API state
        if isinstance(otbr_info, dict) and otbr_info.get("reachable"):
            otbr_xpan = otbr_info.get("extended_pan_id")
            if otbr_xpan:
                _merge_router(
                    {
                        "extended_pan_id": otbr_xpan,
                        "network_name": otbr_info.get("network_name"),
                        "brand_name": "Home Assistant",
                        "model_name": f"OTBR ({otbr_info.get('state', 'active')})",
                        "channel": otbr_info.get("channel"),
                        "pan_id": otbr_info.get("pan_id"),
                        "ext_address": otbr_info.get("ext_address"),
                        "mesh_local_prefix": otbr_info.get("mesh_local_prefix"),
                    },
                    "OpenThread Border Router REST API",
                )

        # 5. Merge live Thread networks reported by commissioned Matter nodes (Cluster 0x0035)
        if matter_nodes:
            for node in matter_nodes:
                if node.get("transport") != "thread":
                    continue
                n_xpan = node.get("extended_pan_id")
                n_name = node.get("thread_network_name")
                n_ch = node.get("thread_channel")
                n_pan = node.get("pan_id")
                n_prefix = node.get("mesh_local_prefix")

                if n_xpan:
                    if n_xpan not in networks_map:
                        networks_map[n_xpan] = {
                            "id": n_xpan,
                            "dataset_id": "",
                            "name": n_name or f"Thread Mesh ({n_xpan[:8]})",
                            "extended_pan_id": n_xpan,
                            "pan_id": n_pan or "",
                            "channel": n_ch,
                            "mesh_local_prefix": n_prefix or "",
                            "preferred": False,
                            "source": "Matter Node Cluster 0x0035",
                            "routers": [],
                            "router_details": [],
                            "matter_node_count": 1,
                        }
                    else:
                        networks_map[n_xpan]["matter_node_count"] = networks_map[n_xpan].get("matter_node_count", 0) + 1
                        if not networks_map[n_xpan].get("channel") and n_ch:
                            networks_map[n_xpan]["channel"] = n_ch
                        if not networks_map[n_xpan].get("pan_id") and n_pan:
                            networks_map[n_xpan]["pan_id"] = n_pan
                        if not networks_map[n_xpan].get("mesh_local_prefix") and n_prefix:
                            networks_map[n_xpan]["mesh_local_prefix"] = n_prefix

        # Sort so Preferred network is first, followed by networks with active border routers / nodes
        net_list = list(networks_map.values())
        net_list.sort(key=lambda x: (not x.get("preferred", False), -len(x.get("routers", [])), -x.get("matter_node_count", 0)))
        return net_list
