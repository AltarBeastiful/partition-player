"""HTTP API (ADR 0001): POST /api/jobs, GET /api/jobs/{id}, GET /api/jobs/{id}/score.musicxml."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings, load_settings
from .jobs import JobStore, Worker

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff", "image/bmp"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = JobStore(settings)
    worker = Worker(store, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.prune(settings.job_ttl_days)
        worker.start()
        yield
        worker.stop()

    app = FastAPI(title="partition-player", version=__version__, lifespan=lifespan)
    app.state.settings, app.state.store, app.state.worker = settings, store, worker

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__, "engine": settings.engine, "fallback": settings.fallback_engine}

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
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        return job.to_dict()

    @app.get("/api/jobs/{job_id}/score.musicxml")
    def get_score(job_id: str) -> FileResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        if job.status != "done":
            raise HTTPException(409, f"job is {job.status}")
        return FileResponse(store.dir(job_id) / "score.musicxml", media_type="application/vnd.recordare.musicxml+xml")

    @app.get("/api/jobs/{job_id}/input")
    def get_input(job_id: str) -> FileResponse:
        p = store.input_path(job_id)
        if p is None:
            raise HTTPException(404, "no such job")
        return FileResponse(p)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    frontend = Path(settings.frontend_dir)
    if (frontend / "index.html").exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
