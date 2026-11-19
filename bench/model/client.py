"""The HTTP client handed to Route.complete(client=...): meters tokens and time, records and replays answers.

Route.complete only calls `client.post(url, headers=, json=, timeout=)` and reads `.raise_for_status()` / `.json()`,
so a replacement needs no change to the backend. Three sources of answers:

  live    a real httpx.Client; with `record` set, every answer is also stored in that JSON file
  replay  answers read from a recorded file (key = sha1 of model + prompt); a miss is an error, never a guess
  script  a function (model, prompt) -> reply text, for the offline harness test
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

# $ per million tokens (input, output). Only what is known; any other model reports cost as n/a unless --price is given.
PRICES = {"haiku": (1.0, 5.0), "sonnet": (3.0, 15.0)}


def price_of(model: str, extra: dict[str, tuple[float, float]] | None = None) -> tuple[float, float] | None:
    table = {**PRICES, **(extra or {})}
    for key, p in table.items():
        if key in model:
            return p
    return None


def key_of(model: str, prompt: str) -> str:
    return hashlib.sha1((model + "\n" + prompt).encode()).hexdigest()


class _Reply:
    def __init__(self, body: dict):
        self.body = body

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self.body


class Meter:
    """Per model: calls, tokens in and out, seconds spent waiting."""

    def __init__(self) -> None:
        self.by_model: dict[str, dict] = {}

    def add(self, model: str, tin: int, tout: int, seconds: float) -> None:
        m = self.by_model.setdefault(model, {"calls": 0, "tin": 0, "tout": 0, "seconds": 0.0})
        m["calls"] += 1
        m["tin"] += tin
        m["tout"] += tout
        m["seconds"] += seconds

    def seconds(self) -> float:
        return sum(m["seconds"] for m in self.by_model.values())

    def cost(self, extra_prices=None) -> float | None:
        """Dollars, or None when any model used has no known price."""
        total = 0.0
        for model, m in self.by_model.items():
            p = price_of(model, extra_prices)
            if p is None:
                return None
            total += m["tin"] * p[0] / 1e6 + m["tout"] * p[1] / 1e6
        return total


class MeteredClient:
    def __init__(self, meter: Meter, live=None, recorded: dict | None = None, script=None, record_to: Path | None = None):
        self.meter, self.live, self.recorded, self.script, self.record_to = meter, live, recorded, script, record_to
        self.stored: dict = dict(recorded or {})

    def post(self, url, headers=None, json=None, timeout=None):  # noqa: A002  (the httpx signature)
        model = json["model"]
        prompt = json["messages"][0]["content"][-1]["text"]
        started = time.perf_counter()
        if self.script is not None:
            text = self.script(model, prompt)
            body = {"content": [{"type": "text", "text": text}], "usage": {"input_tokens": len(prompt) // 3, "output_tokens": len(text) // 3}}
        elif self.live is not None:
            r = self.live.post(url, headers=headers, json=json, timeout=timeout)
            r.raise_for_status()
            body = r.json()
            if self.record_to is not None:
                self.stored[key_of(model, prompt)] = body
                self.record_to.write_text(self._dump())
        else:
            try:
                body = self.stored[key_of(model, prompt)]
            except KeyError:
                raise LookupError("no recorded answer for this prompt") from None
        u = body.get("usage", {})
        self.meter.add(model, int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0)), time.perf_counter() - started)
        return _Reply(body)

    def _dump(self) -> str:
        import json as _json
        return _json.dumps(self.stored, indent=1)


def load_recording(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}
