"""Complete local HTTP/WebSocket server for the AutoClip browser studio."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from autoclip.web.full_store import FullStudioStore
from autoclip.web.rendering import TrackingService
from autoclip.web.runtime_jobs import SerialJobRunner
from autoclip.web.runtime_pipeline import StudioPipeline
from autoclip.web.runtime_store import Artifact, FaceTrackRecord
from autoclip.web.studio_store import Job, StudioClip
from autoclip.web.store import Project
from autoclip.web.tracking import get_tracker_capability

VIDEO_SUFFIXES = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}


class UrlImport(BaseModel):
    url: str


class ClipUpdate(BaseModel):
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, gt=0)
    title: str | None = None
    subtitle_config: dict[str, Any] | None = None
    selected_face_track_id: str | None = None
    tracking_status: str | None = None


class JobResponse(BaseModel):
    job_id: str


PipelineFactory = Callable[[FullStudioStore], Any]
TrackingFactory = Callable[[FullStudioStore], Any]


def create_studio_server(
    library_root: Path | None = None,
    *,
    pipeline_factory: PipelineFactory = StudioPipeline,
    tracking_factory: TrackingFactory = TrackingService,
) -> FastAPI:
    """Build the durable, local-only studio API and its single serial worker."""
    root = library_root or Path.home() / ".autoclip" / "projects"
    store = FullStudioStore(root)
    _mark_interrupted_jobs(store)
    runner = SerialJobRunner(store)
    pipeline = pipeline_factory(store)
    tracking = tracking_factory(store)
    app = FastAPI(title="AutoClip Local Studio", version="1.0.0")
    app.state.store = store
    app.state.runner = runner
    app.state.pipeline = pipeline
    app.state.tracking = tracking

    @app.on_event("shutdown")
    def shutdown_worker() -> None:
        runner.stop()

    @app.get("/api/runtime-health")
    def runtime_health() -> dict[str, Any]:
        return _runtime_health()

    @app.get("/api/projects", response_model=list[Project])
    def list_projects() -> list[Project]:
        return store.list_projects()

    @app.post("/api/projects/import", response_model=Project, status_code=status.HTTP_201_CREATED)
    async def import_project(file: UploadFile = File(...)) -> Project:
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File name required")
        suffix = Path(file.filename).suffix.lower()
        if suffix not in VIDEO_SUFFIXES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Upload a supported video file")
        with tempfile.NamedTemporaryFile(dir=root, suffix=suffix, delete=False) as incoming:
            incoming_path = Path(incoming.name)
            while chunk := await file.read(1024 * 1024):
                incoming.write(chunk)
        try:
            return store.create_from_upload(incoming_path, original_name=file.filename)
        finally:
            incoming_path.unlink(missing_ok=True)

    @app.post("/api/projects/from-url", response_model=Project, status_code=status.HTTP_201_CREATED)
    def import_url_project(body: UrlImport) -> Project:
        try:
            return store.create_from_url(body.url)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    @app.get("/api/projects/{project_id}")
    def project_detail(project_id: str) -> dict[str, Any]:
        try:
            return _project_detail(store, project_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    @app.post("/api/projects/{project_id}/analyze", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
    def analyze_project(project_id: str) -> JobResponse:
        try:
            job = store.create_job(project_id, "analysis", "Queued for local analysis")
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        runner.submit(job, lambda report: pipeline.analyze(project_id, report))
        return JobResponse(job_id=job.id)

    @app.patch("/api/clips/{clip_id}", response_model=StudioClip)
    def edit_clip(clip_id: str, update: ClipUpdate) -> StudioClip:
        payload = update.model_dump(exclude_unset=True)
        try:
            if "selected_face_track_id" in payload:
                selected_face_track_id = payload.pop("selected_face_track_id")
                store.select_face_track(clip_id, selected_face_track_id)
            return store.update_clip(clip_id, **payload) if payload else store.get_clip(clip_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    @app.get("/api/clips/{clip_id}/face-tracks", response_model=list[FaceTrackRecord])
    def list_face_tracks(clip_id: str) -> list[FaceTrackRecord]:
        try:
            return store.list_face_tracks(clip_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    @app.get("/api/clips/{clip_id}/tracking-gaps")
    def list_tracking_gaps(clip_id: str) -> list[dict[str, Any]]:
        try:
            return [gap.__dict__ for gap in store.list_tracking_gaps(clip_id)]
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    @app.post("/api/clips/{clip_id}/tracking-preview", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
    def tracking_preview(clip_id: str) -> JobResponse:
        try:
            clip = store.get_clip(clip_id)
            capability = get_tracker_capability()
            if not capability.available:
                raise ValueError(capability.reason)
            job = store.create_job(clip.project_id, "tracking_preview", "Queued for tracking preview")
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        runner.submit(job, lambda report: tracking.render_preview(clip_id, report))
        return JobResponse(job_id=job.id)

    @app.post("/api/clips/{clip_id}/approve", response_model=StudioClip)
    def approve_clip(clip_id: str) -> StudioClip:
        try:
            return store.approve_clip(clip_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    @app.post("/api/clips/{clip_id}/export", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
    def export_clip(clip_id: str) -> JobResponse:
        try:
            clip = store.get_clip(clip_id)
            if clip.status != "approved":
                raise ValueError("Approve tracking preview before exporting")
            job = store.create_job(clip.project_id, "export", "Queued for approved export")
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        runner.submit(job, lambda report: tracking.export_approved(clip_id, report))
        return JobResponse(job_id=job.id)

    @app.get("/api/jobs/{job_id}", response_model=Job)
    def get_job(job_id: str) -> Job:
        try:
            return store.get_job(job_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    @app.websocket("/api/jobs/{job_id}")
    @app.websocket("/api/jobs/{job_id}/events")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        last_signature: tuple[Any, ...] | None = None
        try:
            while True:
                try:
                    job = store.get_job(job_id)
                except KeyError:
                    await websocket.send_json({"job_id": job_id, "stage": "failed", "progress": 1.0, "message": "Job not found", "error": "not_found"})
                    return
                signature = (job.stage, job.progress, job.message, job.error)
                if signature != last_signature:
                    await websocket.send_json(_job_event(job))
                    last_signature = signature
                if job.stage in {"completed", "failed", "interrupted"}:
                    return
                await asyncio.sleep(0.15)
        finally:
            await websocket.close()

    @app.get("/api/artifacts/{artifact_id}")
    def get_artifact(artifact_id: str) -> FileResponse:
        artifact = _find_artifact(store, artifact_id)
        path = Path(artifact.path).resolve()
        project_root = (store.root / artifact.project_id).resolve()
        if not path.is_file() or project_root not in path.parents:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
        return FileResponse(path)

    return app


def _project_detail(store: FullStudioStore, project_id: str) -> dict[str, Any]:
    clips = store.list_clips(project_id)
    return {
        "project": store.get_project(project_id),
        "clips": clips,
        "face_tracks": {clip.id: store.list_face_tracks(clip.id) for clip in clips},
        "tracking_gaps": {clip.id: store.list_tracking_gaps(clip.id) for clip in clips},
        "jobs": store.list_jobs(project_id),
        "artifacts": store.list_artifacts(project_id),
    }


def _runtime_health() -> dict[str, Any]:
    face = get_tracker_capability()
    try:
        import cv2

        opencv = {"available": True, "version": cv2.__version__}
    except ImportError:
        opencv = {"available": False, "version": None}
    try:
        import torch

        runtime = "gpu" if torch.cuda.is_available() else "cpu"
    except ImportError:
        runtime = "cpu"
    return {
        "ffmpeg": {"available": shutil.which("ffmpeg") is not None},
        "opencv": opencv,
        "face_tracking": {"available": face.available, "engine": face.engine, "reason": face.reason},
        "runtime": runtime,
    }


def _mark_interrupted_jobs(store: FullStudioStore) -> None:
    """A process restart never disguises a broken render as a completed one."""
    with store._connect() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET stage = 'interrupted', error = 'Server restarted', message = 'Interrupted; submit again to resume locally'
            WHERE stage = 'running'
            """
        )


def _find_artifact(store: FullStudioStore, artifact_id: str) -> Artifact:
    for project in store.list_projects():
        for artifact in store.list_artifacts(project.id):
            if artifact.id == artifact_id:
                return artifact
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")


def _job_event(job: Job) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "stage": job.stage,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
    }


app = create_studio_server()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
