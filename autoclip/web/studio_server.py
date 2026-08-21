"""Complete local HTTP/WebSocket server for the AutoClip browser studio."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from autoclip.web.acceleration import (
    AccelerationSelection,
    AccelerationStatus,
    EncoderMode,
    EncoderUnavailable,
    TrackerEngine,
    TrackerUnavailable,
)
from autoclip.web.acceleration_manager import AccelerationManager
from autoclip.web.full_store import FullStudioStore
from autoclip.web.model_catalog import MODEL_PLANS, ModelPlan
from autoclip.web.model_manager import ModelManager
from autoclip.web.onboarding import OnboardingService, ProfileUnavailable
from autoclip.web.rendering import TrackingService
from autoclip.web.runtime_jobs import SerialJobRunner
from autoclip.web.runtime_pipeline import StudioPipeline
from autoclip.web.runtime_store import Artifact, FaceTrackRecord, PerformanceProfile
from autoclip.web.setup_manager import SetupManager, acceleration_runtime_plans
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


class AccelerationInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: Literal[
        "pytorch_cuda_128",
        "onnxruntime_cuda_128",
        "yunet_2023mar",
        "insightface_buffalo_m_retinaface",
        "insightface_antelopev2_scrfd",
    ]
    acknowledge_research_license: bool = False


class AccelerationSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracker_engine: TrackerEngine | None = None
    encoder_mode: EncoderMode | None = None


class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: Literal["id", "en"] | None = None
    onboarding_complete: bool | None = None
    performance_profile: PerformanceProfile | None = None


class RepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    acceleration_manager = AccelerationManager()
    app = FastAPI(title="AutoClip Local Studio", version="1.0.0")
    app.state.store = store
    app.state.runner = runner
    app.state.pipeline = pipeline
    app.state.tracking = tracking
    app.state.acceleration_manager = acceleration_manager
    app.state.setup_manager = SetupManager(acceleration_manager=acceleration_manager)
    app.state.model_manager = ModelManager()
    app.state.onboarding = OnboardingService(
        store=store,
        setup_manager=app.state.setup_manager,
        acceleration_manager=acceleration_manager,
    )

    @app.exception_handler(ProfileUnavailable)
    async def profile_unavailable(_: Request, error: ProfileUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": error.code,
                "title": error.title,
                "recovery_action": error.recovery_action,
                "retryable": error.retryable,
            },
        )

    @app.on_event("shutdown")
    def shutdown_worker() -> None:
        runner.stop()

    @app.get("/api/runtime-health")
    def runtime_health() -> dict[str, Any]:
        acceleration = app.state.acceleration_manager.status()
        return _runtime_health(acceleration)

    @app.get("/api/acceleration/status")
    def acceleration_status() -> dict[str, Any]:
        return _acceleration_status_payload(app.state.acceleration_manager.status())

    @app.get("/api/acceleration/plans")
    def acceleration_plans() -> list[dict[str, Any]]:
        return _acceleration_plan_metadata()

    @app.post("/api/acceleration/recheck")
    def recheck_acceleration() -> dict[str, Any]:
        return _acceleration_status_payload(app.state.acceleration_manager.status())

    @app.post("/api/acceleration/install", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
    def install_acceleration(body: AccelerationInstallRequest) -> JobResponse:
        model_plan = MODEL_PLANS.get(body.plan_id)
        if model_plan is not None and model_plan.research_only:
            if not body.acknowledge_research_license:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"requires_acknowledgement: plan_id={model_plan.id}",
                )
            store.save_model_acknowledgement(model_plan)

        if model_plan is None:
            try:
                app.state.setup_manager.install_plan(body.plan_id)
            except ValueError as error:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

        job = _create_setup_job(store, f"acceleration:{body.plan_id}")
        if model_plan is None:
            runner.submit(
                job,
                lambda report: app.state.setup_manager.install(body.plan_id, report),
            )
        else:
            runner.submit(
                job,
                lambda report: _install_model(
                    app.state.model_manager,
                    model_plan,
                    body.acknowledge_research_license,
                    report,
                ),
            )
        return JobResponse(job_id=job.id)

    @app.get("/api/onboarding")
    def onboarding_status() -> dict[str, object]:
        return _onboarding_service(app).snapshot().payload()

    @app.patch("/api/preferences")
    def update_preferences(body: PreferencesPatch) -> dict[str, Any]:
        changes = body.model_dump(exclude_none=True)
        profile = changes.pop("performance_profile", None)
        if profile is not None:
            _onboarding_service(app).set_profile(profile)
        return asdict(store.update_app_preferences(**changes))

    @app.post("/api/onboarding/repair", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
    def repair_required_setup(_: RepairRequest) -> JobResponse:
        job = _create_setup_job(store, "repair_required")
        runner.submit(job, _onboarding_service(app).repair_required)
        return JobResponse(job_id=job.id)

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
            project = store.create_from_upload(incoming_path, original_name=file.filename)
            _apply_stored_profile(app, project)
            return project
        finally:
            incoming_path.unlink(missing_ok=True)

    @app.post("/api/projects/from-url", response_model=Project, status_code=status.HTTP_201_CREATED)
    def import_url_project(body: UrlImport) -> Project:
        try:
            project = store.create_from_url(body.url)
            _apply_stored_profile(app, project)
            return project
        except ProfileUnavailable:
            raise
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    @app.post("/api/projects/{project_id}/apply-performance-profile")
    def apply_performance_profile(project_id: str) -> dict[str, Any]:
        try:
            return asdict(_onboarding_service(app).apply_profile(project_id))
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    @app.get("/api/projects/{project_id}")
    def project_detail(project_id: str) -> dict[str, Any]:
        try:
            return _project_detail(store, project_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    @app.patch("/api/projects/{project_id}/acceleration")
    def select_project_acceleration(
        project_id: str,
        body: AccelerationSelectionRequest,
    ) -> dict[str, Any]:
        try:
            current = store.get_project_acceleration(project_id)
            tracker_engine = body.tracker_engine or current.tracker_engine
            encoder_mode = body.encoder_mode or current.encoder_mode
            app.state.acceleration_manager.status().resolve(
                AccelerationSelection(
                    tracker_engine=tracker_engine,
                    encoder_mode=encoder_mode,
                ),
            )
            saved = store.set_project_acceleration(
                project_id,
                tracker_engine=tracker_engine,
                encoder_mode=encoder_mode,
            )
            tracker_changed = saved.tracker_engine != current.tracker_engine
            encoder_changed = saved.encoder_mode != current.encoder_mode
            for clip in store.list_clips(project_id):
                if tracker_changed:
                    store.clear_tracking_data(clip.id)
                elif encoder_changed:
                    store.clear_tracking_preview(clip.id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except (TrackerUnavailable, EncoderUnavailable) as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        return asdict(saved)

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
            requires_detection = store.get_clip_tracking_resolution(clip_id) is None
            kind = "tracking_detection" if requires_detection else "tracking_preview"
            message = "Queued for face detection" if requires_detection else "Queued for tracking preview"
            job = store.create_job(clip.project_id, kind, message)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        if requires_detection:
            runner.submit(job, lambda report: tracking.detect_tracks(clip_id, report))
        else:
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
    clip_payloads: list[dict[str, Any]] = []
    for clip in clips:
        payload = asdict(clip)
        resolution = store.get_clip_tracking_resolution(clip.id)
        payload["tracking_resolution"] = None if resolution is None else asdict(resolution)
        clip_payloads.append(payload)
    return {
        "project": store.get_project(project_id),
        "clips": clip_payloads,
        "acceleration": asdict(store.get_project_acceleration(project_id)),
        "face_tracks": {clip.id: store.list_face_tracks(clip.id) for clip in clips},
        "tracking_gaps": {clip.id: store.list_tracking_gaps(clip.id) for clip in clips},
        "jobs": store.list_jobs(project_id),
        "artifacts": store.list_artifacts(project_id),
    }


def _runtime_health(acceleration: AccelerationStatus | None = None) -> dict[str, Any]:
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
    payload = {
        "ffmpeg": {"available": shutil.which("ffmpeg") is not None},
        "opencv": opencv,
        "face_tracking": {"available": face.available, "engine": face.engine, "reason": face.reason},
        "runtime": runtime,
    }
    if acceleration is not None:
        payload["acceleration"] = _acceleration_status_payload(acceleration)
    return payload


def _acceleration_status_payload(acceleration: AccelerationStatus) -> dict[str, Any]:
    return {
        "platform": acceleration.platform,
        "engines": {name: asdict(probe) for name, probe in acceleration.engines.items()},
        "encoders": {name: asdict(probe) for name, probe in acceleration.encoders.items()},
    }


def _acceleration_plan_metadata() -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for plan in acceleration_runtime_plans(__import__("sys").executable).values():
        plans.append(
            {
                "id": plan.component,
                "label": plan.label,
                "kind": "package",
                "requires_restart": plan.requires_restart,
                "detail": plan.detail,
                "license": None,
                "research_only": False,
            },
        )
    for plan in MODEL_PLANS.values():
        plans.append(
            {
                "id": plan.id,
                "label": plan.label,
                "kind": "model",
                "requires_restart": False,
                "detail": f"Downloads one pinned, checksum-verified model ({plan.bytes} bytes).",
                "license": plan.license,
                "research_only": plan.research_only,
                "bytes": plan.bytes,
            },
        )
    return plans


def _create_setup_job(store: FullStudioStore, task: str) -> Job:
    job = Job(
        id=uuid.uuid4().hex,
        project_id="__setup__",
        kind=f"setup:{task}",
        stage="queued",
        progress=0.0,
        message=f"Queued setup for {task}",
        error=None,
    )
    with store._connect() as connection:
        connection.execute(
            """
            INSERT INTO jobs (id, project_id, kind, stage, progress, message, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job.id, job.project_id, job.kind, job.stage, job.progress, job.message, job.error),
        )
    return job


def _onboarding_service(app: FastAPI) -> OnboardingService:
    service = app.state.onboarding
    if (
        service.setup_manager is not app.state.setup_manager
        or service.acceleration_manager is not app.state.acceleration_manager
    ):
        service = OnboardingService(
            store=app.state.store,
            setup_manager=app.state.setup_manager,
            acceleration_manager=app.state.acceleration_manager,
        )
        app.state.onboarding = service
    return service


def _apply_stored_profile(app: FastAPI, project: Project) -> None:
    if app.state.store.get_app_preferences().performance_profile in {"cpu", "gpu"}:
        _onboarding_service(app).apply_profile(project.id)


def _install_model(
    manager: Any,
    plan: ModelPlan,
    acknowledged: bool,
    report: Callable[[str, float, str], None],
) -> None:
    progress = {
        "model_download_started": 0.15,
        "model_cache_hit": 0.9,
        "model_installed": 0.95,
    }

    def model_report(event: str, detail: str) -> None:
        report(event, progress.get(event, 0.5), f"{event}: {detail}")

    manager.install(plan.id, acknowledged, model_report)


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
