"""Configuration loader — pulls endpoints, base URL and limits from env vars.

Customers can override every value via `app.yaml` env entries when deploying.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class AppConfig:
    base_url: str
    endpoints: list[dict] = field(default_factory=list)
    max_tokens: int = 1024
    history_db_path: str = "/tmp/crystal_chat_history.db"


def _parse_endpoints(raw: str) -> list[dict]:
    """Endpoints can be provided as JSON or a comma-separated list of names.

    JSON form:  [{"name":"gpt","label":"OpenAI GPT"},{"name":"claude","label":"Anthropic Claude"}]
    Short form: "gpt,claude"  -> labels default to the names
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return [{"name": n.strip(), "label": n.strip()} for n in raw.split(",") if n.strip()]


def load_config() -> AppConfig:
    base_url = os.environ.get(
        "AI_GATEWAY_BASE_URL",
        "https://adb-520209755093735.15.azuredatabricks.net/ai-gateway/mlflow/v1",
    )
    endpoints_raw = os.environ.get("AI_GATEWAY_ENDPOINTS", "gpt,claude")
    endpoints = _parse_endpoints(endpoints_raw)
    if not endpoints:
        endpoints = [{"name": "gpt", "label": "gpt"}, {"name": "claude", "label": "claude"}]

    max_tokens = int(os.environ.get("AI_GATEWAY_MAX_TOKENS", "1024"))
    history_db_path = os.environ.get("CHAT_HISTORY_DB_PATH", "/tmp/crystal_chat_history.db")

    return AppConfig(
        base_url=base_url.rstrip("/"),
        endpoints=endpoints,
        max_tokens=max_tokens,
        history_db_path=history_db_path,
    )
