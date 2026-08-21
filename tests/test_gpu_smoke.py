"""Opt-in tests that prove real local GPU inference and encoding readiness."""

from __future__ import annotations

import os

import pytest

from autoclip.utils.ffmpeg import smoke_test_encoder
from autoclip.web.acceleration_manager import AccelerationManager


def _require_gpu_smoke() -> None:
    if os.environ.get("AUTOCLIP_RUN_GPU_SMOKE") != "1":
        pytest.skip(
            "GPU smoke disabled; set AUTOCLIP_RUN_GPU_SMOKE=1 to probe real hardware",
        )


@pytest.mark.gpu
def test_windows_yunet_cuda_live_smoke() -> None:
    _require_gpu_smoke()
    status = AccelerationManager().status()
    if status.platform.casefold() != "windows":
        pytest.skip("Windows YuNet CUDA smoke requires Windows")

    capability = status.engine("yunet_cuda")

    assert capability.state == "ready", capability.reason
    assert capability.provider == "CUDAExecutionProvider"


@pytest.mark.gpu
def test_ubuntu_mediapipe_gpu_live_video_smoke() -> None:
    _require_gpu_smoke()
    status = AccelerationManager().status()
    if status.platform.casefold() != "ubuntu":
        pytest.skip("MediaPipe GPU smoke requires Ubuntu")

    capability = status.engine("mediapipe_gpu")

    assert capability.state == "ready", capability.reason
    assert capability.provider == "GPUDelegate"


@pytest.mark.gpu
def test_nvenc_live_smoke() -> None:
    _require_gpu_smoke()
    capability = AccelerationManager().status().encoder("h264_nvenc")
    smoke = smoke_test_encoder("h264_nvenc")

    assert capability.state == "ready", capability.reason
    assert smoke.state == "ready", smoke.reason
