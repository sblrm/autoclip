from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from autoclip.web.acceleration import AccelerationStatus
from autoclip.web.onboarding import OnboardingService
from autoclip.web.setup_manager import ComponentStatus, HardwareStatus, InstallPlan, SetupStatus


class FakeAccelerationManager:
    def __init__(self) -> None:
        self.current = AccelerationStatus.for_test(
            platform="Windows",
            engines={"yunet_cpu": ("ready", "CPUExecutionProvider", "yunet_2023mar")},
            encoders={"libx264": "ready"},
        )

    def status(self) -> AccelerationStatus:
        return self.current


class FakeSetupManager:
    def __init__(self) -> None:
        self.ready: set[str] = set()
        self.installed: list[str] = []

    def status(self) -> SetupStatus:
        component = ComponentStatus(
            "ffmpeg",
            "FFmpeg",
            True,
            "ready" if "ffmpeg" in self.ready else "missing",
            None,
            "test runtime",
        )
        return SetupStatus(
            components=(component,),
            hardware=HardwareStatus(None, None, False),
            is_ready="ffmpeg" in self.ready,
        )

    def install_plan(self, component: str) -> InstallPlan:
        if component != "ffmpeg":
            raise ValueError("Unsupported setup component")
        return InstallPlan(component, "FFmpeg", ["fixed", "ffmpeg"], False, "test plan")

    def install(self, component: str, report: Any) -> InstallPlan:
        plan = self.install_plan(component)
        self.installed.append(component)
        self.ready.add(component)
        report("completed", 1.0, "FFmpeg installed")
        return plan


@pytest.fixture
def app(tmp_path: Path):
    from autoclip.web.studio_server import create_studio_server

    application = create_studio_server(tmp_path / "library")
    acceleration = FakeAccelerationManager()
    setup = FakeSetupManager()
    application.state.acceleration_manager = acceleration
    application.state.setup_manager = setup
    application.state.onboarding = OnboardingService(
        store=application.state.store,
        setup_manager=setup,
        acceleration_manager=acceleration,
    )
    return application


@pytest.fixture
def client(app: Any):
    with TestClient(app) as test_client:
        yield test_client


def test_onboarding_payload_and_profile_preference_are_durable(client: TestClient) -> None:
    initial = client.get("/api/onboarding").json()
    changed = client.patch("/api/preferences", json={"locale": "en", "performance_profile": "cpu"})

    assert initial["recommended_action"]["id"] == "repair_required"
    assert changed.status_code == 200
    assert client.get("/api/onboarding").json()["preferences"]["performance_profile"] == "cpu"


def test_repair_endpoint_rejects_extra_browser_command_and_queues_one_job(client: TestClient) -> None:
    invalid = client.post("/api/onboarding/repair", json={"command": ["powershell"]})
    queued = client.post("/api/onboarding/repair", json={})

    assert invalid.status_code == 422
    assert queued.status_code == 202
    assert queued.json()["job_id"]


def test_gpu_profile_returns_structured_recovery_when_nvenc_is_missing(
    app: Any,
    client: TestClient,
) -> None:
    app.state.acceleration_manager.current = AccelerationStatus.for_test(
        engines={"yunet_cuda": ("ready", "CUDAExecutionProvider", "yunet_2023mar")},
        encoders={"libx264": "ready"},
    )

    response = client.patch("/api/preferences", json={"performance_profile": "gpu"})

    assert response.status_code == 409
    assert response.json() == {
        "code": "gpu_encoder_unavailable",
        "title": "NVENC export is not verified",
        "recovery_action": "Repair GPU export, then retry GPU.",
        "retryable": True,
    }


def test_cpu_profile_is_applied_to_new_url_project(client: TestClient) -> None:
    assert client.patch("/api/preferences", json={"performance_profile": "cpu"}).status_code == 200

    project = client.post("/api/projects/from-url", json={"url": "https://example.test/video.mp4"})
    detail = client.get(f"/api/projects/{project.json()['id']}")

    assert project.status_code == 201
    assert detail.json()["acceleration"] == {
        "project_id": project.json()["id"],
        "tracker_engine": "yunet_cpu",
        "encoder_mode": "libx264",
        "updated_at": detail.json()["acceleration"]["updated_at"],
    }
