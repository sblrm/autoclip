from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from autoclip.web.acceleration import AccelerationStatus, ResolvedAcceleration


class FakeAccelerationManager:
    def __init__(self) -> None:
        self.current = AccelerationStatus.for_test(
            platform="Windows",
            engines={
                "mediapipe_cpu": ("ready", "CPUDelegate"),
                "yunet_cpu": ("ready", "CPUExecutionProvider", "yunet_2023mar"),
                "yunet_cuda": (
                    "missing",
                    "CUDAExecutionProvider",
                    "yunet_2023mar",
                    "Verified detector model is not cached",
                ),
            },
            encoders={
                "libx264": "ready",
                "h264_nvenc": "ready",
                "hevc_nvenc": ("unsupported", "encoder unavailable"),
            },
        )
        self.status_calls = 0

    def status(self) -> AccelerationStatus:
        self.status_calls += 1
        return self.current


class FakeSetupManager:
    def __init__(self) -> None:
        self.installed: list[str] = []

    def install_plan(self, component: str) -> object:
        if component not in {"onnxruntime_cuda_128", "pytorch_cuda_128"}:
            raise ValueError(f"Unsupported setup component: {component}")
        return object()

    def install(self, component: str, report: Any) -> None:
        self.installed.append(component)
        report("installing", 0.5, "Installing ONNX Runtime CUDA")


class FakeModelManager:
    def __init__(self) -> None:
        self.installed: list[tuple[str, bool]] = []

    def install(self, plan_id: str, acknowledged: bool, report: Any) -> None:
        self.installed.append((plan_id, acknowledged))
        report("model_download_started", plan_id)
        report("model_installed", plan_id)


@pytest.fixture
def app(tmp_path: Path):
    from autoclip.web.studio_server import create_studio_server

    acceleration = FakeAccelerationManager()
    setup = FakeSetupManager()
    models = FakeModelManager()
    application = create_studio_server(tmp_path / "library")
    application.state.acceleration_manager = acceleration
    application.state.setup_manager = setup
    application.state.model_manager = models
    application.state.test_acceleration = acceleration
    application.state.test_setup = setup
    application.state.test_models = models
    return application


@pytest.fixture
def client(app: Any):
    with TestClient(app) as test_client:
        yield test_client


def _wait_for_job(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 2
    job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["stage"] in {"completed", "failed"}:
            return job
        time.sleep(0.02)
    return job


def test_acceleration_plans_are_fixed_public_metadata(client: TestClient) -> None:
    response = client.get("/api/acceleration/plans")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()} >= {
        "onnxruntime_cuda_128",
        "pytorch_cuda_128",
        "yunet_2023mar",
    }
    assert all("command" not in item for item in response.json())


def test_browser_cannot_submit_url_or_package(client: TestClient) -> None:
    response = client.post(
        "/api/acceleration/install",
        json={
            "plan_id": "yunet_2023mar",
            "url": "https://evil.test/model.onnx",
            "package": "evil-package",
        },
    )

    assert response.status_code == 422


def test_research_install_requires_saved_acknowledgement(client: TestClient) -> None:
    response = client.post(
        "/api/acceleration/install",
        json={
            "plan_id": "insightface_buffalo_m_retinaface",
            "acknowledge_research_license": False,
        },
    )

    assert response.status_code == 409
    assert "requires_acknowledgement" in response.json()["detail"]


def test_research_acknowledgement_is_saved_before_model_job_runs(
    app: Any,
    client: TestClient,
) -> None:
    response = client.post(
        "/api/acceleration/install",
        json={
            "plan_id": "insightface_buffalo_m_retinaface",
            "acknowledge_research_license": True,
        },
    )

    assert response.status_code == 202
    with app.state.store._connect() as connection:
        acknowledgement = connection.execute(
            "SELECT plan_id, license FROM model_acknowledgements WHERE plan_id = ?",
            ("insightface_buffalo_m_retinaface",),
        ).fetchone()
    assert acknowledgement is not None
    assert acknowledgement["plan_id"] == "insightface_buffalo_m_retinaface"

    job = _wait_for_job(client, response.json()["job_id"])
    assert job["kind"] == "setup:acceleration:insightface_buffalo_m_retinaface"
    assert job["stage"] == "completed"
    assert app.state.test_models.installed == [
        ("insightface_buffalo_m_retinaface", True),
    ]


def test_runtime_plan_uses_setup_manager_in_same_serial_queue(app: Any, client: TestClient) -> None:
    response = client.post(
        "/api/acceleration/install",
        json={"plan_id": "onnxruntime_cuda_128"},
    )

    assert response.status_code == 202
    job = _wait_for_job(client, response.json()["job_id"])
    assert job["kind"] == "setup:acceleration:onnxruntime_cuda_128"
    assert job["stage"] == "completed"
    assert app.state.test_setup.installed == ["onnxruntime_cuda_128"]


def test_pytorch_cuda_plan_is_available_for_gpu_setup(app: Any, client: TestClient) -> None:
    response = client.post(
        "/api/acceleration/install",
        json={"plan_id": "pytorch_cuda_128"},
    )

    assert response.status_code == 202
    job = _wait_for_job(client, response.json()["job_id"])
    assert job["kind"] == "setup:acceleration:pytorch_cuda_128"
    assert job["stage"] == "completed"
    assert app.state.test_setup.installed == ["pytorch_cuda_128"]


def test_status_recheck_and_runtime_health_return_verified_acceleration(
    app: Any,
    client: TestClient,
) -> None:
    status_response = client.get("/api/acceleration/status")
    recheck_response = client.post("/api/acceleration/recheck")
    health_response = client.get("/api/runtime-health")

    assert status_response.status_code == 200
    assert status_response.json()["engines"]["yunet_cuda"] == {
        "state": "missing",
        "provider": "CUDAExecutionProvider",
        "model_id": "yunet_2023mar",
        "reason": "Verified detector model is not cached",
    }
    assert recheck_response.status_code == 200
    assert health_response.status_code == 200
    assert health_response.json()["acceleration"]["platform"] == "Windows"
    assert "runtime" in health_response.json()
    assert app.state.test_acceleration.status_calls == 3


def test_project_acceleration_selection_and_tracking_resolution_are_in_detail(
    app: Any,
    client: TestClient,
) -> None:
    project = client.post(
        "/api/projects/from-url",
        json={"url": "https://example.test/video.mp4"},
    ).json()
    selected = client.patch(
        f"/api/projects/{project['id']}/acceleration",
        json={"tracker_engine": "yunet_cpu", "encoder_mode": "h264_nvenc"},
    )
    clip = app.state.store.create_clip(
        project["id"],
        start_time=0,
        end_time=3,
        title="Moment",
        score=90,
        language="id",
    )
    app.state.store.save_clip_tracking_resolution(
        clip.id,
        ResolvedAcceleration(
            tracker_engine="yunet_cpu",
            encoder_mode="h264_nvenc",
            provider="CPUExecutionProvider",
            model_id="yunet_2023mar",
        ),
        None,
    )
    detail = client.get(f"/api/projects/{project['id']}")

    assert selected.status_code == 200
    assert selected.json()["tracker_engine"] == "yunet_cpu"
    assert selected.json()["encoder_mode"] == "h264_nvenc"
    assert detail.json()["acceleration"]["tracker_engine"] == "yunet_cpu"
    assert detail.json()["clips"][0]["tracking_resolution"]["provider"] == "CPUExecutionProvider"


def test_selection_conflicts_and_missing_project_have_specific_http_status(
    app: Any,
    client: TestClient,
) -> None:
    project = client.post(
        "/api/projects/from-url",
        json={"url": "https://example.test/video.mp4"},
    ).json()

    nvenc = client.patch(
        f"/api/projects/{project['id']}/acceleration",
        json={"encoder_mode": "hevc_nvenc"},
    )
    app.state.test_acceleration.current = AccelerationStatus.for_test(
        platform="Windows",
        encoders={"libx264": "ready"},
    )
    no_tracker = client.patch(
        f"/api/projects/{project['id']}/acceleration",
        json={"tracker_engine": "auto"},
    )
    missing = client.patch(
        "/api/projects/missing/acceleration",
        json={"tracker_engine": "auto"},
    )

    assert nvenc.status_code == 409
    assert "nvenc_error" in nvenc.json()["detail"]
    assert no_tracker.status_code == 409
    assert "no_tracker_engine" in no_tracker.json()["detail"]
    assert missing.status_code == 404


def test_tracking_preview_detects_before_render_and_tracker_change_requires_new_lock(
    app: Any,
    client: TestClient,
    tmp_path: Path,
) -> None:
    project = client.post(
        "/api/projects/from-url",
        json={"url": "https://example.test/video.mp4"},
    ).json()
    clip = app.state.store.create_clip(
        project["id"],
        start_time=0,
        end_time=3,
        title="Moment",
        score=90,
        language="id",
    )
    client.patch(
        f"/api/projects/{project['id']}/acceleration",
        json={"tracker_engine": "yunet_cpu"},
    )
    calls: list[str] = []

    def detect_tracks(clip_id: str, report: Any) -> list[Any]:
        calls.append("detect")
        selected = app.state.store.get_project_acceleration(project["id"])
        app.state.store.clear_tracking_data(clip_id)
        app.state.store.save_clip_tracking_resolution(
            clip_id,
            ResolvedAcceleration(
                tracker_engine=selected.tracker_engine,
                encoder_mode="libx264",
                provider="CPUExecutionProvider",
                model_id="detector-model",
            ),
            None,
        )
        track = app.state.store.save_face_track(
            clip_id,
            label="Subject 1",
            confidence=0.91,
            samples=[{"cx": 0.4, "cy": 0.4, "confidence": 0.91}],
        )
        app.state.store.update_clip(clip_id, tracking_status="needs_subject")
        report("needs_subject", 0.95, "Select a subject")
        return [track]

    def render_preview(clip_id: str, report: Any) -> None:
        calls.append("render")
        assert app.state.store.get_clip(clip_id).selected_face_track_id is not None
        app.state.store.update_clip(clip_id, tracking_status="preview_ready")
        app.state.store.mark_preview_ready(clip_id)
        report("preview_ready", 0.95, "Preview ready")

    app.state.tracking.detect_tracks = detect_tracks
    app.state.tracking.render_preview = render_preview

    first = client.post(f"/api/clips/{clip.id}/tracking-preview")
    first_job = _wait_for_job(client, first.json()["job_id"])
    first_detail = client.get(f"/api/projects/{project['id']}").json()

    assert first.status_code == 202
    assert first_job["kind"] == "tracking_detection"
    assert calls == ["detect"]
    assert first_detail["clips"][0]["selected_face_track_id"] is None
    assert len(first_detail["face_tracks"][clip.id]) == 1

    track_id = first_detail["face_tracks"][clip.id][0]["id"]
    assert client.patch(
        f"/api/clips/{clip.id}",
        json={"selected_face_track_id": track_id},
    ).status_code == 200
    second = client.post(f"/api/clips/{clip.id}/tracking-preview")
    second_job = _wait_for_job(client, second.json()["job_id"])
    assert second_job["kind"] == "tracking_preview"
    assert calls == ["detect", "render"]

    export = app.state.store.save_artifact(
        project["id"],
        "export",
        tmp_path / "finished.mp4",
        clip_id=clip.id,
    )
    switched = client.patch(
        f"/api/projects/{project['id']}/acceleration",
        json={"tracker_engine": "mediapipe_cpu"},
    )
    switched_detail = client.get(f"/api/projects/{project['id']}").json()

    assert switched.status_code == 200
    assert switched_detail["clips"][0]["tracking_resolution"] is None
    assert switched_detail["clips"][0]["selected_face_track_id"] is None
    assert switched_detail["face_tracks"][clip.id] == []
    assert export.id in {item["id"] for item in switched_detail["artifacts"]}

    third = client.post(f"/api/clips/{clip.id}/tracking-preview")
    third_job = _wait_for_job(client, third.json()["job_id"])
    third_detail = client.get(f"/api/projects/{project['id']}").json()
    assert third_job["kind"] == "tracking_detection"
    assert calls == ["detect", "render", "detect"]
    assert third_detail["clips"][0]["selected_face_track_id"] is None


def test_encoder_only_change_preserves_detection_and_subject_lock(
    app: Any,
    client: TestClient,
    tmp_path: Path,
) -> None:
    project = client.post(
        "/api/projects/from-url",
        json={"url": "https://example.test/video.mp4"},
    ).json()
    clip = app.state.store.create_clip(
        project["id"],
        start_time=0,
        end_time=3,
        title="Moment",
        score=90,
        language="id",
    )
    track = app.state.store.save_face_track(
        clip.id,
        label="Subject 1",
        confidence=0.9,
        samples=[],
    )
    app.state.store.select_face_track(clip.id, track.id)
    resolution = app.state.store.save_clip_tracking_resolution(
        clip.id,
        ResolvedAcceleration(
            tracker_engine="yunet_cpu",
            encoder_mode="libx264",
            provider="CPUExecutionProvider",
            model_id="yunet_2023mar",
        ),
        None,
    )
    preview = app.state.store.save_artifact(
        project["id"],
        "tracking_preview",
        tmp_path / "preview.mp4",
        clip_id=clip.id,
    )
    app.state.store.set_project_acceleration(
        project["id"],
        tracker_engine="yunet_cpu",
        encoder_mode="libx264",
    )

    changed = client.patch(
        f"/api/projects/{project['id']}/acceleration",
        json={"encoder_mode": "h264_nvenc"},
    )
    detail = client.get(f"/api/projects/{project['id']}").json()

    assert changed.status_code == 200
    assert detail["clips"][0]["selected_face_track_id"] == track.id
    assert detail["clips"][0]["tracking_resolution"]["tracker_engine"] == resolution.tracker_engine
    assert preview.id not in {item["id"] for item in detail["artifacts"]}
    assert len(detail["face_tracks"][clip.id]) == 1
