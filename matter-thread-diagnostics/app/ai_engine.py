"""
AI Diagnostic Engine supporting Google Gemini, OpenAI, and Anthropic Claude.
Synthesizes real Matter Cluster 0x0035 telemetry, mDNS Border Router discovery,
OTBR REST state, IPv6 ULA routes, and ICMPv6 reachability probes into expert diagnostic reports.
"""
import json
import logging
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger("matter_thread_ai.ai_engine")

SYSTEM_PROMPT = """You are the Matter & Thread AI Diagnostic Specialist running inside Home Assistant OS.
Your goal is to inspect LIVE diagnostic telemetry collected from the user's actual network:
- Selected Target Thread Network (Extended PAN ID, Channel, PAN ID, Mesh-Local Prefix)
- Discovered Thread Border Routers via mDNS (`_meshcop._udp.local.`), HA `thread/discover_routers`, and OpenThread Border Router (OTBR) REST API
- Commissioned Matter-over-Thread Nodes with live Matter Cluster 0x0035 (Thread Network Diagnostics) attributes: RoutingRole (Leader, Router, REED, EndDevice, SleepyEndDevice), RLOC16, Extended PAN ID, NeighborTable (RSSI, LQI, frame/message error rates), RouteTable, and error counters (DetachedRoleCount, ParentChangeCount, OverrunCount)
- Kernel IPv6 Routing Table (`fd00::/8` ULA prefixes advertised via ICMPv6 RIO) and Neighbor Discovery cache
- Active ICMPv6 Ping Reachability & RTT Latency measurements to Border Routers and Matter nodes
- Recent `python-matter-server` and `otbr` log errors

Deep Matter & Thread Domain Knowledge to apply:
1. MULTI-BORDER ROUTER SYNC & SPLIT THREAD NETWORKS:
   - Google Nest Wifi Pro / Nest Hub, Apple TV 4K / HomePod, and Home Assistant (Connect ZBT-1 / SkyConnect OTBR) each act as Thread Border Routers.
   - Compare the `extended_pan_id` across all discovered Border Routers and Matter nodes. If multiple Extended PAN IDs exist, or if nodes are stranded on a different Extended PAN ID than the selected target network, explain exactly which devices are desynced and how to unify them.
2. MATTER CLUSTER 0x0035 LINK & TOPOLOGY DIAGNOSTICS:
   - Inspect each node's `routing_role`, `rloc16`, `rssi` (dBm), `lqi` (0-255), `neighbor_table`, and `telemetry_counters` (`parent_change_count`, `detached_role_count`).
   - RSSI below -82 dBm or LQI below 64 indicates high RF attenuation; recommend adding a mains-powered Matter-over-Thread router (e.g. smart plug) between the Border Router and the weak node.
   - High `parent_change_count` or `detached_role_count` on Sleepy End Devices (SED/ICD) indicates unstable parent router links or Border Router reboots.
3. RF INTERFERENCE (Wi-Fi 2.4 GHz vs Thread 802.15.4):
   - Thread channels 11-14 overlap Wi-Fi Ch 1; 16-19 overlap Wi-Fi Ch 6; 21-24 overlap Wi-Fi Ch 11; Channel 25/26 are clear of standard 20 MHz Wi-Fi channels.
   - USB 3.0 ports emit wideband 2.4 GHz noise; ZBT-1 / SkyConnect radios must use a USB 2.0 extension cable away from the host chassis.
4. IPv6 ROUTING, MULTICAST & ICMPv6 PING REACHABILITY:
   - Matter-over-Thread requires end-to-end IPv6 routing to the Thread ULA prefix (`fd00::/8`) via Border Router link-local addresses (`fe80::...`).
   - If `has_thread_ula_route` is false or ICMPv6 pings to Matter nodes time out while Border Routers are online, check IPv6 RA/RIO acceptance (`accept_ra_rt_info_max_plen`) and Wi-Fi router multicast/IGMP/MLD snooping settings.

Format your response clearly using markdown:
1. 🩺 **Executive Health Rating**: Score out of 100% and Status (CRITICAL / WARNING / HEALTHY) based strictly on the real telemetry provided.
2. 🔍 **Root Cause Analysis**: Cite specific Border Routers, Extended PAN IDs, Matter Node IDs/names, RLOC16s, RSSI/LQI values, and IPv6 routes from the scan data.
3. 🛠️ **Step-by-Step Remediation Plan**: Actionable, numbered steps tailored to the user's exact hardware and network scan results.
4. 📡 **Node-by-Node & RF Recommendations**: Specific placement, routing role, or channel fixes for any weak, offline, or desynced nodes.
"""

CLIENT_TIMEOUT = httpx.Timeout(180.0, connect=30.0, read=180.0, write=30.0)


class AIDiagnosticEngine:
    def __init__(
        self,
        provider: str = "gemini",
        model: str = "gemini-2.5-flash",
        gemini_key: str = "",
        openai_key: str = "",
        anthropic_key: str = "",
    ):
        self.provider = (provider or "gemini").lower()
        self.model = self._normalize_model(self.provider, model)
        self.gemini_key = gemini_key.strip().strip('"').strip("'") if gemini_key else ""
        self.openai_key = openai_key.strip().strip('"').strip("'") if openai_key else ""
        self.anthropic_key = anthropic_key.strip().strip('"').strip("'") if anthropic_key else ""

    def _normalize_model(self, provider: str, model: str) -> str:
        """Map model aliases to valid, active provider model IDs."""
        m = (model or "").strip().lower()
        if provider == "gemini":
            # Map legacy/non-existent 3.8/3-flash aliases to real gemini-2.5-flash
            if not m or m == "gemini" or "3.8" in m or "38" in m or "3-flash" in m:
                return "gemini-2.5-flash"
            return m
        elif provider == "openai":
            if "mini" in m:
                return "gpt-4o-mini"
            return m if m.startswith("gpt-") or m.startswith("o") else "gpt-4o"
        elif provider == "anthropic":
            if "haiku" in m:
                return "claude-3-5-haiku-20241022"
            return m if m.startswith("claude-") else "claude-3-5-sonnet-20241022"
        return m or "gemini-2.5-flash"

    def has_valid_key(self) -> bool:
        if self.provider == "gemini":
            return bool(self.gemini_key and len(self.gemini_key.strip()) > 5)
        elif self.provider == "openai":
            return bool(self.openai_key and len(self.openai_key.strip()) > 5)
        elif self.provider == "anthropic":
            return bool(self.anthropic_key and len(self.anthropic_key.strip()) > 5)
        return False

    async def test_connection(self) -> Dict[str, Any]:
        """Verify API key and model connectivity with a lightweight ping."""
        if not self.has_valid_key():
            return {
                "success": False,
                "error": f"API key for '{self.provider}' is empty or invalid. Please paste your key and click Save Settings.",
            }
        try:
            ping_prompt = "Reply with 'OK: Matter AI ready'."
            if self.provider == "gemini":
                ans = await self._call_gemini(ping_prompt)
            elif self.provider == "openai":
                ans = await self._call_openai(ping_prompt)
            elif self.provider == "anthropic":
                ans = await self._call_anthropic(ping_prompt)
            else:
                return {"success": False, "error": f"Unsupported provider: {self.provider}"}

            return {
                "success": True,
                "message": f"Connected to {self.provider} ({self.model})! Response: {ans.strip()[:60]}",
            }
        except Exception as e:
            err_msg = str(e).strip() or repr(e)
            return {"success": False, "error": f"{type(e).__name__}: {err_msg}"}

    async def run_diagnosis(self, diagnostic_data: Dict[str, Any], user_notes: Optional[str] = None) -> Dict[str, Any]:
        """Send formatted real diagnostic payload to the chosen AI provider."""
        if not self.has_valid_key():
            return {
                "success": False,
                "error": f"Missing or invalid API key for provider '{self.provider}'. Please enter your API key in Settings.",
                "analysis": None,
            }

        prompt = self._build_prompt(diagnostic_data, user_notes)

        try:
            if self.provider == "gemini":
                analysis = await self._call_gemini(prompt)
            elif self.provider == "openai":
                analysis = await self._call_openai(prompt)
            elif self.provider == "anthropic":
                analysis = await self._call_anthropic(prompt)
            else:
                return {"success": False, "error": f"Unsupported AI provider: {self.provider}"}

            return {
                "success": True,
                "provider": self.provider,
                "model": self.model,
                "analysis": analysis,
            }
        except httpx.ReadTimeout:
            logger.error("AI API ReadTimeout after 180s")
            return {
                "success": False,
                "error": f"{self.provider.upper()} took longer than 180 seconds to respond (ReadTimeout). Please try again.",
            }
        except httpx.HTTPStatusError as e:
            logger.error("AI API HTTP Error (%s): %s", e.response.status_code, e.response.text)
            return {"success": False, "error": f"API HTTP Error ({e.response.status_code}): {e.response.text}"}
        except Exception as e:
            logger.error("AI API Exception: %s", e, exc_info=True)
            err_msg = str(e).strip() or repr(e)
            return {"success": False, "error": f"Failed calling {self.provider}: {type(e).__name__} ({err_msg})"}

    def _streamline_telemetry(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Package real diagnostic telemetry into a rich, structured JSON context for the LLM."""
        if "raw_text" in raw_data and "source" in raw_data:
            return raw_data

        rules = raw_data.get("rule_evaluations", {})
        split = rules.get("split_network", {})
        rf = rules.get("rf_coexistence", {})
        nq = rules.get("node_quality", {})
        ipv6 = rules.get("ipv6_routing", {})
        telemetry = raw_data.get("telemetry", {})

        routers_summary = []
        for r in split.get("all_discovered_routers", telemetry.get("border_routers", [])):
            routers_summary.append({
                "name": r.get("name"),
                "model": r.get("model"),
                "brand": r.get("brand"),
                "network_name": r.get("network_name"),
                "extended_pan_id": r.get("extended_pan_id"),
                "channel": r.get("channel"),
                "pan_id": r.get("pan_id"),
                "mesh_local_prefix": r.get("mesh_local_prefix"),
                "ext_address": r.get("ext_address"),
                "rloc16": r.get("rloc16"),
                "addresses": (r.get("addresses") or [])[:4],
                "source": r.get("source"),
            })

        matter_nodes = []
        for n in telemetry.get("matter_server", {}).get("nodes", []):
            matter_nodes.append({
                "node_id": n.get("node_id"),
                "product_name": n.get("product_name"),
                "vendor_name": n.get("vendor_name"),
                "available": n.get("available"),
                "transport": n.get("transport"),
                "routing_role": n.get("routing_role"),
                "rloc16": n.get("rloc16"),
                "ext_address": n.get("ext_address"),
                "extended_pan_id": n.get("extended_pan_id"),
                "thread_channel": n.get("thread_channel"),
                "rssi_dbm": n.get("rssi"),
                "lqi": n.get("lqi"),
                "parent_rloc16": n.get("parent_rloc16"),
                "ipv6_addresses": (n.get("ipv6_addresses") or [])[:3],
                "neighbors_count": len(n.get("neighbor_table") or []),
                "telemetry_counters": n.get("telemetry_counters"),
            })

        return {
            "scan_timestamp": raw_data.get("timestamp"),
            "hardware_platform": raw_data.get("hardware_platform", "Home Assistant OS"),
            "health_score": raw_data.get("summary_score", 100),
            "selected_target_network": raw_data.get("selected_target_network"),
            "available_thread_networks": raw_data.get("available_thread_networks", []),
            "thread_border_routers": routers_summary,
            "otbr_status": telemetry.get("otbr"),
            "mdns_discovery": {
                "scanner_backend": telemetry.get("mdns_info", {}).get("scanner_backend"),
                "meshcop_border_routers_count": telemetry.get("mdns_info", {}).get("meshcop_border_routers_count", 0),
                "matter_operational_nodes_count": telemetry.get("mdns_info", {}).get("matter_operational_nodes_count", 0),
            },
            "split_network_analysis": {
                "is_split_network": split.get("is_split_network", False),
                "distinct_network_count": split.get("distinct_network_count", 0),
                "summary": split.get("summary", ""),
            },
            "rf_coexistence": {
                "thread_channel": rf.get("thread_channel"),
                "severity": rf.get("severity"),
                "overlapping_wifi_channel": rf.get("overlapping_wifi_channel"),
                "recommendation": rf.get("recommendation"),
            },
            "ipv6_routing": {
                "has_thread_ula_route": ipv6.get("has_thread_ula_route", False),
                "detected_ula_prefixes": ipv6.get("detected_ula_prefixes", []),
                "ula_routes_detailed": ipv6.get("ula_routes_detailed", []),
                "neighbors_count": ipv6.get("neighbors_count", 0),
            },
            "active_icmpv6_pings": telemetry.get("reachability_probes", {}),
            "node_quality": {
                "total_nodes": nq.get("total_nodes", len(matter_nodes)),
                "healthy_count": nq.get("healthy_count", 0),
                "offline_nodes": nq.get("offline_nodes", []),
                "weak_nodes": nq.get("weak_nodes", []),
                "wrong_network_nodes": nq.get("wrong_network_nodes", []),
            },
            "matter_nodes_cluster_0x0035": matter_nodes[:30],
            "logs_summary": telemetry.get("logs_sample", {}),
        }

    def _build_prompt(self, data: Dict[str, Any], user_notes: Optional[str]) -> str:
        streamlined = self._streamline_telemetry(data)
        data_json = json.dumps(streamlined, indent=2)
        notes_section = f"\nUser Symptoms / Questions:\n{user_notes}\n" if user_notes else ""
        return (
            f"Please analyze the following real diagnostic scan collected from the user's Home Assistant Matter & Thread network:\n"
            f"{notes_section}\n"
            f"```json\n{data_json}\n```\n\n"
            f"Diagnose all Matter-over-Thread issues found in this scan and provide a specific, actionable troubleshooting report."
        )

    async def _call_gemini(self, prompt: str) -> str:
        """Call Google Gemini REST API with automatic model fallback if a model alias returns 404."""
        candidate_models: List[str] = []
        for m in [self.model, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
            if m and m not in candidate_models:
                candidate_models.append(m)

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.gemini_key.strip(),
        }
        params = {"key": self.gemini_key.strip()}
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 3000,
            },
        }

        last_err = None
        async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT) as client:
            for model_name in candidate_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                r = await client.post(url, json=payload, headers=headers, params=params)
                if r.status_code == 404 and model_name != candidate_models[-1]:
                    logger.warning("Gemini model '%s' returned 404, falling back to next available model", model_name)
                    continue
                if r.status_code != 200:
                    err_text = r.text
                    try:
                        err_json = r.json()
                        err_text = err_json.get("error", {}).get("message", err_text)
                    except Exception:
                        pass
                    last_err = f"Google Error {r.status_code} ({model_name}): {err_text}"
                    raise RuntimeError(last_err)

                self.model = model_name
                res_data = r.json()
                candidates = res_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                return "No response text generated by Gemini."

        raise RuntimeError(last_err or "Failed to call Gemini API")

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI Chat Completions REST API."""
        model_name = self.model or "gpt-4o"
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_key.strip()}",
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 3000,
        }

        async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            res_data = r.json()
            choices = res_data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return "No response text generated by OpenAI."

    async def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Messages REST API."""
        model_name = self.model or "claude-3-5-sonnet-20241022"
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.anthropic_key.strip(),
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": model_name,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 3000,
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            res_data = r.json()
            content = res_data.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "")
            return "No response text generated by Anthropic."
