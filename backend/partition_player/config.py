"""Runtime settings, all overridable from the environment. See ADR 0001."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


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
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("PP_ANTHROPIC_API_KEY", ""))  # lyrics text polish (ADR 0004), off when empty

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"


def load_settings() -> Settings:
    return Settings()
