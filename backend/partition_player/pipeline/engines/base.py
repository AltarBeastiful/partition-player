from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class EngineError(RuntimeError):
    """The engine failed; `log` carries whatever it printed."""

    def __init__(self, message: str, log: str = ""):
        super().__init__(message)
        self.log = log


class Engine(ABC):
    name: str = "base"

    def __init__(self, timeout_s: int = 300):
        self.timeout_s = timeout_s

    @abstractmethod
    def recognize(self, image: Path, out_dir: Path) -> Path:
        """Run OMR on `image`; return the path of the MusicXML written under `out_dir`."""

    def _run(self, cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> str:
        """Run a subprocess with the engine timeout; return combined output; raise EngineError on failure."""
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=self.timeout_s, check=False
            )
        except subprocess.TimeoutExpired as e:
            raise EngineError(f"{self.name} timed out after {self.timeout_s}s", (e.stdout or "") + (e.stderr or "")) from e
        except FileNotFoundError as e:
            raise EngineError(f"{self.name} executable not found: {cmd[0]}") from e
        log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            raise EngineError(f"{self.name} exited with status {proc.returncode}", log)
        return log
