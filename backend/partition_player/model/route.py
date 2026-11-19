"""One model route (ADR 0010, decision 9): base URL, key, model name, and whether it can read images.

The wire format is the Anthropic Messages API, which Anthropic and DeepSeek's compatible endpoint both speak.
A route with no key is disabled: every feature that needs a model stays off.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass

ANTHROPIC_URL = "https://api.anthropic.com"
HAIKU = "claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class Route:
    base_url: str
    api_key: str
    model: str
    vision: bool = True

    @classmethod
    def anthropic(cls, api_key: str, model: str = HAIKU) -> "Route":
        return cls(ANTHROPIC_URL, api_key, model, vision=True)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def complete(self, text: str, image_png: bytes | None = None, max_tokens: int = 400, client=None) -> str:
        """Send one user message (an optional PNG, then text) and return the reply text."""
        if image_png is not None and not self.vision:
            raise ValueError("this route cannot read images")
        if client is None:
            import httpx

            client = httpx.Client()
        content: list[dict] = []
        if image_png is not None:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image_png).decode()}})
        content.append({"type": "text", "text": text})
        r = client.post(
            self.base_url.rstrip("/") + "/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]},
            timeout=60.0,
        )
        r.raise_for_status()
        return "".join(block.get("text", "") for block in r.json().get("content", []))
