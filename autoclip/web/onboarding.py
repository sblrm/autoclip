"""Durable local setup readiness and simple CPU/GPU profile selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Protocol

from autoclip.web.acceleration import (
    AccelerationSelection,
    AccelerationStatus,
    EncoderUnavailable,
    ResolvedAcceleration,
    TrackerUnavailable,
)
from autoclip.web.runtime_store import AppPreferences, PerformanceProfile, ProjectAcceleration, RuntimeStore
from autoclip.web.setup_manager import SetupStatus


Reporter = Callable[[str, float, str], None]


class SetupProvider(Protocol):
    def status(self) -> SetupStatus: ...

    def install_plan(self, component: str) -> object: ...

    def install(self, component: str, report: Reporter) -> object: ...


class AccelerationProvider(Protocol):
    def status(self) -> AccelerationStatus: ...


class ProfileUnavailable(ValueError):
    """A selected performance profile cannot be verified on this computer."""

    def __init__(
        self,
        code: str,
        title: str,
        recovery_action: str,
        retryable: bool = True,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.title = title
        self.recovery_action = recovery_action
        self.retryable = retryable


@dataclass(frozen=True)
class ProfileResolution:
    profile: PerformanceProfile
    resolved: ResolvedAcceleration

    @property
    def tracker_engine(self) -> str:
        return self.resolved.tracker_engine

    @property
    def encoder_mode(self) -> str:
        return self.resolved.encoder_mode


@dataclass(frozen=True)
class RecommendedAction:
    id: str
    title: str


@dataclass(frozen=True)
class OnboardingSnapshot:
    preferences: AppPreferences
    setup: SetupStatus
    acceleration: AccelerationStatus
    recommended_action: RecommendedAction
    tutorial_steps: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        return {
            "preferences": asdict(self.preferences),
            "setup": self.setup.payload(),
            "acceleration": {
                "platform": self.acceleration.platform,
                "engines": {
                    name: asdict(probe)
                    for name, probe in self.acceleration.engines.items()
                },
                "encoders": {
                    name: asdict(probe)
                    for name, probe in self.acceleration.encoders.items()
                },
            },
            "recommended_action": asdict(self.recommended_action),
            "tutorial_steps": list(self.tutorial_steps),
        }


class OnboardingService:
    """Own profile selection and required local setup repair without browser commands."""

    def __init__(
        self,
        *,
        store: RuntimeStore,
        setup_manager: SetupProvider,
        acceleration_manager: AccelerationProvider,
    ) -> None:
        self.store = store
        self.setup_manager = setup_manager
        self.acceleration_manager = acceleration_manager

    def snapshot(self) -> OnboardingSnapshot:
        setup = self.setup_manager.status()
        acceleration = self.acceleration_manager.status()
        action = (
            RecommendedAction("repair_required", "Repair required setup")
            if self._required_missing_component_ids(setup)
            else RecommendedAction("start_project", "Start a project")
        )
        return OnboardingSnapshot(
            preferences=self.store.get_app_preferences(),
            setup=setup,
            acceleration=acceleration,
            recommended_action=action,
            tutorial_steps=setup.tutorial_steps,
        )

    def set_profile(self, profile: PerformanceProfile) -> ProfileResolution:
        resolution = self._resolve_profile(profile, self.acceleration_manager.status())
        self.store.update_app_preferences(performance_profile=profile)
        return resolution

    def apply_profile(self, project_id: str) -> ProjectAcceleration:
        profile = self.store.get_app_preferences().performance_profile
        resolution = self._resolve_profile(profile, self.acceleration_manager.status())
        return self.store.set_project_acceleration(
            project_id,
            tracker_engine=resolution.resolved.tracker_engine,
            encoder_mode=resolution.resolved.encoder_mode,
        )

    def repair_required(self, report: Reporter) -> None:
        missing = self._required_missing_component_ids(self.setup_manager.status())
        if not missing:
            report("repair_ready", 1.0, "Required setup is ready.")
            return

        total = len(missing)
        for index, component in enumerate(missing):
            self.setup_manager.install_plan(component)
            report(
                f"repair:{component}",
                index / total,
                f"Repairing {component}",
            )

            def report_child(stage: str, progress: float, message: str, *, _component: str = component) -> None:
                bounded = max(0.0, min(1.0, progress))
                report(
                    f"repair:{_component}",
                    (index + bounded) / total,
                    message,
                )

            self.setup_manager.install(component, report_child)
            refreshed = self.setup_manager.status()
            still_missing = set(self._required_missing_component_ids(refreshed))
            if component in still_missing:
                raise RuntimeError(f"Required component did not become ready: {component}")

        report("repair_ready", 1.0, "Required setup is ready.")

    @staticmethod
    def _required_missing_component_ids(status: SetupStatus) -> tuple[str, ...]:
        return tuple(
            component.id
            for component in status.components
            if component.required and component.state != "ready"
        )

    def _resolve_profile(
        self,
        profile: PerformanceProfile,
        status: AccelerationStatus,
    ) -> ProfileResolution:
        if profile not in {"auto", "cpu", "gpu"}:
            raise ValueError("Invalid performance_profile")
        if profile == "auto":
            return ProfileResolution(profile, self._resolve(status, AccelerationSelection(), "auto"))
        if profile == "cpu":
            engine = self._first_ready(status, ("yunet_cpu", "mediapipe_cpu", "scrfd_cpu", "retinaface_cpu"))
            if engine is None:
                raise ProfileUnavailable(
                    "cpu_tracker_unavailable",
                    "CPU face tracking is not verified",
                    "Repair required setup, then retry CPU.",
                )
            return ProfileResolution(
                profile,
                self._resolve(status, AccelerationSelection(tracker_engine=engine, encoder_mode="libx264"), "cpu"),
            )

        engine = self._first_ready(
            status,
            ("yunet_cuda", "mediapipe_gpu", "scrfd_cuda", "retinaface_cuda"),
        )
        if engine is None:
            raise ProfileUnavailable(
                "gpu_tracker_unavailable",
                "GPU face tracking is not verified",
                "Repair GPU tracking, then retry GPU.",
            )
        if status.encoders.get("h264_nvenc") is None or status.encoders["h264_nvenc"].state != "ready":
            raise ProfileUnavailable(
                "gpu_encoder_unavailable",
                "NVENC export is not verified",
                "Repair GPU export, then retry GPU.",
            )
        return ProfileResolution(
            profile,
            self._resolve(status, AccelerationSelection(tracker_engine=engine, encoder_mode="h264_nvenc"), "gpu"),
        )

    @staticmethod
    def _first_ready(status: AccelerationStatus, engines: tuple[str, ...]) -> str | None:
        for engine in engines:
            probe = status.engines.get(engine)
            if probe is not None and probe.state == "ready":
                return engine
        return None

    @staticmethod
    def _resolve(
        status: AccelerationStatus,
        selection: AccelerationSelection,
        profile: PerformanceProfile,
    ) -> ResolvedAcceleration:
        try:
            return status.resolve(selection)
        except TrackerUnavailable as error:
            raise ProfileUnavailable(
                f"{profile}_tracker_unavailable",
                "Face tracking is not verified",
                "Repair face tracking, then retry.",
            ) from error
        except EncoderUnavailable as error:
            raise ProfileUnavailable(
                f"{profile}_encoder_unavailable",
                "Video export is not verified",
                "Repair video export, then retry.",
            ) from error
