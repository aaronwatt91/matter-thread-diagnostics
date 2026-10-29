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
1. MULTI-BORDER ROUTER SYNC (SPLIT THREAD NETWORKS):
   - Apple TV 4K / HomePod mini and Home Assistant (SkyConnect/Connect ZBT-1) or Google Nest Hub must share the identical Extended PAN ID (XPAN), Network Key, and Channel.
   - If they have differing Extended PAN IDs, nodes commissioned through Apple/Google cannot talk to HA without sync.
2. RF INTERFERENCE (Wi-Fi 2.4GHz vs Thread 802.15.4):
   - Thread channels 11-26: Thread Ch 11 overlaps Wi-Fi Ch 1; Ch 17-19 overlaps Wi-Fi Ch 6; Ch 22-24 overlaps Wi-Fi Ch 11.
   - Thread Ch 25 is ideal.
   - Note: USB 3.0 ports emit wideband RF noise at 2.4 GHz. SkyConnect / Thread dongles must always use a 1-meter USB extension cable away from HA Green's chassis!
3. IPv6 ROUTING & MULTICAST (ULA, RIO, mDNS):
   - Matter-over-Thread requires IPv6. Border Routers advertise Route Information Options (RIO) for Thread mesh prefixes (fd00::/8).
   - If Wi-Fi routers (UniFi, Omada, Eero, Asus) have "Block LAN to WLAN Multicast", "IGMP Snooping" without MLD snooping, or drop ICMPv6 RAs, HA Green loses routes to Thread devices.
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


class AIDiagnosticEngine:
    def __init__(self, provider: str = "gemini", model: str = "gemini-2.0-flash",
                 gemini_key: str = "", openai_key: str = "", anthropic_key: str = ""):
        self.provider = provider.lower()
        self.model = model
        self.gemini_key = gemini_key
        self.openai_key = openai_key
        self.anthropic_key = anthropic_key

    def has_valid_key(self) -> bool:
        if self.provider == "gemini":
            return bool(self.gemini_key and len(self.gemini_key.strip()) > 5)
        elif self.provider == "openai":
            return bool(self.openai_key and len(self.openai_key.strip()) > 5)
        elif self.provider == "anthropic":
            return bool(self.anthropic_key and len(self.anthropic_key.strip()) > 5)
        return False

    async def run_diagnosis(self, diagnostic_data: Dict[str, Any], user_notes: Optional[str] = None) -> Dict[str, Any]:
        """Send formatted diagnostic payload to the chosen AI provider."""
        if not self.has_valid_key():
            return {
                "success": False,
                "error": f"Missing or invalid API key for provider '{self.provider}'. Please configure your API key in settings.",
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
        except httpx.HTTPStatusError as e:
            logger.error("AI API HTTP Error (%s): %s", e.response.status_code, e.response.text)
            return {"success": False, "error": f"AI API Error ({e.response.status_code}): {e.response.text}"}
        except Exception as e:
            logger.error("AI API Exception: %s", e, exc_info=True)
            return {"success": False, "error": f"Failed calling {self.provider}: {str(e)}"}

    def _build_prompt(self, data: Dict[str, Any], user_notes: Optional[str]) -> str:
        data_json = json.dumps(data, indent=2)
        notes_section = f"\nUser Symptoms/Observations:\n{user_notes}\n" if user_notes else ""
        return (
            f"Please analyze the following telemetry collected from a Home Assistant Green system:\n\n"
            f"{notes_section}\n"
            f"```json\n{data_json}\n```\n\n"
            f"Diagnose all Matter and Thread issues and provide the complete structured troubleshooting report."
        )

    async def _call_gemini(self, prompt: str) -> str:
        """Call Google Gemini REST API."""
        model_name = self.model or "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_key.strip()}"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 3000
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            r.raise_for_status()
            res_data = r.json()
            candidates = res_data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return "No response text generated by Gemini."

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI Chat Completions REST API."""
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
            "max_tokens": 3000
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
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
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": model_name,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 3000,
            "temperature": 0.2
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            res_data = r.json()
            content = res_data.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "")
            return "No response text generated by Anthropic."
