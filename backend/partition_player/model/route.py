"""One model route (ADR 0010, decision 9): base URL, key, model name, and whether it can read images.

The wire format is the Anthropic Messages API, which Anthropic and DeepSeek's compatible endpoint both speak.
A route with no key is disabled: every feature that needs a model stays off.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, replace

ANTHROPIC_URL = "https://api.anthropic.com"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-5-20250929"  # the larger model a failed answer escalates to (ticket 08)
DEEPSEEK_URL = "https://api.deepseek.com/anthropic"  # DeepSeek's Anthropic-compatible endpoint
DEEPSEEK_MODEL = "deepseek-flash"
DEEPSEEK_LARGER = "deepseek-v4-pro"
NO_VISION = "this route cannot read images"


def image_type(data: bytes) -> str | None:
    """The media type of a PNG, JPEG or WebP picture by its first bytes, or None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True)
class Route:
    base_url: str
    api_key: str
    model: str
    vision: bool = True
    larger_model: str = ""   # the model a failed validation and "Try harder" go to; empty means there is none

    @classmethod
    def anthropic(cls, api_key: str, model: str = HAIKU, larger_model: str = SONNET) -> "Route":
        return cls(ANTHROPIC_URL, api_key, model, vision=True, larger_model=larger_model)

    def larger(self) -> "Route | None":
        """The same route asking its larger model, or None when it has none (or is already on it)."""
        if not self.larger_model or self.larger_model == self.model:
            return None
        return replace(self, model=self.larger_model)

    @classmethod
    def deepseek(cls, api_key: str, model: str = DEEPSEEK_MODEL, base_url: str = DEEPSEEK_URL, vision: bool = False, larger_model: str = DEEPSEEK_LARGER) -> "Route":
        """DeepSeek through its Anthropic-compatible API. No vision by default: its larger model replaces
        images with a placeholder, so image spans stay off unless the operator says the model can see."""
        return cls(base_url, api_key, model, vision=vision, larger_model=larger_model)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def complete(self, text: str, image_png: bytes | None = None, max_tokens: int = 400, client=None) -> str:
        """Send one user message (an optional picture, then text) and return the reply text."""
        if image_png is not None and not self.vision:
            raise ValueError(NO_VISION)
        if client is None:
            import httpx

            client = httpx.Client()
        content: list[dict] = []
        if image_png is not None:
            content.append({"type": "image", "source": {"type": "base64", "media_type": image_type(image_png) or "image/png", "data": base64.b64encode(image_png).decode()}})
        content.append({"type": "text", "text": text})
        r = client.post(
            self.base_url.rstrip("/") + "/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]},
            timeout=60.0,
        )
        r.raise_for_status()
        return "".join(block.get("text", "") for block in r.json().get("content", []))


def image_refusal(route: Route, spans: list[dict]) -> str | None:
    """The reason a pass cannot run on this route: a span needs a crop or picture and the route cannot see."""
    if not route.vision and any(s.get("needs_image") for s in spans):
        return f"{NO_VISION}: pick a route with vision, or give the words as typed text"
    return None
