"""Runtime settings, all overridable from the environment. See ADR 0001."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from .model.route import DEEPSEEK_LARGER, DEEPSEEK_MODEL, DEEPSEEK_URL, SONNET, Route


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("PP_DATA_DIR", "data")))
    engine: str = field(default_factory=lambda: os.environ.get("PP_ENGINE", "homr"))
    fallback_engine: str = field(default_factory=lambda: os.environ.get("PP_FALLBACK_ENGINE", "none"))
    audiveris_bin: str = field(default_factory=lambda: os.environ.get("PP_AUDIVERIS_BIN", "Audiveris"))
    job_timeout_s: int = field(default_factory=lambda: _env_int("PP_JOB_TIMEOUT_S", 300))
    job_ttl_days: int = field(default_factory=lambda: _env_int("PP_JOB_TTL_DAYS", 7))  # failed jobs only
    max_scores: int = field(default_factory=lambda: _env_int("PP_MAX_SCORES", 500))  # oldest scores beyond this are dropped
    max_upload_mb: int = field(default_factory=lambda: _env_int("PP_MAX_UPLOAD_MB", 25))
    max_side_px: int = field(default_factory=lambda: _env_int("PP_MAX_SIDE_PX", 2500))
    frontend_dir: Path = field(default_factory=lambda: Path(os.environ.get("PP_FRONTEND_DIR", "../frontend/dist")))
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("PP_ANTHROPIC_API_KEY", ""))  # the model pass (ADR 0010), off when empty
    anthropic_larger_model: str = field(default_factory=lambda: os.environ.get("PP_ANTHROPIC_LARGER_MODEL", SONNET))
    default_route: str = field(default_factory=lambda: os.environ.get("PP_MODEL_ROUTE", "anthropic"))
    deepseek_api_key: str = field(default_factory=lambda: os.environ.get("PP_DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(default_factory=lambda: os.environ.get("PP_DEEPSEEK_BASE_URL", DEEPSEEK_URL))
    deepseek_model: str = field(default_factory=lambda: os.environ.get("PP_DEEPSEEK_MODEL", DEEPSEEK_MODEL))
    deepseek_larger_model: str = field(default_factory=lambda: os.environ.get("PP_DEEPSEEK_LARGER_MODEL", DEEPSEEK_LARGER))
    deepseek_vision: bool = field(default_factory=lambda: os.environ.get("PP_DEEPSEEK_VISION", "").lower() in ("1", "true", "yes"))

    @property
    def model_routes(self) -> dict[str, Route]:
        """The model routes (ADR 0010) by name: the Anthropic preset keyed by PP_ANTHROPIC_API_KEY and the
        DeepSeek preset keyed by PP_DEEPSEEK_API_KEY. A route with no key is off."""
        return {"anthropic": replace(Route.anthropic(self.anthropic_api_key), larger_model=self.anthropic_larger_model),
                "deepseek": Route.deepseek(self.deepseek_api_key, self.deepseek_model, self.deepseek_base_url, self.deepseek_vision, self.deepseek_larger_model)}

    model_max_spans: int = field(default_factory=lambda: _env_int("PP_MODEL_MAX_SPANS", 10))  # spans per model pass on the server's key (ADR 0010); a visitor's own key is not capped

    @property
    def model_route(self) -> Route:
        """The route used when a request names none (PP_MODEL_ROUTE, `anthropic` unless set)."""
        return self.model_routes.get(self.default_route) or self.model_routes["anthropic"]

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"


def load_settings() -> Settings:
    return Settings()
