"""Configuration loader — pulls endpoints, base URL and limits from env vars.

Customers can override every value via `app.yaml` env entries when deploying.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class AppConfig:
    base_url: str
    responses_base_url: str
    endpoints: list[dict] = field(default_factory=list)
    max_tokens: int = 1024
    history_db_path: str = "/tmp/crystal_chat_history.db"
    # Image-generation tool tuning. We stream the image (partial_images), which
    # avoids the synchronous ~640 KB response cap, but still request a compressed
    # format so the stored/rendered payload stays small.
    image_size: str = "1024x1024"
    image_format: str = "webp"
    image_quality: str = "medium"
    image_compression: int = 60
    image_partial_images: int = 2

    def image_model_for(self, endpoint_name: str) -> str | None:
        """Serving-endpoint name used for image generation on this route.

        The AI Gateway route (e.g. ``gpt``) is not a serving endpoint, so image
        generation must target a real OpenAI serving endpoint (e.g.
        ``databricks-gpt-5``) declared via ``"image_model"`` on the entry.
        """
        for ep in self.endpoints:
            if ep.get("name") == endpoint_name:
                return ep.get("image_model")
        return None

    def supports_images(self, endpoint_name: str) -> bool:
        """True if the named route has an ``image_model`` (OpenAI Responses API)."""
        return bool(self.image_model_for(endpoint_name))

    def image_tool(self) -> dict:
        """The image_generation tool spec (size/format/compression + streaming partials)."""
        return {
            "type": "image_generation",
            "size": self.image_size,
            "output_format": self.image_format,
            "quality": self.image_quality,
            "output_compression": self.image_compression,
            "partial_images": self.image_partial_images,
        }


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

    image_size = os.environ.get("AI_GATEWAY_IMAGE_SIZE", "1024x1024")
    image_format = os.environ.get("AI_GATEWAY_IMAGE_FORMAT", "webp")
    image_quality = os.environ.get("AI_GATEWAY_IMAGE_QUALITY", "medium")
    image_compression = int(os.environ.get("AI_GATEWAY_IMAGE_COMPRESSION", "60"))
    image_partial_images = int(os.environ.get("AI_GATEWAY_IMAGE_PARTIALS", "2"))

    # The Responses API (image generation, web search, etc.) is served from the
    # AI Gateway OpenAI-compatible path (/ai-gateway/openai/v1), NOT the mlflow
    # path. Derive it from the same workspace host unless explicitly overridden.
    responses_base_url = os.environ.get("AI_GATEWAY_RESPONSES_BASE_URL", "").strip()
    if not responses_base_url:
        parsed = urlparse(base_url)
        if parsed.scheme and parsed.netloc:
            responses_base_url = f"{parsed.scheme}://{parsed.netloc}/ai-gateway/openai/v1"
        else:
            responses_base_url = base_url

    return AppConfig(
        base_url=base_url.rstrip("/"),
        responses_base_url=responses_base_url.rstrip("/"),
        endpoints=endpoints,
        max_tokens=max_tokens,
        history_db_path=history_db_path,
        image_size=image_size,
        image_format=image_format,
        image_quality=image_quality,
        image_compression=image_compression,
        image_partial_images=image_partial_images,
    )
