"""Isolated local server for the browser smoke path; never runs real media work."""

from __future__ import annotations

import tempfile
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autoclip.web.acceleration import AccelerationStatus, ResolvedAcceleration
from autoclip.web.onboarding import OnboardingService
from autoclip.web.setup_manager import ComponentStatus, HardwareStatus, InstallPlan, SetupStatus
from autoclip.web.usable_studio import create_usable_studio

Reporter = Callable[[str, float, str], None]


class FakePipeline:
    def __init__(self, store) -> None:
        self.store = store

    def analyze(self, project_id: str, report: Reporter) -> None:
        report("analyzing", 0.3, "Analyzing clip candidates")
        if not self.store.list_clips(project_id):
            self.store.create_clip(
                project_id,
                start_time=0.0,
                end_time=12.0,
                title="Browser fixture clip",
                score=95,
                language="id",
            )
        self.store.set_project_status(project_id, "ready")
        report("ready", 1.0, "Clip candidates ready")


class FakeTracking:
    def __init__(self, store) -> None:
        self.store = store

    def detect_tracks(self, clip_id: str, report: Reporter) -> None:
        clip = self.store.get_clip(clip_id)
        self.store.save_clip_tracking_resolution(
            clip_id,
            ResolvedAcceleration(
                tracker_engine="yunet_cpu",
                encoder_mode="libx264",
                provider="CPUExecutionProvider",
                model_id="browser-fixture",
            ),
            None,
        )
        self.store.save_face_track(
            clip_id,
            label="Subject 1",
            confidence=0.98,
            samples=[{"cx": 0.5, "cy": 0.5, "confidence": 0.98}],
        )
        self.store.update_clip(clip_id, tracking_status="needs_subject")
        report("needs_subject", 1.0, "Select Subject 1")

    def render_preview(self, clip_id: str, report: Reporter) -> None:
        clip = self.store.get_clip(clip_id)
        self.store.save_artifact(
            clip.project_id,
            "tracking_preview",
            self.store.root / clip.project_id / "preview.mp4",
            clip_id=clip.id,
            metadata={"encoder_mode": "libx264", "tracker_engine": "yunet_cpu"},
        )
        self.store.mark_preview_ready(clip_id)
        self.store.update_clip(clip_id, tracking_status="preview_ready")
        report("preview_ready", 1.0, "Preview ready")

    def export_approved(self, clip_id: str, report: Reporter) -> None:
        clip = self.store.get_clip(clip_id)
        self.store.save_artifact(
            clip.project_id,
            "export",
            self.store.root / clip.project_id / "export.mp4",
            clip_id=clip.id,
            metadata={"encoder": "libx264", "tracker_engine": "yunet_cpu"},
        )
        report("exported", 1.0, "Export ready")


class ReadySetup:
    def status(self) -> SetupStatus:
        return SetupStatus(
            components=(ComponentStatus("ffmpeg", "FFmpeg", True, "ready", "fixture", "ready"),),
            hardware=HardwareStatus(None, None, False),
            is_ready=True,
        )

    def install_plan(self, component: str) -> InstallPlan:
        raise ValueError(f"fixture does not install {component}")

    def install(self, component: str, report: Reporter) -> InstallPlan:
        raise RuntimeError(f"fixture does not install {component}")


class ReadyAcceleration:
    def status(self) -> AccelerationStatus:
        return AccelerationStatus.for_test(
            platform="Windows",
            engines={"yunet_cpu": ("ready", "CPUExecutionProvider", "browser-fixture")},
            encoders={"libx264": "ready"},
        )


def create_browser_smoke_app():
    root = Path(tempfile.mkdtemp(prefix="autoclip-browser-smoke-"))
    static_root = Path(__file__).resolve().parents[1] / "autoclip" / "web" / "static"
    app = create_usable_studio(
        root / "projects",
        dist=static_root,
        setup_manager=ReadySetup(),
        pipeline_factory=FakePipeline,
        tracking_factory=FakeTracking,
    )
    acceleration = ReadyAcceleration()
    app.state.acceleration_manager = acceleration
    app.state.onboarding = OnboardingService(
        store=app.state.store,
        setup_manager=app.state.setup_manager,
        acceleration_manager=acceleration,
    )

    import autoclip.web.studio_server as studio_server

    studio_server.get_tracker_capability = lambda: SimpleNamespace(
        available=True,
        engine="browser_fixture",
        reason="ready",
    )
    return app


if __name__ == "__main__":
    uvicorn.run(create_browser_smoke_app(), host="127.0.0.1", port=8766, log_level="warning")
