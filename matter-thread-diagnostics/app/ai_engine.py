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

CLIENT_TIMEOUT = httpx.Timeout(55.0, connect=10.0, read=55.0, write=15.0)


def _ipv4_transport() -> Optional[ Any ]:
    """
    Bind outbound cloud API connections to 0.0.0.0 (IPv4) so that `host_network: true`
    never hangs on residential ISP IPv6 WAN blackholes or PMTU drops when sending
    multi-kilobyte JSON prompts to generativelanguage.googleapis.com / openai / anthropic.
    """
    if hasattr(httpx, "AsyncHTTPTransport"):
        try:
            return httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1)
        except Exception:
            return None
    return None


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
        """Preserve user-selected model, providing sensible defaults only when blank."""
        m = (model or "").strip()
        if provider == "gemini":
            if not m or m.lower() == "gemini" or not m.lower().startswith("gemini"):
                return "gemini-2.5-flash"
            return m
        elif provider == "openai":
            if not m or (not m.lower().startswith("gpt-") and not m.lower().startswith("o")):
                return "gpt-4o"
            return m
        elif provider == "anthropic":
            if not m or not m.lower().startswith("claude-"):
                return "claude-3-5-sonnet-20241022"
            return m
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

        compact_networks = []
        for net in (raw_data.get("available_thread_networks") or [])[:6]:
            if isinstance(net, dict):
                compact_networks.append({
                    "name": net.get("name"),
                    "extended_pan_id": net.get("extended_pan_id"),
                    "channel": net.get("channel"),
                    "pan_id": net.get("pan_id"),
                    "preferred": net.get("preferred"),
                    "routers_count": len(net.get("routers") or []),
                })

        pings_raw = telemetry.get("reachability_probes") or {}
        compact_pings = {
            "probed_count": pings_raw.get("probed_count", 0),
            "reachable_count": pings_raw.get("reachable_count", 0),
            "results": [
                {
                    "name": p.get("name"),
                    "ip": p.get("ip"),
                    "reachable": p.get("reachable"),
                    "rtt_ms": p.get("rtt_ms"),
                }
                for p in (pings_raw.get("results") or [])[:12]
                if isinstance(p, dict)
            ],
        }

        logs_raw = telemetry.get("logs_sample") or {}
        compact_logs = {
            "matter_server_recent_errors": (logs_raw.get("matter_server_recent_errors") or [])[-8:],
            "otbr_recent_errors": (logs_raw.get("otbr_recent_errors") or [])[-8:],
        }

        return {
            "scan_timestamp": raw_data.get("timestamp"),
            "hardware_platform": raw_data.get("hardware_platform", "Home Assistant OS"),
            "health_score": raw_data.get("summary_score", 100),
            "selected_target_network": {
                "name": (raw_data.get("selected_target_network") or {}).get("name"),
                "extended_pan_id": (raw_data.get("selected_target_network") or {}).get("extended_pan_id"),
                "channel": (raw_data.get("selected_target_network") or {}).get("channel"),
            } if isinstance(raw_data.get("selected_target_network"), dict) else raw_data.get("selected_target_network"),
            "available_thread_networks": compact_networks,
            "thread_border_routers": routers_summary[:10],
            "otbr_status": {
                "reachable": (telemetry.get("otbr") or {}).get("reachable"),
                "state": (telemetry.get("otbr") or {}).get("state"),
                "extended_pan_id": (telemetry.get("otbr") or {}).get("extended_pan_id"),
                "channel": (telemetry.get("otbr") or {}).get("channel"),
            } if isinstance(telemetry.get("otbr"), dict) else None,
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
                "ula_routes_detailed": (ipv6.get("ula_routes_detailed") or [])[:6],
                "neighbors_count": ipv6.get("neighbors_count", 0),
            },
            "active_icmpv6_pings": compact_pings,
            "node_quality": {
                "total_nodes": nq.get("total_nodes", len(matter_nodes)),
                "healthy_count": nq.get("healthy_count", 0),
                "offline_nodes": (nq.get("offline_nodes") or [])[:15],
                "weak_nodes": (nq.get("weak_nodes") or [])[:15],
                "wrong_network_nodes": (nq.get("wrong_network_nodes") or [])[:15],
            },
            "matter_nodes_cluster_0x0035": matter_nodes[:25],
            "logs_summary": compact_logs,
        }

    def _build_prompt(self, data: Dict[str, Any], user_notes: Optional[str]) -> str:
        streamlined = self._streamline_telemetry(data)
        data_json = json.dumps(streamlined, separators=(",", ":"))
        notes_section = f"\nUser Symptoms / Questions:\n{user_notes}\n" if user_notes else ""
        return (
            f"Please analyze the following real diagnostic scan collected from the user's Home Assistant Matter & Thread network:\n"
            f"{notes_section}\n"
            f"```json\n{data_json}\n```\n\n"
            f"Diagnose all Matter-over-Thread issues found in this scan and provide a concise, specific, actionable troubleshooting report (under 600 words)."
        )

    async def _fetch_live_gemini_models(self, client: httpx.AsyncClient) -> List[Dict[str, str]]:
        """Query Google ModelService.ListModels (`GET /v1beta/models`) to discover exact model IDs supported on this API key."""
        if not self.gemini_key:
            return []
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        headers = {"x-goog-api-key": self.gemini_key.strip()}
        params = {"key": self.gemini_key.strip(), "pageSize": 100}
        try:
            r = await client.get(url, headers=headers, params=params, timeout=10.0)
            if r.status_code != 200:
                return []
            data = r.json()
            raw_models = data.get("models", [])
            out: List[Dict[str, str]] = []
            skip_keywords = ("embedding", "imagen", "veo", "tts", "audio", "aqa", "bison", "gecko", "learnlm", "robotics", "computer-use", "image-generation", "1.0", "1.5")
            for m in raw_models:
                if not isinstance(m, dict):
                    continue
                methods = m.get("supportedGenerationMethods") or []
                if "generateContent" not in methods:
                    continue
                full_name = str(m.get("name") or "")
                short_id = full_name.replace("models/", "").strip()
                if not short_id.startswith("gemini"):
                    continue
                if any(kw in short_id.lower() for kw in skip_keywords):
                    continue
                disp = str(m.get("displayName") or short_id)
                out.append({"value": short_id, "label": f"{disp} ({short_id})" if short_id not in disp else disp})

            # Sort newest/best families first: gemini-3*, then gemini-2.5*, then flash before pro
            def _sort_key(item: Dict[str, str]):
                v = item["value"].lower()
                tier = 0 if "gemini-3" in v else (1 if "gemini-2.5" in v else 2)
                sub = 0 if "flash" in v and "lite" not in v else (1 if "pro" in v else 2)
                return (tier, sub, v)

            out.sort(key=_sort_key)
            return out
        except Exception as e:
            logger.debug("ListModels lookup failed: %s", e)
            return []

    async def list_available_models(self) -> List[Dict[str, str]]:
        """Return live available models for the current provider."""
        if self.provider == "gemini" and self.has_valid_key():
            transport = _ipv4_transport()
            kwargs: Dict[str, Any] = {"timeout": httpx.Timeout(10.0)}
            if transport is not None:
                kwargs["transport"] = transport
            async with httpx.AsyncClient(**kwargs) as client:
                live = await self._fetch_live_gemini_models(client)
                if live:
                    return live
        return []

    def _pick_best_live_gemini_model(self, requested: str, live_models: List[Dict[str, str]]) -> List[str]:
        """Given the user's requested model (e.g. 'gemini-3.8-flash') and live ListModels output, rank the closest live model IDs."""
        req_low = (requested or "").lower()
        live_ids = [m["value"] for m in live_models if m.get("value")]
        ranked: List[str] = []

        # 1. Exact match in live models
        if requested in live_ids:
            ranked.append(requested)

        # 2. If user asked for a Gemini 3 model (e.g. gemini-3.8-flash), prefer live gemini-3* flash/pro models first
        if "gemini-3" in req_low or "3." in req_low:
            want_pro = "pro" in req_low
            for lid in live_ids:
                if "gemini-3" in lid.lower() and (("pro" in lid.lower()) == want_pro) and lid not in ranked:
                    ranked.append(lid)
            for lid in live_ids:
                if "gemini-3" in lid.lower() and lid not in ranked:
                    ranked.append(lid)

        # 3. Prefer gemini-2.5-flash / gemini-2.5-pro from live models
        for pref in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-flash-latest"]:
            if pref in live_ids and pref not in ranked:
                ranked.append(pref)

        # 4. Any remaining live flash/pro model
        for lid in live_ids:
            if lid not in ranked:
                ranked.append(lid)

        # 5. If ListModels returned nothing, fallback to active 2.5 models (NEVER dead 1.5 models)
        if not ranked:
            for fb in ["gemini-2.5-flash", "gemini-2.5-pro"]:
                if fb not in ranked:
                    ranked.append(fb)

        return ranked

    async def _stream_or_post_gemini(
        self,
        client: httpx.AsyncClient,
        model_name: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> tuple[int, str, str]:
        """
        Execute Gemini generation using SSE streaming (`:streamGenerateContent?alt=sse`) first so chunks
        arrive within ~1-2 seconds and never hit idle TCP ReadTimeout, falling back to `:generateContent` if needed.
        Returns (http_status_code, response_text, error_message).
        """
        stream_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent"
        stream_params = {"key": self.gemini_key.strip(), "alt": "sse"}

        try:
            chunks: List[str] = []
            thought_chunks: List[str] = []
            async with client.stream("POST", stream_url, json=payload, headers=headers, params=stream_params) as resp:
                if resp.status_code != 200:
                    raw_err = (await resp.aread()).decode("utf-8", errors="ignore")
                    err_msg = raw_err
                    try:
                        err_json = json.loads(raw_err)
                        err_msg = err_json.get("error", {}).get("message", raw_err)
                    except Exception:
                        pass
                    return resp.status_code, "", err_msg

                async for line in resp.aiter_lines():
                    line_s = line.strip()
                    if not line_s.startswith("data:"):
                        continue
                    data_str = line_s[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        ev = json.loads(data_str)
                        for cand in ev.get("candidates") or []:
                            for part in (cand.get("content") or {}).get("parts") or []:
                                if isinstance(part, dict) and part.get("text"):
                                    if part.get("thought"):
                                        thought_chunks.append(part["text"])
                                    else:
                                        chunks.append(part["text"])
                    except Exception:
                        continue

            final_text = "".join(chunks).strip() or "".join(thought_chunks).strip()
            if final_text:
                return 200, final_text, ""
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError):
            raise
        except Exception as e:
            logger.debug("SSE stream fallback to generateContent for %s: %s", model_name, e)

        # Fallback to standard generateContent
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        params = {"key": self.gemini_key.strip()}
        r = await client.post(url, json=payload, headers=headers, params=params)
        if r.status_code != 200:
            err_text = r.text
            try:
                err_json = r.json()
                err_text = err_json.get("error", {}).get("message", err_text)
            except Exception:
                pass
            return r.status_code, "", err_text

        res_data = r.json()
        candidates = res_data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                non_thought = [p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought") and p.get("text")]
                if non_thought:
                    return 200, "\n".join(non_thought), ""
                all_t = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
                if all_t:
                    return 200, "\n".join(all_t), ""
        return 200, "No response text generated by Gemini.", ""

    async def _call_gemini(self, prompt: str) -> str:
        """
        Call Google Gemini API with the user's selected model first.
        If the selected model name returns 404 on v1beta, dynamically query Google's `ListModels` API
        to resolve the exact live Gemini 3 / 2.5 model ID supported by the user's API key.
        Never falls back to retired gemini-1.5 models.
        """
        requested_model = self.model or "gemini-2.5-flash"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.gemini_key.strip(),
        }

        transport = _ipv4_transport()
        client_kwargs: Dict[str, Any] = {"timeout": CLIENT_TIMEOUT}
        if transport is not None:
            client_kwargs["transport"] = transport

        async with httpx.AsyncClient(**client_kwargs) as client:
            # Start with the exact model selected by the user in Settings / AI Studio
            candidate_models: List[str] = [requested_model]
            live_models_fetched = False
            last_err = None

            idx = 0
            while idx < len(candidate_models):
                model_name = candidate_models[idx]
                idx += 1

                gen_cfg: Dict[str, Any] = {
                    "temperature": 0.2,
                    "maxOutputTokens": 2500,
                }
                # Disable slow internal chain-of-thought on Flash models so streaming starts in <1s
                if "flash" in model_name.lower() and ("2.5" in model_name.lower() or "3" in model_name.lower()):
                    gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}

                payload = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}],
                        }
                    ],
                    "generationConfig": gen_cfg,
                }

                try:
                    status_code, text_out, err_msg = await self._stream_or_post_gemini(client, model_name, payload, headers)
                    # If model rejects thinkingConfig (HTTP 400), retry immediately without thinkingConfig
                    if status_code == 400 and "thinkingConfig" in gen_cfg:
                        gen_cfg.pop("thinkingConfig", None)
                        status_code, text_out, err_msg = await self._stream_or_post_gemini(client, model_name, payload, headers)
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as tex:
                    last_err = f"{type(tex).__name__} on {model_name}"
                    logger.warning("Gemini model '%s' timed out (%s)", model_name, tex)
                    if not live_models_fetched:
                        live_models_fetched = True
                        live_list = await self._fetch_live_gemini_models(client)
                        for alt in self._pick_best_live_gemini_model(requested_model, live_list):
                            if alt not in candidate_models:
                                candidate_models.append(alt)
                    if idx < len(candidate_models):
                        continue
                    raise

                if status_code == 200:
                    if model_name != requested_model:
                        self.model = f"{requested_model} → {model_name}"
                    else:
                        self.model = model_name
                    return text_out

                last_err = f"Google Error {status_code} ({model_name}): {err_msg}"

                # If the exact model string returned 404 (or 429/503), query ListModels dynamically once
                if status_code in (404, 429, 503):
                    if not live_models_fetched:
                        live_models_fetched = True
                        live_list = await self._fetch_live_gemini_models(client)
                        for alt in self._pick_best_live_gemini_model(requested_model, live_list):
                            if alt not in candidate_models:
                                candidate_models.append(alt)
                    if idx < len(candidate_models):
                        logger.warning("Model '%s' returned %s, trying live model '%s'", model_name, status_code, candidate_models[idx])
                        continue

                raise RuntimeError(last_err)

        raise RuntimeError(last_err or f"Failed to call Gemini API with model '{requested_model}'")

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI Chat Completions REST API over IPv4 transport."""
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

        transport = _ipv4_transport()
        client_kwargs: Dict[str, Any] = {"timeout": CLIENT_TIMEOUT}
        if transport is not None:
            client_kwargs["transport"] = transport

        async with httpx.AsyncClient(**client_kwargs) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            res_data = r.json()
            choices = res_data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return "No response text generated by OpenAI."

    async def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Messages REST API over IPv4 transport."""
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

        transport = _ipv4_transport()
        client_kwargs: Dict[str, Any] = {"timeout": CLIENT_TIMEOUT}
        if transport is not None:
            client_kwargs["transport"] = transport

        async with httpx.AsyncClient(**client_kwargs) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            res_data = r.json()
            content = res_data.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "")
            return "No response text generated by Anthropic."
