"""
Home Assistant & Supervisor Client for Matter & Thread diagnostics.
Interacts with Home Assistant Core, Supervisor, and WebSocket endpoints.
Supports both bridge mode and host_network mode (`ws://supervisor/core/websocket` and
`ws://172.30.32.2/core/websocket` with `Host: supervisor` header), streaming
`thread/discover_routers` subscriptions, and Thread Operational Dataset TLV decoding.
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


async def _ws_connect_with_host(ws_url: str, timeout: float = 6.0):
    """
    Connect to a WebSocket URL, automatically supplying `Host: supervisor` when connecting
    via the Supervisor bridge IP (`172.30.32.2`) in `host_network: true` mode.
    """
    needs_host_header = "172.30.32.2" in ws_url
    if needs_host_header:
        try:
            return await websockets.connect(
                ws_url,
                open_timeout=timeout,
                max_size=16 * 1024 * 1024,
                additional_headers={"Host": "supervisor"},
            )
        except TypeError:
            return await websockets.connect(
                ws_url,
                open_timeout=timeout,
                max_size=16 * 1024 * 1024,
                extra_headers={"Host": "supervisor"},
            )
    return await websockets.connect(ws_url, open_timeout=timeout, max_size=16 * 1024 * 1024)


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

    def _headers(self, for_ip_fallback: bool = False) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.supervisor_token:
            headers["Authorization"] = f"Bearer {self.supervisor_token}"
        if for_ip_fallback:
            headers["Host"] = "supervisor"
        return headers

    def _candidate_ws_urls(self) -> List[str]:
        candidate_urls = []
        if self._working_ws_url:
            candidate_urls.append(self._working_ws_url)
        # 1. Official Supervisor proxy hostname
        candidate_urls.append("ws://supervisor/core/websocket")
        # 2. Direct Supervisor IP on hassio bridge (with Host: supervisor header for host_network mode)
        candidate_urls.append("ws://172.30.32.2/core/websocket")
        # 3. Fallback derivations from ha_url
        ha_ws = self.ha_url.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
        candidate_urls.append(f"{ha_ws}/websocket")
        candidate_urls.append(f"{ha_ws}/api/websocket")
        candidate_urls.append("ws://homeassistant:8123/api/websocket")

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
                for base in [self.supervisor_url, "http://172.30.32.2"]:
                    try:
                        r = await client.get(
                            f"{base}{path}",
                            headers=self._headers(for_ip_fallback=("172.30.32.2" in base)),
                        )
                        if r.status_code == 200:
                            res[key] = r.json().get("data", {})
                            break
                    except Exception as e:
                        res[f"{key}_error"] = str(e)
            return res

    async def get_addon_info(self, addon_slug: str) -> Dict[str, Any]:
        """Fetch add-on details."""
        if not self.is_available:
            return {}
        async with httpx.AsyncClient(timeout=8.0) as client:
            for base in [self.supervisor_url, "http://172.30.32.2"]:
                try:
                    r = await client.get(
                        f"{base}/addons/{addon_slug}/info",
                        headers=self._headers(for_ip_fallback=("172.30.32.2" in base)),
                    )
                    if r.status_code == 200:
                        return r.json().get("data", {})
                except Exception as e:
                    logger.debug("Could not fetch addon info for %s from %s: %s", addon_slug, base, e)
        return {}

    async def get_addon_logs(self, addon_slug: str, lines: int = 150) -> str:
        """Fetch recent logs for a specific add-on."""
        if not self.is_available:
            return ""
        async with httpx.AsyncClient(timeout=8.0) as client:
            for base in [self.supervisor_url, "http://172.30.32.2"]:
                try:
                    r = await client.get(
                        f"{base}/addons/{addon_slug}/logs",
                        headers=self._headers(for_ip_fallback=("172.30.32.2" in base)),
                    )
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
            for base in [self.ha_url, "http://172.30.32.2/core"]:
                try:
                    r = await client.get(
                        f"{base}/api/states",
                        headers=self._headers(for_ip_fallback=("172.30.32.2" in base)),
                    )
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

    async def _get_all_ha_states(self) -> List[Dict[str, Any]]:
        """Fetch all Home Assistant states via REST API."""
        if not self.is_available:
            return []
        async with httpx.AsyncClient(timeout=6.0) as client:
            for base in [self.ha_url, "http://172.30.32.2/core"]:
                try:
                    r = await client.get(
                        f"{base}/api/states",
                        headers=self._headers(for_ip_fallback=("172.30.32.2" in base)),
                    )
                    if r.status_code == 200 and isinstance(r.json(), list):
                        return r.json()
                except Exception:
                    continue
        return []

    async def query_ha_websocket(self, command: Dict[str, Any], timeout: float = 8.0) -> Dict[str, Any]:
        """Send a single request/response command over HA WebSocket API."""
        if not self.is_available:
            return {"error": "No supervisor token"}

        last_err = None
        for ws_url in self._candidate_ws_urls():
            ws = None
            try:
                ws = await _ws_connect_with_host(ws_url, timeout=timeout)
                auth_req = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                if auth_req.get("type") != "auth_required":
                    await ws.close()
                    continue

                await ws.send(json.dumps({"type": "auth", "access_token": self.supervisor_token}))
                auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                if auth_res.get("type") != "auth_ok":
                    last_err = f"Auth failed on {ws_url}: {auth_res}"
                    await ws.close()
                    continue

                self._working_ws_url = ws_url

                msg_id = 1
                command_copy = dict(command)
                command_copy["id"] = msg_id
                await ws.send(json.dumps(command_copy))

                response = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                await ws.close()
                return response
            except Exception as e:
                last_err = str(e)
                logger.debug("Attempt to connect HA websocket at %s failed: %s", ws_url, e)
                if ws is not None:
                    try:
                        await ws.close()
                    except Exception:
                        pass

        logger.warning("All HA WebSocket candidate URLs failed (%s): %s", command.get("type"), last_err)
        return {"error": last_err or "All WebSocket candidate URLs failed"}

    async def get_thread_datasets(self) -> Dict[str, Any]:
        """
        Fetch all Thread datasets configured in Home Assistant (`thread/list_datasets`),
        and optionally enrich each dataset with decoded TLV (`thread/get_dataset_tlv`).
        """
        list_res = await self.query_ha_websocket({"type": "thread/list_datasets"})
        if not isinstance(list_res, dict) or not list_res.get("success"):
            fallback_res = await self.query_ha_websocket({"type": "thread/get_dataset"})
            if isinstance(fallback_res, dict) and fallback_res.get("success"):
                return fallback_res
            return list_res if isinstance(list_res, dict) else {"result": {"datasets": []}}

        res_data = list_res.get("result") or {}
        datasets = res_data.get("datasets", []) if isinstance(res_data, dict) else (res_data if isinstance(res_data, list) else [])

        # Enrich each dataset with decoded Operational Dataset TLV (channel, pan_id, mesh_local_prefix)
        for ds in datasets:
            if not isinstance(ds, dict):
                continue
            ds_id = ds.get("dataset_id")
            if not ds_id:
                continue
            try:
                tlv_res = await self.query_ha_websocket(
                    {"type": "thread/get_dataset_tlv", "dataset_id": ds_id},
                    timeout=3.0,
                )
                if isinstance(tlv_res, dict) and tlv_res.get("success") and isinstance(tlv_res.get("result"), dict):
                    tlv_hex = tlv_res["result"].get("tlv")
                    if tlv_hex:
                        decoded = parse_thread_dataset_tlv(tlv_hex)
                        for k, v in decoded.items():
                            if v is not None and not ds.get(k):
                                ds[k] = v
            except Exception as e:
                logger.debug("Optional TLV decode skipped for dataset %s: %s", ds_id, e)

        return {"success": True, "result": {"datasets": datasets}}

    async def get_thread_routers(self, listen_timeout: float = 1.8) -> Dict[str, Any]:
        """
        Discover live Thread Border Routers via Home Assistant's `thread/discover_routers`
        WebSocket subscription stream (or single response).
        """
        if not self.is_available:
            return {"result": {"routers": []}}

        for ws_url in self._candidate_ws_urls():
            ws = None
            try:
                ws = await _ws_connect_with_host(ws_url, timeout=6.0)
                auth_req = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                if auth_req.get("type") != "auth_required":
                    await ws.close()
                    continue
                await ws.send(json.dumps({"type": "auth", "access_token": self.supervisor_token}))
                auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                if auth_res.get("type") != "auth_ok":
                    await ws.close()
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
                        wait_t = min(remaining, 0.45 if routers_by_key else remaining)
                        raw_msg = await asyncio.wait_for(ws.recv(), timeout=wait_t)
                        msg = json.loads(raw_msg)
                    except asyncio.TimeoutError:
                        break
                    except Exception:
                        break

                    if not isinstance(msg, dict):
                        continue

                    if msg.get("id") == sub_id and msg.get("type") == "result":
                        if not msg.get("success"):
                            break
                        res_payload = msg.get("result")
                        if isinstance(res_payload, dict) and "routers" in res_payload:
                            for r in res_payload["routers"]:
                                if isinstance(r, dict):
                                    k = r.get("instance_name") or r.get("server") or str(len(routers_by_key))
                                    routers_by_key[k] = r
                            break
                        elif isinstance(res_payload, list):
                            for r in res_payload:
                                if isinstance(r, dict):
                                    k = r.get("instance_name") or r.get("server") or str(len(routers_by_key))
                                    routers_by_key[k] = r
                            break

                    elif msg.get("id") == sub_id and msg.get("type") == "event":
                        ev = msg.get("event") or {}
                        ev_type = ev.get("type")
                        key = ev.get("key") or str(len(routers_by_key))
                        data = ev.get("data")
                        if ev_type == "router_discovered" and isinstance(data, dict):
                            routers_by_key[key] = data
                        elif ev_type == "router_removed" and key in routers_by_key:
                            routers_by_key.pop(key, None)

                await ws.close()
                return {"success": True, "result": {"routers": list(routers_by_key.values())}}
            except Exception as e:
                logger.debug("thread/discover_routers failed on %s: %s", ws_url, e)
                if ws is not None:
                    try:
                        await ws.close()
                    except Exception:
                        pass

        return {"result": {"routers": []}}

    async def get_device_registry(self) -> List[Dict[str, Any]]:
        """Fetch Home Assistant Device Registry."""
        res = await self.query_ha_websocket({"type": "config/device_registry/list"})
        if isinstance(res, dict) and res.get("success") and isinstance(res.get("result"), list):
            return res["result"]
        return []

    async def get_area_registry(self) -> List[Dict[str, Any]]:
        """Fetch Home Assistant Area Registry (`config/area_registry/list`)."""
        res = await self.query_ha_websocket({"type": "config/area_registry/list"})
        if isinstance(res, dict) and res.get("success") and isinstance(res.get("result"), list):
            return res["result"]
        return []

    async def get_entity_registry(self) -> List[Dict[str, Any]]:
        """Fetch Home Assistant Entity Registry (`config/entity_registry/list`)."""
        res = await self.query_ha_websocket({"type": "config/entity_registry/list"})
        if isinstance(res, dict) and res.get("success") and isinstance(res.get("result"), list):
            return res["result"]
        return []

    @staticmethod
    def enrich_matter_nodes_with_ha_names(
        matter_nodes: List[Dict[str, Any]],
        device_registry: List[Dict[str, Any]],
        area_registry: Optional[List[Dict[str, Any]]] = None,
        entity_registry: Optional[List[Dict[str, Any]]] = None,
        ha_states: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Cross-reference commissioned Matter nodes (`node_id`, `serial_number`, `ext_address`)
        against Home Assistant's Device Registry, Area Registry, and Entity Registry so user-friendly
        names (e.g. 'Living Room Light'), Areas ('Living Room'), and Entity IDs ('light.living_room_light')
        are displayed across all tables, topology maps, purge prompts, and AI reports.
        """
        if not matter_nodes or not device_registry:
            return

        area_by_id: Dict[str, str] = {}
        for a in area_registry or []:
            if isinstance(a, dict) and a.get("area_id") and a.get("name"):
                area_by_id[str(a["area_id"])] = str(a["name"]).strip()

        state_friendly_by_eid: Dict[str, str] = {}
        for s in ha_states or []:
            if isinstance(s, dict) and s.get("entity_id"):
                fn = (s.get("attributes") or {}).get("friendly_name")
                if fn:
                    state_friendly_by_eid[str(s["entity_id"])] = str(fn).strip()

        entities_by_device_id: Dict[str, List[Dict[str, Any]]] = {}
        for ent in entity_registry or []:
            if isinstance(ent, dict) and ent.get("device_id") and not ent.get("disabled_by"):
                entities_by_device_id.setdefault(str(ent["device_id"]), []).append(ent)

        primary_domains = (
            "light.", "switch.", "lock.", "climate.", "cover.", "fan.",
            "media_player.", "vacuum.", "humidifier.", "water_heater.",
            "valve.", "siren.", "binary_sensor.", "sensor.", "event.",
        )

        def _score_entity(e: Dict[str, Any]) -> tuple:
            eid = str(e.get("entity_id") or "").lower()
            cat = e.get("entity_category")
            is_diag_or_cfg = 1 if cat in ("diagnostic", "config") else 0
            dom_rank = next((i for i, d in enumerate(primary_domains) if eid.startswith(d)), 99)
            has_user_name = 0 if e.get("name") else 1
            return (is_diag_or_cfg, dom_rank, has_user_name, eid)

        for node in matter_nodes:
            if not isinstance(node, dict) or node.get("node_id") is None:
                continue
            try:
                nid = int(node["node_id"])
            except (ValueError, TypeError):
                continue

            node_hex_token = f"-{nid:016X}-"
            node_hex_suffix = f"-{nid:016X}"
            node_serial = str(node.get("serial_number") or "").strip().upper()
            node_ext = str(node.get("ext_address") or "").strip().upper().replace(":", "")

            matched_devices: List[Dict[str, Any]] = []
            for d in device_registry:
                if not isinstance(d, dict):
                    continue
                idents = d.get("identifiers") or []
                conns = d.get("connections") or []
                matched = False
                for pair in idents:
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        domain = str(pair[0]).lower()
                        ident_val = str(pair[1]).upper()
                        if domain == "matter":
                            if node_hex_token in ident_val or ident_val.endswith(node_hex_suffix):
                                matched = True
                                break
                            if node_serial and len(node_serial) >= 5 and f"SERIAL_{node_serial}" in ident_val:
                                matched = True
                                break
                if not matched and node_ext and len(node_ext) >= 12:
                    for cpair in conns:
                        if isinstance(cpair, (list, tuple)) and len(cpair) >= 2:
                            cval = str(cpair[1]).upper().replace(":", "").replace("-", "")
                            if cval == node_ext:
                                matched = True
                                break
                if matched:
                    matched_devices.append(d)

            if not matched_devices:
                continue

            # Prefer the device entry that has a user-assigned name (`name_by_user`), or `-MatterNodeDevice`
            matched_devices.sort(
                key=lambda dev: (
                    0 if dev.get("name_by_user") else 1,
                    0 if any("MATTERNODEDEVICE" in str(p[1]).upper() for p in (dev.get("identifiers") or []) if isinstance(p, (list, tuple)) and len(p) >= 2) else 1,
                )
            )
            best_dev = matched_devices[0]
            dev_id = str(best_dev.get("id") or "")

            raw_model_name = node.get("hardware_model") or node.get("product_name") or f"Node {nid}"
            node["hardware_model"] = raw_model_name
            node["ha_device_id"] = dev_id

            # Resolve Area
            area_id = best_dev.get("area_id")
            dev_entities = entities_by_device_id.get(dev_id, [])
            dev_entities.sort(key=_score_entity)
            if not area_id and dev_entities:
                area_id = next((e.get("area_id") for e in dev_entities if e.get("area_id")), None)
            ha_area = area_by_id.get(str(area_id), "") if area_id else ""
            if ha_area:
                node["ha_area"] = ha_area

            # Resolve primary entity & user-friendly name
            primary_entity_id = dev_entities[0].get("entity_id") if dev_entities else None
            if primary_entity_id:
                node["ha_entity_id"] = primary_entity_id

            user_device_name = (best_dev.get("name_by_user") or "").strip()
            user_entity_name = ""
            if dev_entities:
                for e in dev_entities:
                    if e.get("name") and e.get("entity_category") not in ("diagnostic", "config"):
                        user_entity_name = str(e["name"]).strip()
                        break
                if not user_entity_name and primary_entity_id and primary_entity_id in state_friendly_by_eid:
                    cand_fn = state_friendly_by_eid[primary_entity_id]
                    if cand_fn and cand_fn.lower() != raw_model_name.lower():
                        user_entity_name = cand_fn

            default_ha_name = (best_dev.get("name") or "").strip()
            chosen_name = user_device_name or user_entity_name or default_ha_name
            if chosen_name:
                node["ha_name"] = chosen_name
                node["product_name"] = chosen_name

    async def remove_matter_device_from_ha_registry(self, node_id: int) -> Dict[str, Any]:
        """
        Ensure any orphaned Home Assistant Device Registry entries for a purged Matter node_id
        are also cleaned up from Home Assistant Core.
        """
        if not self.is_available:
            return {"removed_devices": 0}
        try:
            devices = await self.get_device_registry()
            node_hex_token = f"-{int(node_id):016X}-"
            removed_ids: List[str] = []
            for d in devices:
                if not isinstance(d, dict):
                    continue
                dev_id = d.get("id")
                idents = d.get("identifiers") or []
                is_matching_matter_node = False
                for pair in idents:
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        domain = str(pair[0]).lower()
                        ident_val = str(pair[1]).upper()
                        if domain == "matter" and node_hex_token in ident_val:
                            is_matching_matter_node = True
                            break
                if is_matching_matter_node and dev_id:
                    for entry_id in d.get("config_entries") or []:
                        await self.query_ha_websocket({
                            "type": "config/device_registry/remove_config_entry",
                            "device_id": dev_id,
                            "config_entry_id": entry_id,
                        })
                    removed_ids.append(dev_id)
            return {"removed_devices": len(removed_ids), "device_ids": removed_ids}
        except Exception as e:
            logger.debug("HA device registry cleanup for node %s skipped: %s", node_id, e)
            return {"removed_devices": 0, "error": str(e)}

    async def get_matter_diagnostics(self) -> Dict[str, Any]:
        """Fetch matter integration diagnostics if available."""
        return await self.query_ha_websocket({"type": "matter/diagnostics"})

    async def get_zbt1_channel_status(
        self,
        otbr_url: str = "http://core-openthread-border-router:8081",
    ) -> Dict[str, Any]:
        """
        Retrieve live status of Home Assistant Connect ZBT-1 / SkyConnect / OTBR Thread radio:
        hardware identity, current channel, active dataset, OTBR state, and comprehensive 2.4 GHz
        RF spectrum matrix across channels 11 to 26.
        """
        raw_probe = await asyncio.gather(
            NetworkChecker.inspect_otbr_rest_api(otbr_url=otbr_url),
            self.get_device_registry(),
            self.get_addon_info("core_openthread_border_router"),
            self.get_thread_datasets(),
            self.query_ha_websocket({"type": "otbr/info"}),
            return_exceptions=True,
        )

        otbr_info = raw_probe[0] if isinstance(raw_probe[0], dict) else {"reachable": False}
        device_registry = raw_probe[1] if isinstance(raw_probe[1], list) else []
        otbr_addon_info = raw_probe[2] if isinstance(raw_probe[2], dict) else {}
        datasets_res = raw_probe[3] if isinstance(raw_probe[3], dict) else {}
        otbr_ws_info = raw_probe[4] if isinstance(raw_probe[4], dict) and isinstance(raw_probe[4].get("result"), dict) else {}
        ws_router = next(iter(otbr_ws_info.get("result", {}).values()), {}) if otbr_ws_info.get("result") else {}

        # 1. Identify ZBT-1 / SkyConnect hardware from device registry or add-on
        hardware_device = None
        for dev in device_registry:
            if not isinstance(dev, dict):
                continue
            combined = f"{dev.get('manufacturer', '')} {dev.get('model', '')} {dev.get('name', '')}".lower()
            if any(k in combined for k in ("zbt-1", "skyconnect", "nabu casa", "connect zbt-1")):
                hardware_device = dev
                break

        hardware_name = "Home Assistant Connect ZBT-1"
        hardware_model = "Connect ZBT-1 (Silicon Labs EFR32MG21)"
        hardware_manufacturer = "Nabu Casa"
        if hardware_device:
            hardware_name = hardware_device.get("name_by_user") or hardware_device.get("name") or hardware_name
            hardware_model = hardware_device.get("model") or hardware_model
            hardware_manufacturer = hardware_device.get("manufacturer") or hardware_manufacturer
        elif otbr_addon_info.get("name"):
            hardware_name = otbr_addon_info.get("name")

        # 2. Extract current channel, XPAN, and OTBR state
        current_channel = otbr_info.get("channel") or ws_router.get("channel")
        active_xpan = otbr_info.get("extended_pan_id") or ws_router.get("extended_pan_id")
        network_name = otbr_info.get("network_name")
        pan_id = otbr_info.get("pan_id")
        otbr_state = otbr_info.get("state")
        mesh_prefix = otbr_info.get("mesh_local_prefix")
        ext_address = otbr_info.get("ext_address") or ws_router.get("extended_address")

        # Fallback to preferred dataset if OTBR REST API was briefly initializing
        datasets_list = (datasets_res.get("result") or {}).get("datasets", []) if isinstance(datasets_res, dict) else []
        pref_ds = next((d for d in datasets_list if isinstance(d, dict) and d.get("preferred")), None)
        if not pref_ds and datasets_list:
            pref_ds = datasets_list[0] if isinstance(datasets_list[0], dict) else None

        if not current_channel and pref_ds:
            current_channel = pref_ds.get("channel")
        if not active_xpan and pref_ds:
            active_xpan = pref_ds.get("extended_pan_id")
        if not network_name and pref_ds:
            network_name = pref_ds.get("network_name")
        if not pan_id and pref_ds:
            pan_id = pref_ds.get("pan_id")
        if not ext_address and pref_ds and pref_ds.get("preferred_extended_address"):
            ext_address = pref_ds.get("preferred_extended_address")

        # 3. Build channels 11 to 26 matrix
        from thread_analyzer import THREAD_WIFI_OVERLAP_MAP
        channels_matrix = []
        for ch in range(11, 27):
            freq = 2405 + (ch - 11) * 5
            ov = THREAD_WIFI_OVERLAP_MAP.get(ch, {})
            wifi_ch = ov.get("wifi_channel")
            sev = ov.get("severity", "UNKNOWN")
            is_rec = ch in (25, 26)
            is_cur = current_channel is not None and int(current_channel) == ch

            rec_badge = "Best (Cleanest)" if ch == 26 else ("Recommended" if ch == 25 else ("Guard Band" if ch in (15, 20) else f"Wi-Fi Ch {wifi_ch} Overlap"))

            channels_matrix.append({
                "channel": ch,
                "frequency_mhz": freq,
                "wifi_overlap_channel": wifi_ch,
                "severity": sev,
                "is_current": is_cur,
                "is_recommended": is_rec,
                "recommendation_badge": rec_badge,
                "description": ov.get("interference", ""),
            })

        return {
            "hardware": {
                "name": hardware_name,
                "model": hardware_model,
                "manufacturer": hardware_manufacturer,
                "detected": bool(hardware_device or otbr_info.get("reachable") or ws_router),
                "addon_version": otbr_addon_info.get("version"),
                "addon_state": otbr_addon_info.get("state"),
            },
            "otbr": {
                "reachable": bool(otbr_info.get("reachable") or ws_router),
                "url": ws_router.get("url") or otbr_info.get("otbr_url", otbr_url),
                "state": otbr_state or ("leader" if ws_router else "unknown"),
                "network_name": network_name or "Home Assistant Thread Network",
                "extended_pan_id": active_xpan,
                "pan_id": pan_id,
                "mesh_local_prefix": mesh_prefix,
                "ext_address": ext_address,
                "rloc16": otbr_info.get("rloc16"),
            },
            "current_channel": current_channel,
            "channels_matrix": channels_matrix,
        }

    async def set_otbr_channel(
        self,
        channel: int,
        delay_seconds: int = 30,
        otbr_url: str = "http://core-openthread-border-router:8081",
    ) -> Dict[str, Any]:
        """
        Change the Thread network operating channel on Home Assistant Connect ZBT-1 / OTBR.
        Uses Home Assistant WebSocket API `otbr/set_channel` and direct OpenThread Border Router
        REST API (:8081) for reliable execution.
        """
        if channel < 11 or channel > 26:
            return {"success": False, "error": f"Invalid Thread channel {channel}. Valid channels are 11 to 26."}

        # Step 0: Record previous channel and retrieve current ZBT-1 status
        status_before = await self.get_zbt1_channel_status(otbr_url)
        prev_channel = status_before.get("current_channel")
        active_xpan = (status_before.get("otbr") or {}).get("extended_pan_id")

        # Step 1: Discover OTBR extended_address from Home Assistant WebSocket API
        # Home Assistant Core's otbr/set_channel command schema requires:
        # {"type": "otbr/set_channel", "channel": int, "extended_address": str}
        ha_ws_success = False
        ha_ws_error = None
        target_ext_addrs: List[str] = []

        if self.is_available:
            try:
                # 1a. Query otbr/info to retrieve all loaded OTBR instances and their extended_address
                otbr_info_res = await self.query_ha_websocket({"type": "otbr/info"}, timeout=8.0)
                if isinstance(otbr_info_res, dict) and isinstance(otbr_info_res.get("result"), dict):
                    for ext_addr, r_info in otbr_info_res["result"].items():
                        if ext_addr and isinstance(ext_addr, str):
                            clean_addr = ext_addr.lower().replace(":", "").strip()
                            if clean_addr not in target_ext_addrs:
                                if isinstance(r_info, dict) and (
                                    r_info.get("channel") == prev_channel or
                                    (active_xpan and str(r_info.get("extended_pan_id", "")).lower() == str(active_xpan).lower())
                                ):
                                    target_ext_addrs.insert(0, clean_addr)
                                else:
                                    target_ext_addrs.append(clean_addr)
            except Exception as e:
                logger.debug("Failed querying otbr/info: %s", e)

            # 1b. Fallback to status_before ext_address
            status_ext = (status_before.get("otbr") or {}).get("ext_address")
            if status_ext:
                clean_addr = str(status_ext).lower().replace(":", "").strip()
                if clean_addr not in target_ext_addrs:
                    target_ext_addrs.append(clean_addr)

            # 1c. Fallback to thread/list_datasets for preferred_extended_address
            if not target_ext_addrs:
                try:
                    ds_res = await self.get_thread_datasets()
                    datasets = (ds_res.get("result") or {}).get("datasets", []) if isinstance(ds_res, dict) else []
                    for d in datasets:
                        if isinstance(d, dict) and d.get("preferred_extended_address"):
                            clean_addr = str(d["preferred_extended_address"]).lower().replace(":", "").strip()
                            if clean_addr not in target_ext_addrs:
                                target_ext_addrs.append(clean_addr)
                except Exception as e:
                    logger.debug("Failed extracting preferred_extended_address from datasets: %s", e)

            # 1d. Execute otbr/set_channel
            if target_ext_addrs:
                for ext_addr in target_ext_addrs:
                    cmd = {
                        "type": "otbr/set_channel",
                        "channel": int(channel),
                        "extended_address": ext_addr,
                    }
                    logger.info("Executing HA WebSocket command with extended_address: %s", cmd)
                    ws_res = await self.query_ha_websocket(cmd, timeout=15.0)
                    logger.info("HA WebSocket otbr/set_channel response: %s", ws_res)

                    if isinstance(ws_res, dict) and ws_res.get("success"):
                        ha_ws_success = True
                        break
                    elif isinstance(ws_res, dict) and "error" in ws_res:
                        err_obj = ws_res["error"]
                        ha_ws_error = err_obj.get("message", err_obj.get("code", str(err_obj))) if isinstance(err_obj, dict) else str(err_obj)
                        # If schema failed with extra keys (legacy HA Core schema), retry without extended_address
                        if "extra keys not allowed" in str(ha_ws_error):
                            legacy_cmd = {"type": "otbr/set_channel", "channel": int(channel)}
                            ws_legacy = await self.query_ha_websocket(legacy_cmd, timeout=15.0)
                            if isinstance(ws_legacy, dict) and ws_legacy.get("success"):
                                ha_ws_success = True
                                break
            else:
                # If no extended address could be determined anywhere, try legacy command without extended_address
                legacy_cmd = {"type": "otbr/set_channel", "channel": int(channel)}
                logger.info("Executing legacy HA WebSocket command without extended_address: %s", legacy_cmd)
                ws_res = await self.query_ha_websocket(legacy_cmd, timeout=15.0)
                logger.info("HA WebSocket otbr/set_channel response: %s", ws_res)

                if isinstance(ws_res, dict) and ws_res.get("success"):
                    ha_ws_success = True
                elif isinstance(ws_res, dict) and "error" in ws_res:
                    err_obj = ws_res["error"]
                    ha_ws_error = err_obj.get("message", err_obj.get("code", str(err_obj))) if isinstance(err_obj, dict) else str(err_obj)

        # If HA WebSocket succeeded, Home Assistant Core has directly updated the channel
        # on the OTBR add-on. We refresh datasets and return immediately.
        if ha_ws_success:
            try:
                await self.get_thread_datasets()
            except Exception:
                pass

            return {
                "success": True,
                "channel": int(channel),
                "previous_channel": prev_channel,
                "delay_seconds": int(delay_seconds),
                "method": "ha_websocket",
                "mode": "pending_migration" if delay_seconds > 0 else "immediate_switch",
                "message": (
                    f"Successfully changed Thread channel to Channel {channel} on Home Assistant Connect ZBT-1 via Home Assistant OTBR!"
                ),
            }

        # Step 2: Fallback to direct OpenThread Border Router REST API if HA WebSocket was unavailable or failed
        logger.info("HA WebSocket failed or unavailable (error=%s), trying direct OTBR REST API...", ha_ws_error)
        otbr_direct_res = await NetworkChecker.set_otbr_channel_direct(
            channel=int(channel),
            delay_sec=int(delay_seconds),
            otbr_url=otbr_url,
        )

        if otbr_direct_res.get("success"):
            try:
                await self.get_thread_datasets()
            except Exception:
                pass

            mode_str = otbr_direct_res.get("mode", "pending_migration" if delay_seconds > 0 else "immediate_switch")
            return {
                "success": True,
                "channel": int(channel),
                "previous_channel": prev_channel,
                "delay_seconds": int(delay_seconds),
                "method": "otbr_rest_api",
                "mode": mode_str,
                "message": (
                    f"Successfully changed Thread channel to Channel {channel} on OpenThread Border Router REST API! "
                    + (f"Thread mesh will migrate in {delay_seconds} seconds via Pending Operational Dataset." if delay_seconds > 0 else "Active channel updated immediately.")
                ),
            }

        # Step 3: If both failed, construct a clear and descriptive error message
        err_msg_parts = []
        if ha_ws_error:
            err_msg_parts.append(f"Home Assistant WebSocket: {ha_ws_error}")
        if otbr_direct_res.get("error"):
            err_msg_parts.append(f"OTBR REST API: {otbr_direct_res['error']}")

        err_msg = " | ".join(err_msg_parts) if err_msg_parts else "Could not change channel via HA WebSocket or OTBR REST API."
        return {
            "success": False,
            "error": err_msg,
            "previous_channel": prev_channel,
            "requested_channel": channel,
            "ha_ws_error": ha_ws_error,
            "otbr_direct_error": otbr_direct_res.get("error"),
        }

    async def get_all_available_thread_networks(
        self,
        otbr_url: str = "http://core-openthread-border-router:8081",
        matter_nodes: Optional[List[Dict[str, Any]]] = None,
        mdns_info: Optional[Dict[str, Any]] = None,
        otbr_info: Optional[Dict[str, Any]] = None,
        datasets_res: Optional[Dict[str, Any]] = None,
        routers_res: Optional[Dict[str, Any]] = None,
        device_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate and normalize all Thread networks available across:
          1. Home Assistant Thread Datasets + decoded Operational Dataset TLVs (`thread/list_datasets` + `thread/get_dataset_tlv`)
          2. Home Assistant Border Router mDNS discovery stream (`thread/discover_routers`)
          3. Direct LAN mDNS `_meshcop._udp.local.` scan (pure-Python UDP DNS-SD + Zeroconf)
          4. OpenThread Border Router REST API (`:8081`)
          5. Commissioned Matter-over-Thread nodes' live Cluster 0x0035 attributes (`extended_pan_id`, `thread_network_name`, `thread_channel`)
          6. Home Assistant Device Registry & Entity States (ensuring registered Google Nest Wifi Pro, Apple TV/HomePod, and SkyConnect/ZBT-1 hardware is always selectable even if mDNS multicast is filtered)
        """
        networks_map: Dict[str, Dict[str, Any]] = {}

        # Fetch any missing inputs safely
        if datasets_res is None:
            try:
                datasets_res = await self.get_thread_datasets()
            except Exception as e:
                logger.warning("Error fetching Thread datasets: %s", e)
                datasets_res = {}

        if routers_res is None:
            try:
                routers_res = await self.get_thread_routers()
            except Exception as e:
                logger.warning("Error discovering Thread routers via HA: %s", e)
                routers_res = {}

        if mdns_info is None:
            try:
                mdns_info = await NetworkChecker.inspect_mdns_discovery(scan_duration=1.5)
            except Exception as e:
                logger.warning("Error in mDNS discovery: %s", e)
                mdns_info = {}

        if otbr_info is None:
            try:
                otbr_info = await NetworkChecker.inspect_otbr_rest_api(otbr_url=otbr_url)
            except Exception as e:
                logger.warning("Error querying OTBR REST API: %s", e)
                otbr_info = {}

        # 1. Process HA Datasets (with decoded TLV data)
        try:
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
                net_name = ds.get("network_name") or ds.get("name") or (f"Thread Mesh ({xpan[:8]})" if xpan else "Home Assistant Thread Network")
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
                    "source": "Home Assistant Dataset" + (" ★ Preferred" if is_pref else ""),
                    "routers": [],
                    "router_details": [],
                    "matter_node_count": 0,
                }
        except Exception as e:
            logger.warning("Error processing Thread datasets: %s", e)

        # Helper to merge a discovered border router into networks_map without duplicating routers or creating UNKNOWN shadow networks
        def _norm_ip(ip_s: str) -> str:
            return str(ip_s or "").split("/")[0].split("%")[0].strip().lower()

        def _merge_router(r_dict: Dict[str, Any], default_source: str):
            xpan = str(r_dict.get("extended_pan_id") or r_dict.get("ext_pan_id") or "").upper().replace(":", "").replace("0X", "")
            net_name = r_dict.get("network_name") or r_dict.get("instance_name") or r_dict.get("name") or (f"Thread Mesh ({xpan[:8]})" if xpan else "Thread Mesh")
            brand = r_dict.get("brand_name") or r_dict.get("vendor_name") or ""
            model = r_dict.get("model_name") or r_dict.get("model") or ""
            inst = str(r_dict.get("instance_name") or r_dict.get("name") or r_dict.get("server") or "Border Router").strip()
            r_label = inst if inst and inst != "Border Router" else (f"{brand} {model}".strip() or "Border Router")
            ch = r_dict.get("channel")
            pan_id = r_dict.get("pan_id")
            pan_str = f"0x{pan_id:04X}" if isinstance(pan_id, int) else str(pan_id or "")
            addrs = r_dict.get("addresses") or (r_dict.get("ipv6_addresses", []) + r_dict.get("ipv4_addresses", []))
            ext_addr = str(r_dict.get("ext_address") or r_dict.get("extended_address") or "").upper().replace(":", "")
            cand_ips = {_norm_ip(a) for a in addrs if _norm_ip(a)}
            inst_lower = inst.lower()

            # If xpan is UNKNOWN/empty, check if this router already belongs to an existing network in networks_map
            if not xpan or xpan == "UNKNOWN":
                for existing_net in networks_map.values():
                    for rd in existing_net.get("router_details", []):
                        rd_ips = {_norm_ip(a) for a in (rd.get("addresses") or []) if _norm_ip(a)}
                        rd_name_lower = str(rd.get("name") or "").lower()
                        rd_inst_lower = str(rd.get("instance_name") or "").lower()
                        if (
                            (inst_lower and (inst_lower == rd_name_lower or inst_lower == rd_inst_lower))
                            or (ext_addr and rd.get("ext_address") == ext_addr)
                            or (cand_ips and rd_ips and (cand_ips & rd_ips))
                        ):
                            for a in addrs:
                                if a not in rd["addresses"]:
                                    rd["addresses"].append(a)
                            return
                # If we already have valid Thread networks with real XPANs, don't pollute dropdown with an UNKNOWN partial mDNS record
                if any(k and k != "UNKNOWN" for k in networks_map.keys()):
                    return

            key = xpan if (xpan and xpan != "UNKNOWN") else net_name
            r_detail = {
                "name": r_label,
                "instance_name": inst,
                "server": r_dict.get("server"),
                "ext_address": ext_addr or None,
                "thread_version": r_dict.get("thread_version"),
                "addresses": list(addrs),
            }

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
                    "router_details": [r_detail],
                    "matter_node_count": 0,
                }
            else:
                entry = networks_map[key]
                # Deduplicate router inside entry["router_details"]
                dup_rd = None
                for rd in entry["router_details"]:
                    rd_ips = {_norm_ip(a) for a in (rd.get("addresses") or []) if _norm_ip(a)}
                    rd_name_lower = str(rd.get("name") or "").lower()
                    rd_inst_lower = str(rd.get("instance_name") or "").lower()
                    if (
                        (inst_lower and (inst_lower == rd_name_lower or inst_lower == rd_inst_lower))
                        or (r_label.lower() == rd_name_lower)
                        or (ext_addr and rd.get("ext_address") and ext_addr == rd.get("ext_address"))
                        or (cand_ips and rd_ips and (cand_ips & rd_ips))
                    ):
                        dup_rd = rd
                        break
                if dup_rd is not None:
                    for a in addrs:
                        if a not in dup_rd["addresses"]:
                            dup_rd["addresses"].append(a)
                    if not dup_rd.get("ext_address") and ext_addr:
                        dup_rd["ext_address"] = ext_addr
                    if not dup_rd.get("thread_version") and r_dict.get("thread_version"):
                        dup_rd["thread_version"] = r_dict.get("thread_version")
                else:
                    if r_label not in entry["routers"]:
                        entry["routers"].append(r_label)
                    entry["router_details"].append(r_detail)

                if not entry.get("channel") and ch:
                    entry["channel"] = ch
                if not entry.get("pan_id") and pan_str:
                    entry["pan_id"] = pan_str
                if not entry.get("mesh_local_prefix") and r_dict.get("mesh_local_prefix"):
                    entry["mesh_local_prefix"] = r_dict["mesh_local_prefix"]

        # 2. Merge HA discovered routers (`thread/discover_routers`)
        try:
            if isinstance(routers_res, dict):
                r_data = routers_res.get("result", {})
                r_list = r_data.get("routers", []) if isinstance(r_data, dict) else (r_data if isinstance(r_data, list) else [])
                for r in r_list:
                    if isinstance(r, dict):
                        _merge_router(r, "HA Border Router Discovery")
        except Exception as e:
            logger.warning("Error merging HA routers: %s", e)

        # 3. Merge direct mDNS `_meshcop._udp.local.` Border Routers
        try:
            if isinstance(mdns_info, dict):
                for mr in mdns_info.get("meshcop_border_routers", []):
                    if isinstance(mr, dict):
                        _merge_router(mr, "Live mDNS (_meshcop._udp)")
        except Exception as e:
            logger.warning("Error merging mDNS routers: %s", e)

        # 4. Merge OpenThread Border Router REST API state
        try:
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
        except Exception as e:
            logger.warning("Error merging OTBR info: %s", e)

        # 5. Merge live Thread networks reported by commissioned Matter nodes (Cluster 0x0035)
        try:
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
        except Exception as e:
            logger.warning("Error merging Matter node networks: %s", e)

        # 6. Fallback: Only check Home Assistant Device Registry and Entity States if NO live Thread datasets or mDNS routers were found
        if not networks_map:
            try:
                if device_registry is None:
                    device_registry = await self.get_device_registry()
                for d in device_registry or []:
                    if not isinstance(d, dict):
                        continue
                    m_str = f"{d.get('manufacturer', '')} {d.get('model', '')} {d.get('name', '')}".lower()
                    if "wifi pro" in m_str or ("nest" in m_str and ("router" in m_str or "point" in m_str or "hub" in m_str)):
                        name = d.get("name_by_user") or d.get("name") or "Google Nest Wifi Pro"
                        networks_map["GOOGLE_NEST_MESH"] = {
                            "id": "GOOGLE_NEST_MESH",
                            "dataset_id": "",
                            "name": f"Google Nest Thread Mesh ({name})",
                            "extended_pan_id": "NEST_TBR_DETECTED",
                            "pan_id": "",
                            "channel": None,
                            "mesh_local_prefix": "",
                            "preferred": False,
                            "source": "HA Device Registry (Nest Border Router)",
                            "routers": [name],
                            "router_details": [{"name": name, "server": d.get("id"), "addresses": []}],
                            "matter_node_count": 0,
                        }
                    elif "apple tv" in m_str or "homepod" in m_str:
                        name = d.get("name_by_user") or d.get("name") or "Apple TV / HomePod"
                        networks_map["APPLE_THREAD_MESH"] = {
                            "id": "APPLE_THREAD_MESH",
                            "dataset_id": "",
                            "name": f"Apple Thread Mesh ({name})",
                            "extended_pan_id": "APPLE_TBR_DETECTED",
                            "pan_id": "",
                            "channel": None,
                            "mesh_local_prefix": "",
                            "preferred": False,
                            "source": "HA Device Registry (Apple Border Router)",
                            "routers": [name],
                            "router_details": [{"name": name, "server": d.get("id"), "addresses": []}],
                            "matter_node_count": 0,
                        }
            except Exception as e:
                logger.debug("Error checking device registry for Thread hardware: %s", e)

            try:
                states = await self._get_all_ha_states()
                for s in states:
                    eid = s.get("entity_id", "").lower()
                    attrs = s.get("attributes", {})
                    fname = attrs.get("friendly_name", "")
                    combined = f"{eid} {fname} {attrs}".lower()

                    if "wifi pro" in combined or ("nest" in combined and ("router" in combined or "point" in combined or "hub" in combined)):
                        r_name = fname or "Google Nest Wifi Pro"
                        if "GOOGLE_NEST_MESH" not in networks_map:
                            networks_map["GOOGLE_NEST_MESH"] = {
                                "id": "GOOGLE_NEST_MESH",
                                "dataset_id": "",
                                "name": f"Google Nest Thread Mesh ({r_name})",
                                "extended_pan_id": "NEST_TBR_DETECTED",
                                "pan_id": "",
                                "channel": None,
                                "mesh_local_prefix": "",
                                "preferred": False,
                                "source": "HA Entity States (Nest Border Router)",
                                "routers": [r_name],
                                "router_details": [{"name": r_name, "server": eid, "addresses": []}],
                                "matter_node_count": 0,
                            }
                    elif "apple tv" in combined or "homepod" in combined:
                        r_name = fname or "Apple TV / HomePod"
                        if "APPLE_THREAD_MESH" not in networks_map:
                            networks_map["APPLE_THREAD_MESH"] = {
                                "id": "APPLE_THREAD_MESH",
                                "dataset_id": "",
                                "name": f"Apple Thread Mesh ({r_name})",
                                "extended_pan_id": "APPLE_TBR_DETECTED",
                                "pan_id": "",
                                "channel": None,
                                "mesh_local_prefix": "",
                                "preferred": False,
                                "source": "HA Entity States (Apple Border Router)",
                                "routers": [r_name],
                                "router_details": [{"name": r_name, "server": eid, "addresses": []}],
                                "matter_node_count": 0,
                            }
            except Exception as e:
                logger.debug("Error checking HA states for Thread hardware: %s", e)

        net_list = list(networks_map.values())
        net_list.sort(key=lambda x: (not x.get("preferred", False), -len(x.get("routers", [])), -x.get("matter_node_count", 0)))
        return net_list
