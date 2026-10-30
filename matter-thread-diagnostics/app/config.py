"""
Configuration manager for Matter & Thread AI Diagnostics Add-on.
Loads from Home Assistant Supervisor (/data/options.json) and persists
custom user settings across updates in /data/matter_ai_settings.json.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger("matter_thread_ai.config")

OPTIONS_FILE = os.environ.get("HA_OPTIONS_PATH", "/data/options.json")
PERSISTENT_SETTINGS_FILES = [
    "/data/matter_ai_settings.json",
    os.path.join(os.path.dirname(__file__), "matter_ai_settings.json")
]


class AppConfig(BaseModel):
    ai_provider: str = "gemini"  # gemini, openai, anthropic
    ai_model: str = "gemini-3.8-flash"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    matter_server_url: str = "ws://core-matter-server:5580/ws"
    otbr_url: str = "http://core-openthread-border-router:8081"
    log_level: str = "info"
    target_thread_network: str = ""
    supervisor_token: Optional[str] = None
    supervisor_url: str = "http://supervisor"
    ha_url: str = "http://supervisor/core"

    @classmethod
    def load(cls) -> "AppConfig":
        data: Dict[str, Any] = {}

        # 1. Load from Home Assistant Supervisor options if present
        if os.path.exists(OPTIONS_FILE):
            try:
                with open(OPTIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info("Loaded options from Supervisor: %s", OPTIONS_FILE)
            except Exception as e:
                logger.error("Failed to read options file %s: %s", OPTIONS_FILE, e)

        # 2. Overlay with custom user settings saved from the UI
        for pfile in PERSISTENT_SETTINGS_FILES:
            if os.path.exists(pfile):
                try:
                    with open(pfile, "r", encoding="utf-8") as f:
                        ui_data = json.load(f)
                        data.update({k: v for k, v in ui_data.items() if v is not None and v != ""})
                        logger.info("Loaded custom settings from: %s", pfile)
                    break
                except Exception as e:
                    logger.debug("Could not read %s: %s", pfile, e)

        # 3. Allow override from environment variables
        ai_provider = os.environ.get("AI_PROVIDER", data.get("ai_provider", "gemini"))
        ai_model = os.environ.get("AI_MODEL", data.get("ai_model", "gemini-3.8-flash"))
        gemini_api_key = os.environ.get("GEMINI_API_KEY", data.get("gemini_api_key", ""))
        openai_api_key = os.environ.get("OPENAI_API_KEY", data.get("openai_api_key", ""))
        anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", data.get("anthropic_api_key", ""))
        matter_server_url = os.environ.get("MATTER_SERVER_URL", data.get("matter_server_url", "ws://core-matter-server:5580/ws"))
        otbr_url = os.environ.get("OTBR_URL", data.get("otbr_url", "http://core-openthread-border-router:8081"))
        log_level = os.environ.get("LOG_LEVEL", data.get("log_level", "info"))
        target_thread_network = os.environ.get("TARGET_THREAD_NETWORK", data.get("target_thread_network", ""))

        supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
        supervisor_url = os.environ.get("SUPERVISOR_URL", "http://supervisor")
        ha_url = os.environ.get("HA_URL", f"{supervisor_url}/core")

        # Clean keys
        gemini_api_key = (gemini_api_key or "").strip().strip('"').strip("'")
        openai_api_key = (openai_api_key or "").strip().strip('"').strip("'")
        anthropic_api_key = (anthropic_api_key or "").strip().strip('"').strip("'")

        return cls(
            ai_provider=ai_provider,
            ai_model=ai_model,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            matter_server_url=matter_server_url,
            otbr_url=otbr_url,
            log_level=log_level,
            target_thread_network=target_thread_network,
            supervisor_token=supervisor_token,
            supervisor_url=supervisor_url,
            ha_url=ha_url,
        )

    def save_options(self, updates: Dict[str, Any]) -> None:
        """Save updated options to memory and persist to disk."""
        for k, v in updates.items():
            if hasattr(self, k) and v is not None:
                if isinstance(v, str):
                    v = v.strip().strip('"').strip("'")
                setattr(self, k, v)

        # Write to first writable persistent location
        data_to_save = self.model_dump(exclude={"supervisor_token", "supervisor_url", "ha_url"})
        saved = False
        for pfile in PERSISTENT_SETTINGS_FILES:
            try:
                os.makedirs(os.path.dirname(pfile), exist_ok=True)
                with open(pfile, "w", encoding="utf-8") as f:
                    json.dump(data_to_save, f, indent=2)
                logger.info("Persisted user settings to %s", pfile)
                saved = True
                break
            except Exception as e:
                logger.debug("Could not write settings to %s: %s", pfile, e)

        if not saved:
            logger.warning("Could not persist settings to disk, keeping in memory.")


# Global singleton
config = AppConfig.load()
