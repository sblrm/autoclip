"""Local FastAPI studio API with durable clip-review workflow."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, status
from pydantic import BaseModel, Field

from autoclip.web.studio_store import Job, StudioClip, StudioStore
from autoclip.web.store import Project


class ClipUpdate(BaseModel):
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, gt=0)
    title: str | None = None
    subtitle_config: dict[str, Any] | None = None
    selected_face_track_id: str | None = None
    tracking_status: str | None = None


class JobResponse(BaseModel):
    job_id: str


def create_studio_app(library_root: Path | None = None) -> FastAPI:
    """Build the local-only AutoClip studio API."""
    root = library_root or Path.home() / ".autoclip" / "projects"
    store = StudioStore(root)
    app = FastAPI(title="AutoClip Local Studio", version="0.2.0")
    app.state.store = store

    @app.post("/api/projects/import", response_model=Project, status_code=status.HTTP_201_CREATED)
    async def import_project(file: UploadFile = File(...)) -> Project:
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File name required")
        suffix = Path(file.filename).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(dir=root, suffix=suffix, delete=False) as incoming:
            incoming_path = Path(incoming.name)
            while chunk := await file.read(1024 * 1024):
                incoming.write(chunk)
        try:
            return store.create_from_upload(incoming_path, original_name=file.filename)
        finally:
            incoming_path.unlink(missing_ok=True)

    @app.get("/api/projects/{project_id}")
    def get_project_detail(project_id: str) -> dict[str, Any]:
        try:
            return {
                "project": store.get_project(project_id),
                "clips": store.list_clips(project_id),
                "jobs": _list_jobs(store, project_id),
            }
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    @app.post("/api/projects/{project_id}/analyze", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
    def analyze_project(project_id: str) -> JobResponse:
        try:
            job = store.create_job(project_id, "analysis", "Waiting to analyze video")
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        return JobResponse(job_id=job.id)

    @app.patch("/api/clips/{clip_id}", response_model=StudioClip)
    def edit_clip(clip_id: str, update: ClipUpdate) -> StudioClip:
        try:
            changes = update.model_dump(exclude_unset=True)
            return store.update_clip(clip_id, **changes)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    @app.post("/api/clips/{clip_id}/tracking-preview", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
    def create_tracking_preview(clip_id: str) -> JobResponse:
        try:
            clip = store.get_clip(clip_id)
            job = store.create_job(clip.project_id, "tracking_preview", "Waiting to render tracking preview")
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        return JobResponse(job_id=job.id)

    @app.post("/api/clips/{clip_id}/approve", response_model=StudioClip)
    def approve_clip(clip_id: str) -> StudioClip:
        try:
            return store.approve_clip(clip_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    @app.get("/api/jobs/{job_id}", response_model=Job)
    def get_job(job_id: str) -> Job:
        try:
            return store.get_job(job_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    @app.websocket("/api/jobs/{job_id}/events")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        try:
            job = store.get_job(job_id)
        except KeyError:
            await websocket.send_json({"job_id": job_id, "stage": "failed", "progress": 1.0, "message": "Job not found", "error": "not_found"})
        else:
            await websocket.send_json(_job_event(job))
        await websocket.close()

    return app


def _list_jobs(store: StudioStore, project_id: str) -> list[Job]:
    with store._connect() as connection:  # noqa: SLF001 - local store query boundary
        rows = connection.execute(
            "SELECT id, project_id, kind, stage, progress, message, error FROM jobs WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    return [Job(**dict(row)) for row in rows]


def _job_event(job: Job) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "stage": job.stage,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
    }


app = create_studio_app()
