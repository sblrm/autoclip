from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from autoclip.web.acceleration import ResolvedAcceleration
from autoclip.web.model_catalog import ModelPlan


@dataclass
class FakeProbe:
    system_name: str = "Linux"
    distro_id: str = "ubuntu"
    nvidia: tuple[str, str] | None = ("NVIDIA RTX", "555.42")
    torch_cuda: bool = True
    ort_providers: tuple[str, ...] = ("CPUExecutionProvider", "CUDAExecutionProvider")
    preload_error: Exception | None = None

    def __post_init__(self) -> None:
        self.calls: list[str] = []

    def system(self) -> str:
        self.calls.append("system")
        return self.system_name

    def freedesktop_os_release(self) -> dict[str, str]:
        self.calls.append("freedesktop_os_release")
        return {"ID": self.distro_id}

    def nvidia_info(self) -> tuple[str, str] | None:
        self.calls.append("nvidia_info")
        return self.nvidia

    def torch_cuda_available(self) -> bool:
        self.calls.append("torch_cuda_available")
        return self.torch_cuda

    def onnxruntime_providers(self) -> tuple[str, ...]:
        self.calls.append("onnxruntime_providers")
        return self.ort_providers

    def preload_onnxruntime(self) -> None:
        self.calls.append("preload_onnxruntime")
        if self.preload_error is not None:
            raise self.preload_error

    def nvenc_available(self, encoder: str) -> bool:
        self.calls.append(f"nvenc_available:{encoder}")
        return self.nvidia is not None


class FakeDetector:
    def __init__(self, resolution: ResolvedAcceleration, *, error: Exception | None = None) -> None:
        self.engine = resolution.tracker_engine
        self.provider = resolution.provider
        self.model_id = resolution.model_id
        self.error = error
        self.detect_calls = 0

    def __enter__(self) -> "FakeDetector":
        if self.error is not None:
            raise self.error
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> list[object]:
        assert frame_bgr.shape == (320, 320, 3)
        assert timestamp_ms >= 0
        self.detect_calls += 1
        if self.error is not None:
            raise self.error
        return []


class FakeDetectorFactory:
    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.resolutions: list[ResolvedAcceleration] = []
        self.detectors: list[FakeDetector] = []

    def create(self, resolution: ResolvedAcceleration) -> FakeDetector:
        self.resolutions.append(resolution)
        detector = FakeDetector(resolution, error=self.failures.get(resolution.tracker_engine))
        self.detectors.append(detector)
        return detector


def all_models_available(_: str) -> bool:
    return True


def test_mediapipe_gpu_probe_never_reports_cpu_as_gpu() -> None:
    from autoclip.web.acceleration_manager import AccelerationManager

    factory = FakeDetectorFactory({"mediapipe_gpu": RuntimeError("GPU delegate unavailable")})
    status = AccelerationManager(
        probe=FakeProbe(),
        detector_factory=factory,
        model_available=all_models_available,
    ).status()
    capability = status.engine("mediapipe_gpu")

    assert capability.state == "failed"
    assert capability.provider == "GPUDelegate"
    assert capability.provider != "CPUDelegate"


def test_non_ubuntu_mediapipe_gpu_is_unsupported_without_detector_creation() -> None:
    from autoclip.web.acceleration_manager import AccelerationManager

    factory = FakeDetectorFactory()
    status = AccelerationManager(
        probe=FakeProbe(distro_id="debian"),
        detector_factory=factory,
        model_available=all_models_available,
    ).status()

    assert status.engine("mediapipe_gpu").state == "unsupported"
    assert all(item.tracker_engine != "mediapipe_gpu" for item in factory.resolutions)


def test_missing_cached_model_is_missing_without_detector_creation() -> None:
    from autoclip.web.acceleration_manager import AccelerationManager

    factory = FakeDetectorFactory()
    status = AccelerationManager(
        probe=FakeProbe(),
        detector_factory=factory,
        model_available=lambda model_id: model_id != "yunet_2023mar",
    ).status()

    assert status.engine("yunet_cuda").state == "missing"
    assert all(item.tracker_engine != "yunet_cuda" for item in factory.resolutions)


def test_cuda_session_exception_is_failed_with_scrubbed_detail() -> None:
    from autoclip.web.acceleration_manager import AccelerationManager

    secret = r"C:\Users\private\yunet.onnx token=hunter2"
    factory = FakeDetectorFactory({"yunet_cuda": RuntimeError(secret)})
    status = AccelerationManager(
        probe=FakeProbe(),
        detector_factory=factory,
        model_available=all_models_available,
    ).status()

    capability = status.engine("yunet_cuda")
    assert capability.state == "failed"
    assert capability.provider == "CUDAExecutionProvider"
    assert capability.reason is not None
    assert "private" not in capability.reason
    assert "hunter2" not in capability.reason


def test_empty_face_result_proves_live_inference_without_fallback() -> None:
    from autoclip.web.acceleration_manager import AccelerationManager

    factory = FakeDetectorFactory()
    probe = FakeProbe()
    status = AccelerationManager(
        probe=probe,
        detector_factory=factory,
        model_available=all_models_available,
    ).status()

    capability = status.engine("yunet_cuda")
    gpu_detector = next(item for item in factory.detectors if item.engine == "yunet_cuda")
    assert capability.state == "ready"
    assert capability.provider == "CUDAExecutionProvider"
    assert gpu_detector.detect_calls == 1
    assert "nvidia_info" in probe.calls
    assert "torch_cuda_available" in probe.calls
    assert "onnxruntime_providers" in probe.calls
    assert "preload_onnxruntime" in probe.calls


def test_default_model_cache_check_validates_size_and_sha256(
    monkeypatch: object,
    tmp_path: object,
) -> None:
    import pytest

    from autoclip.web.acceleration_manager import AccelerationManager

    monkeypatch = monkeypatch  # type: ignore[assignment]
    tmp_path = Path(str(tmp_path))
    payload = b"detector-only-model"
    plan = ModelPlan(
        id="yunet_2023mar",
        label="fixture",
        source_url="https://example.invalid/yunet.onnx",
        sha256=hashlib.sha256(payload).hexdigest(),
        bytes=len(payload),
        license="MIT",
        research_only=False,
        destination_relative_path="yunet/model.onnx",
    )
    model_path = tmp_path / "yunet" / "model.onnx"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(payload)
    factory = FakeDetectorFactory()
    manager = AccelerationManager(
        probe=FakeProbe(),
        detector_factory=factory,
        models_root=tmp_path,
        model_plans={plan.id: plan},
    )

    assert manager.status().engine("yunet_cpu").state == "ready"

    model_path.write_bytes(b"x" * len(payload))
    assert manager.status().engine("yunet_cpu").state == "missing"


def test_live_status_contains_all_detector_families() -> None:
    from autoclip.web.acceleration_manager import AccelerationManager

    status = AccelerationManager(
        probe=FakeProbe(),
        detector_factory=FakeDetectorFactory(),
        model_available=all_models_available,
    ).status()

    assert set(status.engines) == {
        "mediapipe_cpu",
        "mediapipe_gpu",
        "yunet_cpu",
        "yunet_cuda",
        "scrfd_cpu",
        "scrfd_cuda",
        "retinaface_cpu",
        "retinaface_cuda",
    }
