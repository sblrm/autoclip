"""Stable contracts for selecting a verified local acceleration backend."""

from __future__ import annotations

import platform as platform_module
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

def _read_os_release() -> str:
    try:
        return Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return ""


def _default_platform() -> str:
    system = platform_module.system()
    if system.casefold() != "linux":
        return system

    values: dict[str, str] = {}
    for line in _read_os_release().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value.strip().strip('"')
    if values.get("ID", "").casefold() == "ubuntu":
        return "Ubuntu"
    if "ubuntu" in values.get("ID_LIKE", "").casefold().split():
        return "Ubuntu"
    return system

TrackerEngine = Literal[
    "auto", "mediapipe_cpu", "mediapipe_gpu", "yunet_cpu", "yunet_cuda",
    "scrfd_cpu", "scrfd_cuda", "retinaface_cpu", "retinaface_cuda",
]
EncoderMode = Literal["auto", "h264_nvenc", "hevc_nvenc", "libx264"]
RuntimeState = Literal[
    "ready", "missing", "unsupported", "failed", "requires_acknowledgement",
]


@dataclass(frozen=True)
class AccelerationSelection:
    tracker_engine: TrackerEngine = "auto"
    encoder_mode: EncoderMode = "auto"


@dataclass(frozen=True)
class ResolvedAcceleration:
    tracker_engine: TrackerEngine
    encoder_mode: EncoderMode
    provider: str
    model_id: str | None


class TrackerUnavailable(ValueError):
    """Raised when no requested tracker engine is ready to run."""

    error_code = "tracker_error"


class EncoderUnavailable(ValueError):
    """Raised when an explicitly requested NVENC encoder is unavailable."""

    error_code = "nvenc_error"


@dataclass(frozen=True)
class EngineProbe:
    """The verified runtime result for one face-tracker engine."""

    state: RuntimeState = "missing"
    provider: str = ""
    model_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class EncoderProbe:
    """The verified runtime result for one video encoder."""

    state: RuntimeState = "missing"
    reason: str | None = None


@dataclass(frozen=True)
class AccelerationStatus:
    """Immutable local probe results and their deterministic resolution policy."""

    platform: str = field(default_factory=_default_platform)
    engines: Mapping[str, EngineProbe | tuple[Any, ...] | str | Mapping[str, Any]] = field(
        default_factory=dict,
    )
    encoders: Mapping[str, EncoderProbe | tuple[Any, ...] | str | Mapping[str, Any]] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "engines",
            MappingProxyType({name: _engine_probe(value) for name, value in self.engines.items()}),
        )
        object.__setattr__(
            self,
            "encoders",
            MappingProxyType({name: _encoder_probe(value) for name, value in self.encoders.items()}),
        )

    @classmethod
    def for_test(
        cls,
        *,
        platform: str | None = None,
        engines: Mapping[str, EngineProbe | tuple[Any, ...] | str | Mapping[str, Any]] | None = None,
        encoders: Mapping[str, EncoderProbe | tuple[Any, ...] | str | Mapping[str, Any]] | None = None,
    ) -> "AccelerationStatus":
        """Build an immutable status from compact probe fixtures."""
        return cls(
            platform=platform if platform is not None else _default_platform(),
            engines={} if engines is None else engines,
            encoders={} if encoders is None else encoders,
        )

    def resolve(self, selection: AccelerationSelection) -> ResolvedAcceleration:
        """Resolve a selection only to locally verified, ready backends."""
        tracker_engine, tracker = self._resolve_tracker(selection.tracker_engine)
        encoder_mode = self._resolve_encoder(selection.encoder_mode)
        return ResolvedAcceleration(
            tracker_engine=tracker_engine,
            encoder_mode=encoder_mode,
            provider=tracker.provider,
            model_id=tracker.model_id,
        )

    def _resolve_tracker(self, requested: TrackerEngine) -> tuple[TrackerEngine, EngineProbe]:
        if requested != "auto":
            probe = self.engines.get(requested, EngineProbe())
            if probe.state != "ready":
                reason = probe.reason or "no probe result"
                raise TrackerUnavailable(
                    f"tracker_error: engine={requested} state={probe.state} reason={reason}",
                )
            return requested, probe

        candidates: tuple[TrackerEngine, ...]
        if self.platform.casefold() == "ubuntu":
            candidates = ("mediapipe_gpu", "yunet_cuda", "mediapipe_cpu", "yunet_cpu")
        else:
            candidates = ("yunet_cuda", "mediapipe_cpu", "yunet_cpu")
        for engine in candidates:
            probe = self.engines.get(engine)
            if probe is not None and probe.state == "ready":
                return engine, probe
        raise TrackerUnavailable("no_tracker_engine")

    def _resolve_encoder(self, requested: EncoderMode) -> EncoderMode:
        if requested != "auto":
            probe = self.encoders.get(requested, EncoderProbe())
            if probe.state != "ready":
                reason = probe.reason or "no probe result"
                raise EncoderUnavailable(f"nvenc_error: encoder={requested} state={probe.state} reason={reason}")
            return requested
        if self.encoders.get("h264_nvenc", EncoderProbe()).state == "ready":
            return "h264_nvenc"
        return "libx264"


def _engine_probe(value: EngineProbe | tuple[Any, ...] | str | Mapping[str, Any]) -> EngineProbe:
    if isinstance(value, EngineProbe):
        return value
    if isinstance(value, str):
        return EngineProbe(state=value)
    if isinstance(value, Mapping):
        return EngineProbe(
            state=value.get("state", "missing"),
            provider=value.get("provider", ""),
            model_id=value.get("model_id"),
            reason=value.get("reason"),
        )
    state, *details = value
    provider = details[0] if details else ""
    model_id = details[1] if len(details) > 1 else None
    reason = details[2] if len(details) > 2 else None
    return EngineProbe(state=state, provider=provider, model_id=model_id, reason=reason)


def _encoder_probe(value: EncoderProbe | tuple[Any, ...] | str | Mapping[str, Any]) -> EncoderProbe:
    if isinstance(value, EncoderProbe):
        return value
    if isinstance(value, str):
        return EncoderProbe(state=value)
    if isinstance(value, Mapping):
        return EncoderProbe(state=value.get("state", "missing"), reason=value.get("reason"))
    state, *details = value
    return EncoderProbe(state=state, reason=details[0] if details else None)
