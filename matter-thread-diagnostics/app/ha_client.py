"""
Home Assistant & Supervisor Client for Matter & Thread diagnostics.
Interacts with Home Assistant Core, Supervisor, and WebSocket endpoints.
"""
import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
import httpx
import websockets

logger = logging.getLogger("matter_thread_ai.ha_client")


class HAClient:
    def __init__(self, supervisor_token: Optional[str] = None, ha_url: str = "http://supervisor/core", supervisor_url: str = "http://supervisor"):
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

    async def get_supervisor_info(self) -> Dict[str, Any]:
        """Fetch supervisor and host information (HAOS on Green)."""
        if not self.is_available:
            return {"status": "offline", "reason": "No SUPERVISOR_TOKEN (running outside HAOS)"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            res: Dict[str, Any] = {}
            try:
                r = await client.get(f"{self.supervisor_url}/info", headers=self._headers())
                if r.status_code == 200:
                    res["supervisor"] = r.json().get("data", {})
            except Exception as e:
                res["supervisor_error"] = str(e)

            try:
                r = await client.get(f"{self.supervisor_url}/host/info", headers=self._headers())
                if r.status_code == 200:
                    res["host"] = r.json().get("data", {})
            except Exception as e:
                res["host_error"] = str(e)

            try:
                r = await client.get(f"{self.supervisor_url}/network/info", headers=self._headers())
                if r.status_code == 200:
                    res["network"] = r.json().get("data", {})
            except Exception as e:
                res["network_error"] = str(e)

            return res

    async def get_addon_info(self, addon_slug: str) -> Dict[str, Any]:
        """Fetch add-on details (e.g. core_matter_server or core_openthread_border_router)."""
        if not self.is_available:
            return {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.get(f"{self.supervisor_url}/addons/{addon_slug}/info", headers=self._headers())
                if r.status_code == 200:
                    return r.json().get("data", {})
            except Exception as e:
                logger.debug("Could not fetch addon info for %s: %s", addon_slug, e)
        return {}

    async def get_addon_logs(self, addon_slug: str, lines: int = 200) -> str:
        """Fetch recent logs for a specific add-on."""
        if not self.is_available:
            return ""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.get(f"{self.supervisor_url}/addons/{addon_slug}/logs", headers=self._headers())
                if r.status_code == 200:
                    text = r.text
                    lines_list = text.strip().split("\n")
                    return "\n".join(lines_list[-lines:])
            except Exception as e:
                logger.debug("Could not fetch addon logs for %s: %s", addon_slug, e)
        return ""

    async def get_matter_nodes_via_ha(self) -> List[Dict[str, Any]]:
        """Fetch Matter entities and device states from Home Assistant Core."""
        if not self.is_available:
            return []
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.get(f"{self.ha_url}/api/states", headers=self._headers())
                if r.status_code == 200:
                    states = r.json()
                    matter_entities = [
                        s for s in states
                        if "matter" in s.get("entity_id", "") or "thread" in s.get("entity_id", "") or s.get("attributes", {}).get("integration") == "matter"
                    ]
                    return matter_entities
            except Exception as e:
                logger.error("Failed to query HA states: %s", e)
        return []

    async def query_ha_websocket(self, command: Dict[str, Any], timeout: float = 8.0) -> Dict[str, Any]:
        """Send command over HA WebSocket API with candidate URL fallback and response capture."""
        if not self.is_available:
            return {"error": "No supervisor token"}

        candidate_urls = []
        if self._working_ws_url:
            candidate_urls.append(self._working_ws_url)

        # 1. Primary official Supervisor proxy WebSocket endpoint:
        candidate_urls.append("ws://supervisor/core/websocket")
        # 2. Direct core endpoint inside Docker network:
        candidate_urls.append("ws://homeassistant:8123/api/websocket")
        # 3. Fallback derivations from ha_url:
        ha_ws = self.ha_url.replace("http://", "ws://").replace("https://", "wss://").rstrip('/')
        candidate_urls.append(f"{ha_ws}/websocket")
        candidate_urls.append(f"{ha_ws}/api/websocket")

        # Deduplicate while preserving order
        deduped_urls = []
        seen = set()
        for u in candidate_urls:
            if u not in seen:
                seen.add(u)
                deduped_urls.append(u)

        last_err = None
        for ws_url in deduped_urls:
            try:
                async with websockets.connect(ws_url, open_timeout=timeout) as ws:
                    # 1. Receive auth required
                    auth_req = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                    if auth_req.get("type") != "auth_required":
                        continue

                    # 2. Authenticate
                    await ws.send(json.dumps({
                        "type": "auth",
                        "access_token": self.supervisor_token
                    }))
                    auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                    if auth_res.get("type") != "auth_ok":
                        last_err = f"Auth failed on {ws_url}: {auth_res}"
                        continue

                    # Remember working URL for speed
                    self._working_ws_url = ws_url

                    # 3. Send command
                    msg_id = 1
                    command_copy = dict(command)
                    command_copy["id"] = msg_id
                    await ws.send(json.dumps(command_copy))

                    # 4. Receive response
                    response = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                    return response
            except Exception as e:
                last_err = str(e)
                logger.debug("Attempt to connect HA websocket at %s failed: %s", ws_url, e)

        logger.warning("All HA WebSocket candidate URLs failed (%s): %s", command.get("type"), last_err)
        return {"error": last_err or "All WebSocket candidate URLs failed"}

    async def get_thread_datasets(self) -> Dict[str, Any]:
        """
        Fetch all Thread datasets configured in Home Assistant.
        Calls 'thread/list_datasets' and then retrieves TLV/metadata for each.
        """
        list_res = await self.query_ha_websocket({"type": "thread/list_datasets"})
        if not isinstance(list_res, dict) or not list_res.get("success"):
            # Fallback to get_dataset if list_datasets not supported on older versions
            return await self.query_ha_websocket({"type": "thread/get_dataset"})
        return list_res

    async def get_thread_routers(self) -> Dict[str, Any]:
        """Discover Thread Border Routers (Nest Wifi Pro, Apple TV, SkyConnect) active on the network."""
        return await self.query_ha_websocket({"type": "thread/discover_routers"}, timeout=10.0)

    async def get_device_registry(self) -> List[Dict[str, Any]]:
        """Fetch full Home Assistant Device Registry to detect registered Nest, Google, and Thread hardware."""
        res = await self.query_ha_websocket({"type": "config/device_registry/list"})
        if isinstance(res, dict) and res.get("success") and isinstance(res.get("result"), list):
            return res["result"]
        return []

    async def get_matter_diagnostics(self) -> Dict[str, Any]:
        """Fetch matter integration diagnostics if available."""
        return await self.query_ha_websocket({"type": "matter/diagnostics"})

    async def get_all_available_thread_networks(self) -> List[Dict[str, Any]]:
        """
        Aggregate and normalize all Thread networks available in Home Assistant:
        1. Datasets stored in Home Assistant (thread/list_datasets)
        2. Networks discovered from active Border Routers (thread/discover_routers)
        3. Networks associated with registered Thread hardware in device registry
        """
        networks_map: Dict[str, Dict[str, Any]] = {}

        # 1. Fetch datasets from HA
        try:
            datasets_res = await self.get_thread_datasets()
            datasets_list = []
            if isinstance(datasets_res, dict):
                res_data = datasets_res.get("result", {})
                if isinstance(res_data, dict) and "datasets" in res_data:
                    d_items = res_data["datasets"]
                    if isinstance(d_items, list):
                        datasets_list = d_items
                    elif isinstance(d_items, dict):
                        datasets_list = list(d_items.values())
                elif isinstance(res_data, list):
                    datasets_list = res_data
                elif isinstance(res_data, dict) and ("dataset_id" in res_data or "extended_pan_id" in res_data):
                    datasets_list = [res_data]

            for ds in datasets_list:
                ds_id = str(ds.get("dataset_id") or "")
                xpan = str(ds.get("extended_pan_id") or ds.get("ext_pan_id") or "").upper().replace(":", "").replace("0X", "")
                net_name = ds.get("network_name") or ds.get("name") or (f"Thread Network ({xpan[:6]}...)" if xpan else "Home Assistant Thread Network")
                is_pref = bool(ds.get("preferred", False))
                ch = ds.get("channel")
                pan_id = ds.get("pan_id")
                pan_str = hex(pan_id) if isinstance(pan_id, int) else str(pan_id or "")

                key = xpan if xpan and xpan != "UNKNOWN" else (ds_id or net_name)
                networks_map[key] = {
                    "id": key,
                    "dataset_id": ds_id,
                    "name": net_name,
                    "extended_pan_id": xpan,
                    "pan_id": pan_str,
                    "channel": ch,
                    "preferred": is_pref,
                    "source": "Home Assistant Dataset" + (" ★ Preferred" if is_pref else ""),
                    "routers": []
                }
        except Exception as e:
            logger.warning("Error fetching Thread datasets: %s", e)

        # 2. Fetch discovered routers from HA
        try:
            routers_res = await self.get_thread_routers()
            routers_list = []
            if isinstance(routers_res, dict):
                r_data = routers_res.get("result", {})
                if isinstance(r_data, dict) and "routers" in r_data:
                    routers_list = r_data["routers"]
                elif isinstance(r_data, list):
                    routers_list = r_data

            for r in routers_list:
                xpan = str(r.get("extended_pan_id") or r.get("ext_pan_id") or "").upper().replace(":", "").replace("0X", "")
                net_name = r.get("network_name") or r.get("name") or (f"Thread Network ({xpan[:6]}...)" if xpan else "Thread Mesh")
                brand = r.get("brand_name") or r.get("vendor_name") or ""
                model = r.get("model_name") or r.get("model") or "Border Router"
                r_name = f"{brand} {model}".strip() if (brand or model) else "Border Router"
                ch = r.get("channel")
                pan_id = r.get("pan_id")
                pan_str = hex(pan_id) if isinstance(pan_id, int) else str(pan_id or "")

                key = xpan if xpan and xpan != "UNKNOWN" else net_name
                if key not in networks_map:
                    networks_map[key] = {
                        "id": key,
                        "dataset_id": "",
                        "name": net_name,
                        "extended_pan_id": xpan,
                        "pan_id": pan_str,
                        "channel": ch,
                        "preferred": False,
                        "source": f"Live Border Router ({r_name})",
                        "routers": [r_name]
                    }
                else:
                    if r_name not in networks_map[key]["routers"]:
                        networks_map[key]["routers"].append(r_name)
                    if not networks_map[key].get("channel") and ch:
                        networks_map[key]["channel"] = ch
                    if not networks_map[key].get("pan_id") and pan_str:
                        networks_map[key]["pan_id"] = pan_str
        except Exception as e:
            logger.warning("Error discovering Thread routers: %s", e)

        # 3. Check device registry for any hardware that wasn't found yet
        try:
            device_registry = await self.get_device_registry()
            for d in device_registry:
                m_str = f"{d.get('manufacturer', '')} {d.get('model', '')} {d.get('name', '')}".lower()
                if "wifi pro" in m_str or ("nest" in m_str and ("router" in m_str or "point" in m_str)):
                    name = d.get("name") or "Google Nest Wifi Pro"
                    has_nest = any("nest" in n["name"].lower() or any("nest" in r.lower() for r in n.get("routers", [])) for n in networks_map.values())
                    if not has_nest:
                        networks_map["GOOGLE_NEST_MESH"] = {
                            "id": "GOOGLE_NEST_MESH",
                            "dataset_id": "",
                            "name": f"Google Nest Thread Mesh ({name})",
                            "extended_pan_id": "GOOGLE_THREAD_MESH",
                            "pan_id": "",
                            "channel": None,
                            "preferred": False,
                            "source": "Home Assistant Device Registry",
                            "routers": [name]
                        }
                elif "apple tv" in m_str or "homepod" in m_str:
                    name = d.get("name") or "Apple TV / HomePod"
                    has_apple = any("apple" in n["name"].lower() or any("apple" in r.lower() for r in n.get("routers", [])) for n in networks_map.values())
                    if not has_apple:
                        networks_map["APPLE_THREAD_MESH"] = {
                            "id": "APPLE_THREAD_MESH",
                            "dataset_id": "",
                            "name": f"Apple Thread Mesh ({name})",
                            "extended_pan_id": "APPLE_THREAD_MESH",
                            "pan_id": "",
                            "channel": None,
                            "preferred": False,
                            "source": "Home Assistant Device Registry",
                            "routers": [name]
                        }
        except Exception as e:
            logger.warning("Error reading device registry: %s", e)

        # 4. Check Home Assistant States (HTTP REST API fallback)
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                r = await client.get(f"{self.ha_url}/api/states", headers=self._headers())
                if r.status_code == 200:
                    states = r.json()
                    for s in states:
                        eid = s.get("entity_id", "").lower()
                        attrs = s.get("attributes", {})
                        fname = attrs.get("friendly_name", "")
                        combined = f"{eid} {fname} {attrs}".lower()

                        if "wifi pro" in combined or ("nest" in combined and ("router" in combined or "point" in combined)):
                            r_name = fname or "Google Nest Wifi Pro"
                            has_nest = any("nest" in n["name"].lower() or any("nest" in r.lower() for r in n.get("routers", [])) for n in networks_map.values())
                            if not has_nest:
                                networks_map["GOOGLE_NEST_MESH"] = {
                                    "id": "GOOGLE_NEST_MESH",
                                    "dataset_id": "",
                                    "name": f"Google Nest Thread Mesh ({r_name})",
                                    "extended_pan_id": "GOOGLE_THREAD_MESH",
                                    "pan_id": "",
                                    "channel": None,
                                    "preferred": False,
                                    "source": "Home Assistant Entity States",
                                    "routers": [r_name]
                                }
                        elif "apple tv" in combined or "homepod" in combined:
                            r_name = fname or "Apple TV / HomePod"
                            has_apple = any("apple" in n["name"].lower() or any("apple" in r.lower() for r in n.get("routers", [])) for n in networks_map.values())
                            if not has_apple:
                                networks_map["APPLE_THREAD_MESH"] = {
                                    "id": "APPLE_THREAD_MESH",
                                    "dataset_id": "",
                                    "name": f"Apple Thread Mesh ({r_name})",
                                    "extended_pan_id": "APPLE_THREAD_MESH",
                                    "pan_id": "",
                                    "channel": None,
                                    "preferred": False,
                                    "source": "Home Assistant Entity States",
                                    "routers": [r_name]
                                }
        except Exception as e:
            logger.debug("Could not inspect states for Thread hardware: %s", e)

        return list(networks_map.values())
