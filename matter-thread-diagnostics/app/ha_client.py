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
        """Send command over HA WebSocket API with robust authentication and response capture."""
        if not self.is_available:
            return {"error": "No supervisor token"}

        ws_url = self.ha_url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
        try:
            async with websockets.connect(ws_url, open_timeout=timeout) as ws:
                # 1. Receive auth required
                auth_req = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                if auth_req.get("type") != "auth_required":
                    return {"error": "Unexpected auth handshake response", "raw": auth_req}

                # 2. Authenticate
                await ws.send(json.dumps({
                    "type": "auth",
                    "access_token": self.supervisor_token
                }))
                auth_res = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                if auth_res.get("type") != "auth_ok":
                    return {"error": "Auth failed", "raw": auth_res}

                # 3. Send command
                msg_id = 1
                command["id"] = msg_id
                await ws.send(json.dumps(command))

                # 4. Receive response
                response = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                return response
        except asyncio.TimeoutError:
            logger.warning("HA WebSocket command timed out (%s)", command.get("type"))
            return {"error": f"Timeout waiting for response to {command.get('type')}"}
        except Exception as e:
            logger.warning("HA WebSocket command failed (%s): %s", command.get("type"), e)
            return {"error": str(e)}

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
