"""
Matter Server Client for querying python-matter-server WebSocket API directly.
"""
import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
import websockets

logger = logging.getLogger("matter_thread_ai.matter_client")


class MatterClient:
    def __init__(self, ws_url: str = "ws://core-matter-server:5580/ws"):
        self.ws_url = ws_url

    async def get_nodes_and_server_info(self, timeout: float = 4.0) -> Dict[str, Any]:
        """
        Connect to python-matter-server WebSocket API to retrieve detailed node topology,
        operational credentials, reachability status, and diagnostic endpoints.
        """
        result: Dict[str, Any] = {
            "connected": False,
            "server_version": None,
            "nodes": [],
            "error": None
        }

        try:
            async with websockets.connect(self.ws_url, open_timeout=timeout) as ws:
                result["connected"] = True
                
                # Fetch server info / version
                msg_id = 1
                await ws.send(json.dumps({"message_id": str(msg_id), "command": "server_info"}))
                
                # Read response
                raw_info = await asyncio.wait_for(ws.recv(), timeout=timeout)
                info_data = json.loads(raw_info)
                if info_data.get("result"):
                    result["server_version"] = info_data["result"].get("version")
                    result["schema_version"] = info_data["result"].get("schema_version")

                # Fetch nodes
                msg_id += 1
                await ws.send(json.dumps({"message_id": str(msg_id), "command": "get_nodes"}))
                raw_nodes = await asyncio.wait_for(ws.recv(), timeout=timeout)
                nodes_data = json.loads(raw_nodes)

                if "result" in nodes_data and isinstance(nodes_data["result"], list):
                    result["nodes"] = self._format_nodes(nodes_data["result"])
                elif "result" in nodes_data and isinstance(nodes_data["result"], dict):
                    result["nodes"] = self._format_nodes(list(nodes_data["result"].values()))

        except asyncio.TimeoutError:
            result["error"] = f"Connection timed out reaching {self.ws_url}"
            logger.debug(result["error"])
        except ConnectionRefusedError:
            result["error"] = f"Connection refused at {self.ws_url} (Matter Server add-on may be stopped or initializing)"
            logger.debug(result["error"])
        except Exception as e:
            result["error"] = f"Matter server WS error: {str(e)}"
            logger.debug(result["error"])

        return result

    def _format_nodes(self, raw_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize Matter node data into structured diagnostic format."""
        formatted = []
        for n in raw_nodes:
            node_id = n.get("node_id")
            available = n.get("available", False)
            attributes = n.get("attributes", {})
            endpoints = n.get("endpoints", {})

            # Extract basic info
            basic_info = {}
            for ep_id, ep_val in endpoints.items() if isinstance(endpoints, dict) else []:
                clusters = ep_val.get("clusters", {})
                # Basic Information Cluster: ID 40 (0x0028)
                if "40" in clusters:
                    c = clusters["40"].get("attributes", {})
                    basic_info = {
                        "vendor_name": c.get("1") or c.get("vendor_name"),
                        "product_name": c.get("3") or c.get("product_name"),
                        "serial_number": c.get("15") or c.get("serial_number"),
                        "software_version_string": c.get("8") or c.get("software_version_string"),
                    }
                    break

            # Detect transport (Thread, WiFi, Ethernet)
            transport = "thread"  # Default assumption for Matter over Thread check
            if "wifi" in str(attributes).lower() or "wlan" in str(attributes).lower():
                transport = "wifi"
            elif "ethernet" in str(attributes).lower():
                transport = "ethernet"

            formatted.append({
                "node_id": node_id,
                "available": available,
                "transport": transport,
                "vendor_name": basic_info.get("vendor_name") or n.get("vendor_name", "Unknown"),
                "product_name": basic_info.get("product_name") or n.get("product_name", f"Matter Node {node_id}"),
                "software_version": basic_info.get("software_version_string"),
                "date_commissioned": n.get("date_commissioned"),
                "is_bridge": n.get("is_bridge", False),
                "raw_summary": {
                    "attribute_count": len(attributes),
                    "endpoint_count": len(endpoints),
                }
            })
        return formatted
