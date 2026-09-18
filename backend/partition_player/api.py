"""HTTP API (ADR 0001).

Jobs double as the score library: a finished job is a saved score with a name, reachable at /s/{id}.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings, load_settings
from .jobs import MAX_NAME, JobStore, Worker
from .pipeline.lyrics import edit as lyrics_edit
from .pipeline.lyrics import inject as lyrics_inject

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff", "image/bmp"}


class Rename(BaseModel):
    name: str = Field(max_length=MAX_NAME)


class Verses(BaseModel):
    verses: list[str] = Field(max_length=12)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = JobStore(settings)
    worker = Worker(store, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.clean_all()
        store.prune(settings.job_ttl_days)
        store.cap(settings.max_scores)
        worker.start()
        yield
        worker.stop()

    app = FastAPI(title="partition-player", version=__version__, lifespan=lifespan)
    app.state.settings, app.state.store, app.state.worker = settings, store, worker

    def load(job_id: str):
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "no such score")
        return job

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__, "engine": settings.engine, "fallback": settings.fallback_engine}

    @app.get("/api/jobs")
    def list_jobs(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
        return [j.to_dict() for j in store.list(limit)]

    @app.post("/api/jobs", status_code=202)
    async def create_job(file: UploadFile) -> dict:
        if file.content_type not in ALLOWED_TYPES:
            raise HTTPException(415, f"unsupported file type {file.content_type}; send a JPEG, PNG or WebP image")
        data = await file.read()
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"image larger than {settings.max_upload_mb} MB")
        if not data:
            raise HTTPException(400, "empty upload")
        job = store.create(file.filename or "upload.jpg", data)
        worker.submit(job.id)
        return job.to_dict()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        return load(job_id).to_dict()

    @app.patch("/api/jobs/{job_id}")
    def rename_job(job_id: str, body: Rename) -> dict:
        load(job_id)
        return store.rename(job_id, body.name).to_dict()

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str) -> None:
        if not store.delete(job_id):
            raise HTTPException(404, "no such score")

    @app.get("/api/jobs/{job_id}/score.musicxml")
    def get_score(job_id: str) -> FileResponse:
        job = load(job_id)
        if job.status != "done":
            raise HTTPException(409, f"job is {job.status}")
        return FileResponse(store.dir(job_id) / "score.musicxml", media_type="application/vnd.recordare.musicxml+xml",
                            headers={"Cache-Control": "no-cache"})  # the lyrics editor rewrites it in place

    def lyrics_state(job_id: str) -> dict:
        score = store.dir(job_id) / "score.musicxml"
        lyrics_file = store.dir(job_id) / "lyrics.json"
        placed = lyrics_inject.load(lyrics_file) if lyrics_file.exists() else []
        counts = lyrics_inject.onset_counts(score)
        order = [(m, o) for m, n in enumerate(counts) for o in range(n)]
        verses = [lyrics_edit.verse_text(placed, v, order) for v in range(1, max([p.verse for p in placed], default=0) + 1)]
        return {"verses": verses, "notes": len(order), "measures": counts,
                "syllables": [sum(1 for p in placed if p.verse == v) for v in range(1, len(verses) + 1)]}

    @app.get("/api/jobs/{job_id}/lyrics")
    def get_lyrics(job_id: str) -> dict:
        job = load(job_id)
        if job.status != "done":
            raise HTTPException(409, f"job is {job.status}")
        return lyrics_state(job_id)

    @app.patch("/api/jobs/{job_id}/lyrics")
    def save_lyrics(job_id: str, body: Verses) -> dict:
        """Replace the lyrics from verse texts (ADR 0004): the score's <lyric> elements are rewritten in
        place, chords and everything else stay, lyrics.json records the new placements."""
        job = load(job_id)
        if job.status != "done":
            raise HTTPException(409, f"job is {job.status}")
        score = store.dir(job_id) / "score.musicxml"
        lyrics_file = store.dir(job_id) / "lyrics.json"
        with store.lock:
            old = lyrics_inject.load(lyrics_file) if lyrics_file.exists() else []
            counts = lyrics_inject.onset_counts(score)
            order = [(m, o) for m, n in enumerate(counts) for o in range(n)]
            verses = [v for v in body.verses if v.strip()]
            placed = lyrics_edit.deal(verses, order, old)
            lyrics_inject.rewrite(score, placed)
            lyrics_inject.save(lyrics_file, placed, [], [])
        return lyrics_state(job_id)

    @app.get("/api/jobs/{job_id}/input")
    def get_input(job_id: str) -> FileResponse:
        p = store.input_path(job_id)
        if p is None:
            raise HTTPException(404, "no such score")
        return FileResponse(p)

    @app.get("/api/jobs/{job_id}/thumb.jpg")
    def get_thumb(job_id: str) -> FileResponse:
        p = store.thumb_path(job_id)
        if p is None:
            raise HTTPException(404, "no thumbnail")
        return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    frontend = Path(settings.frontend_dir)
    index = frontend / "index.html"
    if index.exists():
        if (frontend / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            """Serve a real file if there is one, else index.html so /s/{id} deep links work."""
            if path.startswith("api/"):
                raise HTTPException(404, "not found")
            candidate = (frontend / path).resolve() if path else index
            if path and candidate.is_file() and frontend.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
