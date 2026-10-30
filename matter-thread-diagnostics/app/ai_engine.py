"""
AI Diagnostic Engine supporting Google Gemini, OpenAI, and Anthropic Claude.
Synthesizes Matter & Thread telemetry into expert diagnostic reports.
"""
import json
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger("matter_thread_ai.ai_engine")

SYSTEM_PROMPT = """You are the Matter & Thread AI Diagnostic Specialist running on a Home Assistant Green hub (HAOS).
Your goal is to inspect diagnostic telemetry (Thread mesh topology, active datasets, Border Router sync, IPv6 routes, Matter server logs, node reachability, and RF co-existence) and provide precise, actionable troubleshooting guidance.

Deep Matter & Thread Domain Knowledge to apply:
1. MULTI-BORDER ROUTER SYNC (SPLIT THREAD NETWORKS, GOOGLE NEST WIFI PRO & APPLE TV):
   - Google Nest Wifi Pro, Google Nest Hub (2nd gen), Apple TV 4K / HomePod mini, and Home Assistant (SkyConnect/Connect ZBT-1) each contain Thread Border Routers.
   - If they operate on differing Extended PAN IDs (XPAN) or Network Keys, devices paired through Google Home or Apple Home cannot route to Home Assistant (Split Network failure!).
   - GOOGLE NEST WIFI PRO SYNC PROCEDURE:
     * Google stores Thread credentials inside Google Play Services / Google Home Keychain on Android or iOS.
     * To unify Nest Wifi Pro with Home Assistant Green: Open the Home Assistant Companion App on a phone signed into the Google Home account -> Settings -> Companion App -> Troubleshooting -> "Sync Thread Credentials" (import Google credentials into HA).
     * Then in Home Assistant: Settings -> Devices & Services -> Thread -> Select the Google Nest network -> "Make Preferred Network".
   - APPLE TV / HOMEPOD SYNC PROCEDURE:
     * In Apple Home, Apple TVs & HomePods create an Apple Keychain Thread network.
     * Use Home Assistant Companion App on iOS -> Settings -> Companion App -> Troubleshooting -> "Sync Thread Credentials" to import Apple's dataset into Home Assistant.
2. RF INTERFERENCE (Wi-Fi 2.4GHz vs Thread 802.15.4):
   - Thread channels 11-26: Thread Ch 11 overlaps Wi-Fi Ch 1; Ch 17-19 overlaps Wi-Fi Ch 6; Ch 22-24 overlaps Wi-Fi Ch 11.
   - Thread Ch 25 is ideal.
   - Note: USB 3.0 ports emit wideband RF noise at 2.4 GHz. SkyConnect / Thread dongles must always use a 1-meter USB extension cable away from HA Green's chassis!
3. IPv6 ROUTING & MULTICAST (ULA, RIO, mDNS):
   - Matter-over-Thread requires IPv6. Border Routers advertise Route Information Options (RIO) for Thread mesh prefixes (fd00::/8).
   - If Wi-Fi routers (Nest Wifi Pro, UniFi, Omada, Eero, Asus) have "Block LAN to WLAN Multicast", "IGMP Snooping" without MLD snooping, or drop ICMPv6 RAs, HA Green loses routes to Thread devices.
4. MATTER PROTOCOL SESSIONS:
   - PASE (Passcode-Authenticated Session Establishment) fails during commissioning if Bluetooth or initial Wi-Fi/Thread handshake drops.
   - CASE (Certificate-Authenticated Session Establishment) fails if IPv6 route or fabric operational credentials mismatch.
   - ICD (Intermittently Connected Devices / Sleepy End Devices) battery nodes go offline if parent router reboots or child polling fails.

Format your response clearly using markdown with:
1. 🩺 **Executive Health Rating**: (Score out of 100% and Status: CRITICAL / WARNING / HEALTHY)
2. 🔍 **Root Cause Analysis**: Point out the exact primary and secondary technical issues identified in the data.
3. 🛠️ **Step-by-Step Remediation Plan**: Clear, numbered steps the user should execute directly in Home Assistant Green or on their network hardware.
4. 📡 **RF & Hardware Recommendations**: Physical placement, channel changes, extension cable checks.
5. 💻 **Copy-Paste Commands & Tools**: Any relevant commands, dataset sync steps, or HA Developer Tools states to check.
"""

# 3-minute read timeout for deep LLM generation
CLIENT_TIMEOUT = httpx.Timeout(180.0, connect=30.0, read=180.0, write=30.0)


class AIDiagnosticEngine:
    def __init__(self, provider: str = "gemini", model: str = "gemini-3.8-flash",
                 gemini_key: str = "", openai_key: str = "", anthropic_key: str = ""):
        self.provider = (provider or "gemini").lower()
        self.model = self._normalize_model(self.provider, model)
        self.gemini_key = gemini_key.strip().strip('"').strip("'") if gemini_key else ""
        self.openai_key = openai_key.strip().strip('"').strip("'") if openai_key else ""
        self.anthropic_key = anthropic_key.strip().strip('"').strip("'") if anthropic_key else ""

    def _normalize_model(self, provider: str, model: str) -> str:
        """Map model alias designations to valid endpoints."""
        m = (model or "").strip().lower()
        if provider == "gemini":
            if not m or m == "gemini" or "3.8" in m or "38" in m:
                return "gemini-3.8-flash"
            if "3-flash" in m or "3" in m:
                return "gemini-3.8-flash"
            return m or "gemini-3.8-flash"
        elif provider == "openai":
            if "mini" in m:
                return "gpt-4o-mini"
            return "gpt-4o"
        elif provider == "anthropic":
            if "haiku" in m:
                return "claude-3-5-haiku-20241022"
            return "claude-3-5-sonnet-20241022"
        return m or "gemini-3.8-flash"

    def has_valid_key(self) -> bool:
        if self.provider == "gemini":
            return bool(self.gemini_key and len(self.gemini_key.strip()) > 5)
        elif self.provider == "openai":
            return bool(self.openai_key and len(self.openai_key.strip()) > 5)
        elif self.provider == "anthropic":
            return bool(self.anthropic_key and len(self.anthropic_key.strip()) > 5)
        return False

    async def test_connection(self) -> Dict[str, Any]:
        """Verify API key and model connectivity with a tiny ping."""
        if not self.has_valid_key():
            return {
                "success": False,
                "error": f"API key for '{self.provider}' is empty or invalid. Please paste your key in the box below and click Save Settings."
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
                "message": f"Connected to {self.provider} ({self.model})! Response: {ans.strip()[:60]}"
            }
        except Exception as e:
            err_msg = str(e).strip() or repr(e)
            return {"success": False, "error": f"{type(e).__name__}: {err_msg}"}

    async def run_diagnosis(self, diagnostic_data: Dict[str, Any], user_notes: Optional[str] = None) -> Dict[str, Any]:
        """Send formatted diagnostic payload to the chosen AI provider."""
        if not self.has_valid_key():
            return {
                "success": False,
                "error": f"Missing or invalid API key for provider '{self.provider}'. Please enter your API key in the Settings & API Keys tab.",
                "analysis": None
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
                "analysis": analysis
            }
        except httpx.ReadTimeout:
            logger.error("AI API ReadTimeout after 180s")
            return {
                "success": False,
                "error": "Google Gemini took longer than 180 seconds to respond (ReadTimeout). Please try again or test your connection in Settings."
            }
        except httpx.HTTPStatusError as e:
            logger.error("AI API HTTP Error (%s): %s", e.response.status_code, e.response.text)
            return {"success": False, "error": f"Google API Error ({e.response.status_code}): {e.response.text}"}
        except Exception as e:
            logger.error("AI API Exception: %s", e, exc_info=True)
            err_msg = str(e).strip() or repr(e)
            return {"success": False, "error": f"Failed calling {self.provider}: {type(e).__name__} ({err_msg})"}

    def _streamline_telemetry(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Strip raw socket dumps to high-density diagnostic facts so LLMs respond rapidly."""
        rules = raw_data.get("rule_evaluations", {})
        split = rules.get("split_network", {})
        rf = rules.get("rf_coexistence", {})
        nq = rules.get("node_quality", {})
        ipv6 = rules.get("ipv6_routing", {})
        telemetry = raw_data.get("telemetry", {})

        # Extract clean border router summary
        routers_summary = []
        for r in split.get("all_discovered_routers", telemetry.get("border_routers", [])):
            routers_summary.append({
                "name": r.get("name"),
                "model": r.get("model"),
                "brand": r.get("brand"),
                "network_name": r.get("network_name"),
                "extended_pan_id": r.get("extended_pan_id"),
                "channel": r.get("channel"),
            })

        # Extract clean node summary
        matter_nodes = []
        for n in telemetry.get("matter_server", {}).get("nodes", []):
            matter_nodes.append({
                "node_id": n.get("node_id"),
                "product_name": n.get("product_name"),
                "vendor_name": n.get("vendor_name"),
                "available": n.get("available"),
                "rssi": n.get("rssi"),
            })

        return {
            "hardware_platform": raw_data.get("hardware_platform", "Home Assistant Green"),
            "health_score": raw_data.get("summary_score", 100),
            "thread_border_routers": routers_summary,
            "split_network_analysis": {
                "is_split_network": split.get("is_split_network", False),
                "distinct_network_count": split.get("distinct_network_count", 1),
                "found_nest_wifi_pro": split.get("found_nest_wifi_pro", False),
                "summary": split.get("summary", ""),
            },
            "rf_coexistence": {
                "thread_channel": rf.get("thread_channel"),
                "severity": rf.get("severity"),
                "overlapping_wifi_channel": rf.get("overlapping_wifi_channel"),
            },
            "ipv6_routing": {
                "has_thread_ula_route": ipv6.get("has_thread_ula_route", False),
                "detected_ula_prefixes": ipv6.get("detected_ula_prefixes", []),
            },
            "node_quality": {
                "total_nodes": nq.get("total_nodes", len(matter_nodes)),
                "offline_nodes": nq.get("offline_nodes", []),
                "weak_nodes": nq.get("weak_nodes", []),
            },
            "matter_over_thread_nodes": matter_nodes[:15],
        }

    def _build_prompt(self, data: Dict[str, Any], user_notes: Optional[str]) -> str:
        streamlined = self._streamline_telemetry(data)
        data_json = json.dumps(streamlined, indent=2)
        notes_section = f"\nUser Symptoms/Observations:\n{user_notes}\n" if user_notes else ""
        return (
            f"Please analyze the following telemetry collected from a Home Assistant Green system:\n\n"
            f"{notes_section}\n"
            f"```json\n{data_json}\n```\n\n"
            f"Diagnose all Matter and Thread issues and provide the complete structured troubleshooting report."
        )

    async def _call_gemini(self, prompt: str) -> str:
        """Call Google Gemini REST API with 180s timeout."""
        model_name = self.model or "gemini-3.8-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.gemini_key.strip()
        }
        params = {"key": self.gemini_key.strip()}
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2500
            }
        }

        async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT) as client:
            r = await client.post(url, json=payload, headers=headers, params=params)
            if r.status_code != 200:
                err_text = r.text
                try:
                    err_json = r.json()
                    err_text = err_json.get("error", {}).get("message", err_text)
                except Exception:
                    pass
                raise RuntimeError(f"Google Error {r.status_code}: {err_text}")

            res_data = r.json()
            candidates = res_data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return "No response text generated by Gemini."

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI Chat Completions REST API with 180s timeout."""
        model_name = self.model or "gpt-4o"
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_key.strip()}"
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 2500
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
        """Call Anthropic Messages REST API with 180s timeout."""
        model_name = self.model or "claude-3-5-sonnet-20241022"
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.anthropic_key.strip(),
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": model_name,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 2500,
            "temperature": 0.2
        }

        async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            res_data = r.json()
            content = res_data.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "")
            return "No response text generated by Anthropic."
