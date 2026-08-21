"""Live local acceleration probes; readiness always includes real inference."""

from __future__ import annotations

import platform
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol, cast

import numpy as np

from autoclip.utils.ffmpeg import (
    EncoderCapability,
    list_video_encoders,
    smoke_test_encoder,
)
from autoclip.web.acceleration import (
    AccelerationStatus,
    EncoderProbe,
    EngineProbe,
    ResolvedAcceleration,
    TrackerEngine,
    TrackerUnavailable,
)
from autoclip.web.detectors import DetectorFactory
from autoclip.web.model_catalog import MODEL_PLANS, ModelPlan
from autoclip.web.model_manager import ModelManager


class Probe(Protocol):
    def system(self) -> str: ...

    def freedesktop_os_release(self) -> Mapping[str, str]: ...

    def nvidia_info(self) -> tuple[str, str] | None: ...

    def torch_cuda_available(self) -> bool: ...

    def onnxruntime_providers(self) -> tuple[str, ...]: ...

    def preload_onnxruntime(self) -> None: ...

    def nvenc_available(self, encoder: str) -> bool: ...


class RuntimeProbe:
    """Read current machine capabilities without claiming detector readiness."""

    def system(self) -> str:
        return platform.system()

    def freedesktop_os_release(self) -> Mapping[str, str]:
        if not hasattr(platform, "freedesktop_os_release"):
            return {}
        try:
            return platform.freedesktop_os_release()
        except OSError:
            return {}

    def nvidia_info(self) -> tuple[str, str] | None:
        try:
            completed = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version",
                    "--format=csv,noheader",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return None
        first_line = completed.stdout.splitlines()[0].strip() if completed.stdout else ""
        name, separator, driver = first_line.partition(",")
        if not separator or not name.strip() or not driver.strip():
            return None
        return name.strip(), driver.strip()

    def torch_cuda_available(self) -> bool:
        try:
            import torch
        except ImportError:
            return False
        return bool(torch.cuda.is_available())

    def onnxruntime_providers(self) -> tuple[str, ...]:
        try:
            import onnxruntime
        except ImportError:
            return ()
        return tuple(str(provider) for provider in onnxruntime.get_available_providers())

    def preload_onnxruntime(self) -> None:
        import onnxruntime

        onnxruntime.preload_dlls()

    def nvenc_available(self, encoder: str) -> bool:
        return self.nvenc_smoke(encoder).state == "ready"

    def nvenc_smoke(self, encoder: str) -> EncoderCapability:
        """Require FFmpeg enumeration plus one real encoded frame."""
        if encoder not in list_video_encoders():
            return EncoderCapability.missing(f"{encoder} is not listed by FFmpeg")
        return smoke_test_encoder(encoder)  # type: ignore[arg-type]

class LiveAccelerationStatus(AccelerationStatus):
    """Acceleration status with convenient named capability lookup."""

    def engine(self, name: str) -> EngineProbe:
        return self.engines.get(name, EngineProbe())

    def encoder(self, name: str) -> EncoderProbe:
        return self.encoders.get(name, EncoderProbe())


ModelAvailable = Callable[[str], bool]


class AccelerationManager:
    """Build immutable capability state from dependency checks and live inference."""

    _MODEL_IDS: Mapping[TrackerEngine, str] = {
        "yunet_cpu": "yunet_2023mar",
        "yunet_cuda": "yunet_2023mar",
        "scrfd_cpu": "insightface_antelopev2_scrfd",
        "scrfd_cuda": "insightface_antelopev2_scrfd",
        "retinaface_cpu": "insightface_buffalo_m_retinaface",
        "retinaface_cuda": "insightface_buffalo_m_retinaface",
    }

    def __init__(
        self,
        *,
        probe: Probe | None = None,
        detector_factory: object | None = None,
        models_root: Path | None = None,
        model_plans: Mapping[str, ModelPlan] | None = None,
        model_available: ModelAvailable | None = None,
    ) -> None:
        self._probe = probe or RuntimeProbe()
        self._models_root = (models_root or Path.home() / ".autoclip" / "models").expanduser()
        self._model_plans = model_plans or MODEL_PLANS
        self._model_available_override = model_available
        self._model_manager = ModelManager(self._models_root, model_plans=self._model_plans)
        self._detector_factory = detector_factory or DetectorFactory(models_root=self._models_root)

    def status(self) -> LiveAccelerationStatus:
        system = self._safe_system()
        is_ubuntu = self._is_ubuntu(system)
        display_platform = "Ubuntu" if is_ubuntu else system
        nvidia = self._safe_nvidia_info()
        torch_cuda = self._safe_bool(self._probe.torch_cuda_available)
        ort_providers = self._safe_ort_providers()
        preload_error = self._preload_error()

        engines: dict[str, EngineProbe] = {
            "mediapipe_cpu": self._probe_detector(
                "mediapipe_cpu",
                provider="CPUDelegate",
                model_id=None,
            ),
        }
        if is_ubuntu:
            engines["mediapipe_gpu"] = self._probe_detector(
                "mediapipe_gpu",
                provider="GPUDelegate",
                model_id=None,
            )
        else:
            engines["mediapipe_gpu"] = EngineProbe(
                state="unsupported",
                provider="GPUDelegate",
                reason="MediaPipe GPU is supported only on Ubuntu",
            )

        for family in ("yunet", "scrfd", "retinaface"):
            cpu_engine = cast(TrackerEngine, f"{family}_cpu")
            cuda_engine = cast(TrackerEngine, f"{family}_cuda")
            model_id = self._MODEL_IDS[cpu_engine]
            engines[cpu_engine] = self._probe_onnx_engine(
                cpu_engine,
                provider="CPUExecutionProvider",
                model_id=model_id,
                providers=ort_providers,
                preload_error=preload_error,
                cuda_environment_ready=True,
            )
            engines[cuda_engine] = self._probe_onnx_engine(
                cuda_engine,
                provider="CUDAExecutionProvider",
                model_id=model_id,
                providers=ort_providers,
                preload_error=preload_error,
                cuda_environment_ready=nvidia is not None and torch_cuda,
            )

        encoders = {
            "libx264": EncoderProbe(state="ready"),
            "h264_nvenc": self._probe_encoder("h264_nvenc", nvidia),
            "hevc_nvenc": self._probe_encoder("hevc_nvenc", nvidia),
        }
        return LiveAccelerationStatus(
            platform=display_platform,
            engines=engines,
            encoders=encoders,
        )

    def _probe_onnx_engine(
        self,
        engine: TrackerEngine,
        *,
        provider: str,
        model_id: str,
        providers: tuple[str, ...],
        preload_error: Exception | None,
        cuda_environment_ready: bool,
    ) -> EngineProbe:
        if not self._model_available(model_id):
            return EngineProbe(
                state="missing",
                provider=provider,
                model_id=model_id,
                reason="Verified detector model is not cached",
            )
        if provider not in providers:
            return EngineProbe(
                state="unsupported",
                provider=provider,
                model_id=model_id,
                reason=f"{provider} is unavailable",
            )
        if provider == "CUDAExecutionProvider" and not cuda_environment_ready:
            return EngineProbe(
                state="unsupported",
                provider=provider,
                model_id=model_id,
                reason="NVIDIA CUDA runtime checks did not pass",
            )
        if preload_error is not None:
            return EngineProbe(
                state="failed",
                provider=provider,
                model_id=model_id,
                reason=f"ONNX Runtime preload failed ({type(preload_error).__name__})",
            )
        return self._probe_detector(engine, provider=provider, model_id=model_id)

    def _probe_detector(
        self,
        engine: TrackerEngine,
        *,
        provider: str,
        model_id: str | None,
    ) -> EngineProbe:
        resolution = ResolvedAcceleration(
            tracker_engine=engine,
            encoder_mode="libx264",
            provider=provider,
            model_id=model_id,
        )
        try:
            create = getattr(self._detector_factory, "create")
            detector = create(resolution)
            with detector as active:
                if active.engine != engine or active.provider != provider:
                    raise TrackerUnavailable(f"{engine} returned a different provider")
                frame = np.zeros((320, 320, 3), dtype=np.uint8)
                active.detect(frame, 0)
        except Exception as exc:
            return EngineProbe(
                state="failed",
                provider=provider,
                model_id=model_id,
                reason=f"{engine} live probe failed ({type(exc).__name__})",
            )
        return EngineProbe(state="ready", provider=provider, model_id=model_id)

    def _model_available(self, model_id: str) -> bool:
        if self._model_available_override is not None:
            try:
                return bool(self._model_available_override(model_id))
            except Exception:
                return False
        return self._model_manager.is_installed(model_id)

    def _is_ubuntu(self, system: str) -> bool:
        if system.casefold() != "linux":
            return False
        try:
            return self._probe.freedesktop_os_release().get("ID", "").casefold() == "ubuntu"
        except Exception:
            return False

    def _safe_system(self) -> str:
        try:
            return str(self._probe.system())
        except Exception:
            return "Unknown"

    def _safe_nvidia_info(self) -> tuple[str, str] | None:
        try:
            value = self._probe.nvidia_info()
        except Exception:
            return None
        if value is None or len(value) != 2 or not value[0] or not value[1]:
            return None
        return value

    def _safe_ort_providers(self) -> tuple[str, ...]:
        try:
            return tuple(self._probe.onnxruntime_providers())
        except Exception:
            return ()

    def _preload_error(self) -> Exception | None:
        try:
            self._probe.preload_onnxruntime()
        except Exception as exc:
            return exc
        return None

    @staticmethod
    def _safe_bool(call: Callable[[], bool]) -> bool:
        try:
            return bool(call())
        except Exception:
            return False

    def _probe_encoder(self, encoder: str, nvidia: tuple[str, str] | None) -> EncoderProbe:
        if nvidia is None:
            return EncoderProbe(state="unsupported", reason="NVIDIA GPU or driver is unavailable")
        smoke = getattr(self._probe, "nvenc_smoke", None)
        if callable(smoke):
            try:
                capability = smoke(encoder)
            except Exception as exc:
                return EncoderProbe(
                    state="failed",
                    reason=f"NVENC smoke failed ({type(exc).__name__})",
                )
            state = getattr(capability, "state", "failed")
            reason = getattr(capability, "reason", None)
            if state == "ready":
                return EncoderProbe(state="ready")
            if state == "missing":
                return EncoderProbe(state="unsupported", reason=reason)
            return EncoderProbe(state="failed", reason=reason or f"{encoder} smoke failed")
        try:
            available = self._probe.nvenc_available(encoder)
        except Exception as exc:
            return EncoderProbe(
                state="failed",
                reason=f"NVENC probe failed ({type(exc).__name__})",
            )
        if available:
            return EncoderProbe(state="ready")
        return EncoderProbe(state="unsupported", reason=f"{encoder} is unavailable")
