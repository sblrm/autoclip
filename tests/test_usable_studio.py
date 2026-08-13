from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from autoclip.web.setup_manager import ComponentStatus, HardwareStatus, SetupStatus


class ReadyManager:
    def __init__(self) -> None:
        self.installed: list[str] = []

    def status(self) -> SetupStatus:
        return SetupStatus(
            components=(ComponentStatus("ffmpeg", "FFmpeg", True, "ready", "7", "Video export."),),
            hardware=HardwareStatus("NVIDIA GeForce RTX 5070", "610.88", False),
            is_ready=True,
        )

    def install_plan(self, component: str):
        if component != "opencv":
            raise ValueError("Unsupported setup component")
        return object()

    def install(self, component: str, report) -> None:
        self.installed.append(component)
        report("installing", 0.5, "Installing OpenCV")


def test_setup_status_and_install_job_are_available_without_a_video_project(tmp_path: Path) -> None:
    from autoclip.web.usable_studio import create_usable_studio

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "ux.html").write_text("<main>Setup Center</main>", encoding="utf-8")
    manager = ReadyManager()
    app = create_usable_studio(tmp_path / "projects", dist=dist, setup_manager=manager)
    client = TestClient(app)

    status = client.get("/api/setup/status")
    queued = client.post("/api/setup/install", json={"component": "opencv"})
    deadline = time.monotonic() + 2
    job = None
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{queued.json()['job_id']}").json()
        if job["stage"] == "completed":
            break
        time.sleep(0.02)
    app.state.runner.stop()

    assert status.status_code == 200
    assert status.json()["hardware"]["adapter"] == "NVIDIA GeForce RTX 5070"
    assert queued.status_code == 202
    assert manager.installed == ["opencv"]
    assert job["stage"] == "completed"
