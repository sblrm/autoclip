from __future__ import annotations

from pathlib import Path

import pytest

from autoclip.web.acceleration import AccelerationStatus
from autoclip.web.runtime_store import RuntimeStore
from autoclip.web.setup_manager import ComponentStatus, InstallPlan, SetupStatus


def test_app_preferences_default_and_partial_update(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path / "library")

    assert store.get_app_preferences().performance_profile == "auto"
    saved = store.update_app_preferences(
        locale="en",
        last_project_id="p1",
        performance_profile="cpu",
    )

    assert saved.locale == "en"
    assert saved.last_project_id == "p1"
    assert RuntimeStore(tmp_path / "library").get_app_preferences() == saved


def test_app_preferences_reject_invalid_profile(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="performance_profile"):
        RuntimeStore(tmp_path / "library").update_app_preferences(
            performance_profile="cuda",
        )


class FakeAccelerationManager:
    def __init__(self, status: AccelerationStatus) -> None:
        self._status = status

    def status(self) -> AccelerationStatus:
        return self._status


class FakeSetupManager:
    def __init__(self, required: tuple[str, ...], ready: set[str]) -> None:
        self.required = required
        self.ready = set(ready)
        self.installed: list[str] = []
        self.planned: list[str] = []
        self.status_calls = 0

    def status(self) -> SetupStatus:
        self.status_calls += 1
        components = tuple(
            ComponentStatus(
                component,
                component,
                True,
                "ready" if component in self.ready else "missing",
                None,
                "test component",
            )
            for component in self.required
        )
        return SetupStatus(components, hardware=__import__("types").SimpleNamespace(), is_ready=all(
            component in self.ready for component in self.required
        ))

    def install_plan(self, component: str) -> InstallPlan:
        self.planned.append(component)
        return InstallPlan(component, component, ["fixed", component], False, "test plan")

    def install(self, component: str, report: object) -> InstallPlan:
        self.installed.append(component)
        self.ready.add(component)
        return self.install_plan(component)


def test_gpu_profile_requires_verified_tracker_and_nvenc(tmp_path: Path) -> None:
    from autoclip.web.onboarding import OnboardingService, ProfileUnavailable

    service = OnboardingService(
        store=RuntimeStore(tmp_path / "library"),
        setup_manager=FakeSetupManager((), set()),
        acceleration_manager=FakeAccelerationManager(
            AccelerationStatus.for_test(
                engines={"yunet_cuda": ("ready", "CUDAExecutionProvider", "yunet_2023mar")},
                encoders={"libx264": "ready"},
            )
        ),
    )

    with pytest.raises(ProfileUnavailable, match="gpu_encoder_unavailable"):
        service.set_profile("gpu")


def test_cpu_profile_persists_verified_cpu_selection(tmp_path: Path) -> None:
    from autoclip.web.onboarding import OnboardingService

    store = RuntimeStore(tmp_path / "library")
    service = OnboardingService(
        store=store,
        setup_manager=FakeSetupManager((), set()),
        acceleration_manager=FakeAccelerationManager(
            AccelerationStatus.for_test(
                engines={"yunet_cpu": ("ready", "CPUExecutionProvider", "yunet_2023mar")},
                encoders={"libx264": "ready"},
            )
        ),
    )

    selected = service.set_profile("cpu")

    assert selected.tracker_engine == "yunet_cpu"
    assert selected.encoder_mode == "libx264"
    assert store.get_app_preferences().performance_profile == "cpu"


def test_snapshot_names_required_repair_when_runtime_is_missing(tmp_path: Path) -> None:
    from autoclip.web.onboarding import OnboardingService

    service = OnboardingService(
        store=RuntimeStore(tmp_path / "library"),
        setup_manager=FakeSetupManager(("ffmpeg",), set()),
        acceleration_manager=FakeAccelerationManager(AccelerationStatus.for_test()),
    )

    assert service.snapshot().recommended_action.id == "repair_required"


def test_repair_required_skips_ready_components_and_rechecks_each_child(tmp_path: Path) -> None:
    from autoclip.web.onboarding import OnboardingService

    setup = FakeSetupManager(("ffmpeg", "opencv", "whisper"), {"ffmpeg"})
    service = OnboardingService(
        store=RuntimeStore(tmp_path / "library"),
        setup_manager=setup,
        acceleration_manager=FakeAccelerationManager(
            AccelerationStatus.for_test(
                engines={"yunet_cpu": ("ready", "CPUExecutionProvider", "yunet_2023mar")},
                encoders={"libx264": "ready"},
            )
        ),
    )
    events: list[tuple[str, float, str]] = []

    service.repair_required(lambda stage, progress, message: events.append((stage, progress, message)))

    assert setup.installed == ["opencv", "whisper"]
    assert setup.planned == ["opencv", "opencv", "whisper", "whisper"]
    assert setup.status_calls == 3
    assert events[-1][0] == "repair_ready"
