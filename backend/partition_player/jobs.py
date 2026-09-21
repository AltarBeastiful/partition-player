"""Filesystem-backed job store and a single worker thread (ADR 0001).

Layout while running: <data>/jobs/<id>/{input.<ext>, status.json, preprocessed.png, <engine>/..., score.musicxml}
After success only {status.json, result.json, score.musicxml, thumb.jpg, lyrics.json} and the editor's files
{original.musicxml, review.json, review.webp, layout.json} are kept (about 350 KB instead of 20 MB, ADR 0005);
after failure the input and the engine error logs stay until `prune` drops the job.
"""
from __future__ import annotations

import json
import logging
import queue
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Settings
from .pipeline.run import recognize

log = logging.getLogger(__name__)

TERMINAL = {"done", "failed"}
MAX_NAME = 120
KEEP_DONE = {"status.json", "result.json", "score.musicxml", "thumb.jpg", "lyrics.json",
             "original.musicxml", "review.json", "review.webp", "layout.json", "evidence.json"}
KEEP_FAILED_SUFFIXES = (".error.log",)


def default_name(input_name: str) -> str:
    stem = Path(input_name).stem.replace("_", " ").replace("-", " ").strip()
    return clean_name(stem) or "Untitled score"


def clean_name(name: str) -> str:
    return " ".join(name.split())[:MAX_NAME]


@dataclass
class Job:
    id: str
    status: str = "queued"  # queued | preprocessing | recognizing | postprocessing | done | failed
    message: str = "Waiting for a free worker"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    input_name: str = ""
    name: str = ""  # user-facing title, editable; defaults to the upload's file name
    error: str | None = None
    result: dict | None = None
    edited_at: str | None = None  # last save from the editor (ADR 0005)

    def to_dict(self) -> dict:
        return asdict(self)


class JobStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.jobs_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def dir(self, job_id: str) -> Path:
        return self.root / job_id

    @property
    def lock(self) -> threading.Lock:
        """Guards status.json writes and, for the lyrics editor, the score rewrite."""
        return self._lock

    def create(self, input_name: str, data: bytes) -> Job:
        job_id = uuid.uuid4().hex[:12]
        d = self.dir(job_id)
        d.mkdir(parents=True)
        ext = Path(input_name).suffix.lower() or ".bin"
        (d / f"input{ext}").write_bytes(data)
        job = Job(id=job_id, input_name=input_name, name=default_name(input_name))
        self.save(job)
        return job

    def list(self, limit: int = 50) -> list[Job]:
        """Newest first. Every job is listed, so an in-progress or failed one shows up in the library too."""
        jobs = [j for d in self.root.iterdir() if (j := self.get(d.name)) is not None]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def rename(self, job_id: str, name: str) -> Job | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.name = clean_name(name) or default_name(job.input_name)
        self.save(job)
        return job

    def delete(self, job_id: str) -> bool:
        d = self.dir(job_id)
        if not (d / "status.json").exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True

    def thumb_path(self, job_id: str) -> Path | None:
        p = self.dir(job_id) / "thumb.jpg"
        return p if p.exists() else None

    def input_path(self, job_id: str) -> Path | None:
        for p in self.dir(job_id).glob("input.*"):
            return p
        return None

    def save(self, job: Job) -> None:
        job.updated_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            tmp = self.dir(job.id) / "status.json.tmp"
            tmp.write_text(json.dumps(job.to_dict(), indent=2))
            tmp.replace(self.dir(job.id) / "status.json")

    def get(self, job_id: str) -> Job | None:
        p = self.dir(job_id) / "status.json"
        if not p.exists():
            return None
        job = Job(**json.loads(p.read_text()))
        if not job.name:  # jobs written before names existed
            job.name = default_name(job.input_name)
        return job

    def unfinished(self) -> list[Job]:
        jobs = []
        for d in sorted(self.root.iterdir()):
            job = self.get(d.name)
            if job and job.status not in TERMINAL:
                jobs.append(job)
        return jobs

    def clean(self, job: Job) -> None:
        """Delete what a finished job no longer needs, so the library costs kilobytes per score, not megabytes."""
        d = self.dir(job.id)
        for p in list(d.iterdir()):
            if job.status == "done":
                keep = p.name in KEEP_DONE
            else:
                keep = p.name == "status.json" or p.name.startswith("input.") or p.name.endswith(KEEP_FAILED_SUFFIXES)
            if keep:
                continue
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)

    def clean_all(self) -> None:
        for job in self.list(limit=10**6):
            if job.status in TERMINAL:
                self.clean(job)

    def cap(self, max_scores: int) -> int:
        """Keep at most `max_scores` finished scores; the oldest go first."""
        done = [j for j in self.list(limit=10**6) if j.status == "done"]
        removed = 0
        for job in done[max_scores:]:
            log.info("dropping old score %s (%s) to stay under PP_MAX_SCORES=%d", job.id, job.name, max_scores)
            removed += int(self.delete(job.id))
        return removed

    def prune(self, ttl_days: int) -> int:
        """Drop failed jobs older than the TTL. Finished scores are the user's library and stay until deleted."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
        removed = 0
        for d in self.root.iterdir():
            job = self.get(d.name)
            if job and job.status == "failed" and datetime.fromisoformat(job.created_at) < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        return removed


class Worker:
    """One thread, one job at a time: a recognition already uses every core the VPS has."""

    def __init__(self, store: JobStore, settings: Settings):
        self.store = store
        self.settings = settings
        self.q: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="pp-worker", daemon=True)
        self._stop = threading.Event()

    def start(self) -> None:
        for job in self.store.unfinished():  # re-queue whatever a restart interrupted
            job.status, job.message = "queued", "Re-queued after restart"
            self.store.save(job)
            self.q.put(job.id)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def submit(self, job_id: str) -> None:
        self.q.put(job_id)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            self._process(job_id)

    def _process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        image = self.store.input_path(job_id)
        if job is None or image is None:
            return

        def progress(stage: str, message: str) -> None:
            job.status, job.message = stage, message
            self.store.save(job)

        started = time.monotonic()
        try:
            recognize(image, self.store.dir(job_id), self.settings, progress)
            info = json.loads((self.store.dir(job_id) / "result.json").read_text())
            job.status, job.message = "done", "Score ready"
            job.result = {"engine": info.get("engine"), "stats": info.get("stats"), "seconds": round(time.monotonic() - started, 1)}
        except Exception as e:  # noqa: BLE001  (the job must record any failure)
            log.exception("job %s failed", job_id)
            job.status, job.message, job.error = "failed", "Recognition failed", str(e)
        self.store.save(job)
        self.store.clean(job)
        self.store.prune(self.settings.job_ttl_days)
        self.store.cap(self.settings.max_scores)
