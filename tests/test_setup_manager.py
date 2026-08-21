from __future__ import annotations

import sys

import pytest

from autoclip.web.acceleration import AccelerationStatus


class FakeProbe:
    def __init__(
        self,
        *,
        ffmpeg: str | None = None,
        opencv: str | None = None,
        mediapipe: str | None = None,
        whisper: str | None = None,
        torch: str | None = "2.12.0+cpu",
        cuda: bool = False,
        adapter: str | None = "NVIDIA GeForce RTX 5070",
        driver: str | None = "610.88",
        onnxruntime: str | None = None,
        ort_providers: tuple[str, ...] = (),
    ) -> None:
        self.ffmpeg = ffmpeg
        self.opencv = opencv
        self.mediapipe = mediapipe
        self.whisper = whisper
        self.torch = torch
        self.cuda = cuda
        self.adapter = adapter
        self.driver = driver
        self.onnxruntime = onnxruntime
        self.ort_providers = ort_providers

    def executable_version(self, name: str) -> str | None:
        return {"ffmpeg": self.ffmpeg}.get(name)

    def package_version(self, name: str) -> str | None:
        return {
            "cv2": self.opencv,
            "mediapipe": self.mediapipe,
            "whisper": self.whisper,
            "torch": self.torch,
            "onnxruntime": self.onnxruntime,
        }.get(name)

    def cuda_available(self) -> bool:
        return self.cuda

    def nvidia_adapter(self) -> tuple[str | None, str | None]:
        return self.adapter, self.driver

    def onnxruntime_providers(self) -> tuple[str, ...]:
        return self.ort_providers


def test_status_identifies_missing_tools_and_component_specific_acceleration() -> None:
    from autoclip.web.setup_manager import SetupManager

    status = SetupManager(probe=FakeProbe()).status()
    components = {component.id: component for component in status.components}

    assert status.hardware.adapter == "NVIDIA GeForce RTX 5070"
    assert status.hardware.gpu_ready is False
    assert status.is_ready is False
    assert components["ffmpeg"].state == "missing"
    assert components["opencv"].state == "missing"
    assert components["whisper"].acceleration == "cpu"
    assert components["face_tracking"].acceleration == "cpu"


def test_working_cu128_torch_is_preserved_without_reinstall() -> None:
    from autoclip.web.setup_manager import SetupManager

    manager = SetupManager(probe=FakeProbe(torch="2.11.0+cu128", cuda=True))

    with pytest.raises(ValueError, match="already active"):
        manager.install_plan("whisper_gpu")


def test_onnxruntime_cuda_plan_is_pinned_to_cuda_128_runtime() -> None:
    from autoclip.web.setup_manager import SetupManager

    plan = SetupManager(probe=FakeProbe()).install_plan("onnxruntime_cuda_128")

    assert plan.requires_restart is False
    assert plan.command == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "onnxruntime-gpu[cuda,cudnn]==1.26.0",
    ]


def test_torch_and_gpu_torch_have_fixed_install_plans() -> None:
    from autoclip.web.setup_manager import SetupManager

    manager = SetupManager(probe=FakeProbe(torch=None))

    cpu_plan = manager.install_plan("torch")
    gpu_plan = manager.install_plan("pytorch_cuda_128")

    assert cpu_plan.command == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "torch",
        "torchaudio",
        "--index-url",
        "https://download.pytorch.org/whl/cpu",
    ]
    assert gpu_plan.command[-3:] == ["torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"]


def test_gpu_torch_install_refuses_cpu_only_machine() -> None:
    from autoclip.web.setup_manager import SetupManager

    with pytest.raises(ValueError, match="NVIDIA GPU not detected"):
        SetupManager(probe=FakeProbe(adapter=None, driver=None)).install_plan("pytorch_cuda_128")


def test_status_exposes_verified_tracker_and_encoder_evidence() -> None:
    from autoclip.web.setup_manager import SetupManager

    class StaticAccelerationManager:
        def status(self) -> AccelerationStatus:
            return AccelerationStatus.for_test(
                platform="Windows",
                engines={
                    "mediapipe_cpu": ("ready", "CPUDelegate"),
                    "mediapipe_gpu": (
                        "unsupported",
                        "GPUDelegate",
                        None,
                        "Ubuntu only",
                    ),
                    "yunet_cpu": ("ready", "CPUExecutionProvider", "yunet_2023mar"),
                    "yunet_cuda": (
                        "missing",
                        "CUDAExecutionProvider",
                        "yunet_2023mar",
                        "model missing",
                    ),
                },
                encoders={
                    "libx264": "ready",
                    "h264_nvenc": "ready",
                    "hevc_nvenc": ("unsupported", "encoder unavailable"),
                },
            )

    status = SetupManager(
        probe=FakeProbe(
            ffmpeg="7.1",
            opencv="4.10",
            mediapipe="0.10",
            whisper="20250625",
            torch="2.11.0+cu128",
            cuda=True,
            onnxruntime="1.26.0",
            ort_providers=("CPUExecutionProvider", "CUDAExecutionProvider"),
        ),
        acceleration_manager=StaticAccelerationManager(),
    ).status()
    components = {component.id: component for component in status.components}

    assert components["whisper"].provider == "PyTorch CUDA"
    assert components["torch"].version == "2.11.0+cu128"
    assert components["onnxruntime_cuda_128"].provider == "CUDAExecutionProvider"
    assert components["mediapipe_cpu"].provider == "CPUDelegate"
    assert components["mediapipe_gpu"].probe_detail == "Ubuntu only"
    assert components["yunet_cpu"].model_id == "yunet_2023mar"
    assert components["yunet_cuda"].state == "missing"
    assert components["ffmpeg_h264_nvenc"].state == "ready"
    assert components["ffmpeg_hevc_nvenc"].error_code == "nvenc_error"


def test_cpu_only_onnxruntime_is_not_reported_as_cuda_ready() -> None:
    from autoclip.web.setup_manager import SetupManager

    class ModelMissingAccelerationManager:
        def status(self) -> AccelerationStatus:
            return AccelerationStatus.for_test(
                engines={
                    "yunet_cuda": (
                        "missing",
                        "CUDAExecutionProvider",
                        "yunet_2023mar",
                        "model missing",
                    ),
                },
            )

    status = SetupManager(
        probe=FakeProbe(
            onnxruntime="1.26.0",
            ort_providers=("CPUExecutionProvider",),
        ),
        acceleration_manager=ModelMissingAccelerationManager(),
    ).status()
    components = {component.id: component for component in status.components}

    assert components["onnxruntime_cuda_128"].state == "unsupported"
    assert "CUDAExecutionProvider" in (components["onnxruntime_cuda_128"].probe_detail or "")


def test_unknown_install_component_is_rejected() -> None:
    from autoclip.web.setup_manager import SetupManager

    with pytest.raises(ValueError, match="Unsupported setup component"):
        SetupManager(probe=FakeProbe()).install_plan("arbitrary-command")


def test_ubuntu_ffmpeg_plan_is_fixed_pkexec_apt_get() -> None:
    from autoclip.web.setup_manager import SetupManager

    plan = SetupManager(probe=FakeProbe(), platform_name="Ubuntu").install_plan("ffmpeg")

    assert plan.command == ["pkexec", "apt-get", "install", "-y", "ffmpeg"]


def test_ffmpeg_plan_rejects_unsupported_system_package_platform() -> None:
    from autoclip.web.setup_manager import SetupManager

    with pytest.raises(ValueError, match="unsupported_platform"):
        SetupManager(probe=FakeProbe(), platform_name="Darwin").install_plan("ffmpeg")
