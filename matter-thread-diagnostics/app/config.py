"""
Configuration manager for Matter & Thread AI Diagnostics Add-on.
Loads from /data/options.json (Home Assistant) or environment variables.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger("matter_thread_ai.config")

OPTIONS_FILE = os.environ.get("HA_OPTIONS_PATH", "/data/options.json")


class AppConfig(BaseModel):
    ai_provider: str = "gemini"  # gemini, openai, anthropic
    ai_model: str = "gemini-2.0-flash"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    matter_server_url: str = "ws://core-matter-server:5580/ws"
    otbr_url: str = "http://core-openthread-border-router:8081"
    log_level: str = "info"
    supervisor_token: Optional[str] = None
    supervisor_url: str = "http://supervisor"
    ha_url: str = "http://supervisor/core"

    @classmethod
    def load(cls) -> "AppConfig":
        data: Dict[str, Any] = {}
        if os.path.exists(OPTIONS_FILE):
            try:
                with open(OPTIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info("Loaded options from %s", OPTIONS_FILE)
            except Exception as e:
                logger.error("Failed to read options file %s: %s", OPTIONS_FILE, e)

        # Allow override from environment variables
        ai_provider = os.environ.get("AI_PROVIDER", data.get("ai_provider", "gemini"))
        ai_model = os.environ.get("AI_MODEL", data.get("ai_model", "gemini-2.0-flash"))
        gemini_api_key = os.environ.get("GEMINI_API_KEY", data.get("gemini_api_key", ""))
        openai_api_key = os.environ.get("OPENAI_API_KEY", data.get("openai_api_key", ""))
        anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", data.get("anthropic_api_key", ""))
        matter_server_url = os.environ.get("MATTER_SERVER_URL", data.get("matter_server_url", "ws://core-matter-server:5580/ws"))
        otbr_url = os.environ.get("OTBR_URL", data.get("otbr_url", "http://core-openthread-border-router:8081"))
        log_level = os.environ.get("LOG_LEVEL", data.get("log_level", "info"))

        supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
        supervisor_url = os.environ.get("SUPERVISOR_URL", "http://supervisor")
        ha_url = os.environ.get("HA_URL", f"{supervisor_url}/core")

        return cls(
            ai_provider=ai_provider,
            ai_model=ai_model,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            matter_server_url=matter_server_url,
            otbr_url=otbr_url,
            log_level=log_level,
            supervisor_token=supervisor_token,
            supervisor_url=supervisor_url,
            ha_url=ha_url,
        )

    def save_options(self, updates: Dict[str, Any]) -> None:
        """Save updated options to memory and file if permitted."""
        for k, v in updates.items():
            if hasattr(self, k) and v is not None:
                setattr(self, k, v)
        try:
            if os.path.exists(os.path.dirname(OPTIONS_FILE)):
                with open(OPTIONS_FILE, "w", encoding="utf-8") as f:
                    data = self.model_dump(exclude={"supervisor_token", "supervisor_url", "ha_url"})
                    json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Could not persist options to disk (read-only or local dev): %s", e)


# Global singleton
config = AppConfig.load()
