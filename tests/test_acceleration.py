"""Tests for stable GPU acceleration selection contracts."""

from __future__ import annotations

import pytest
import autoclip.web.acceleration as acceleration

from autoclip.web.acceleration import AccelerationSelection, AccelerationStatus, EncoderUnavailable, TrackerUnavailable


def test_auto_prefers_verified_yunet_cuda_on_windows() -> None:
    status = AccelerationStatus.for_test(platform="Windows", engines={"yunet_cuda": ("ready", "CUDAExecutionProvider")}, encoders={"h264_nvenc": "ready"})
    resolved = status.resolve(AccelerationSelection())
    assert resolved.tracker_engine == "yunet_cuda"
    assert resolved.encoder_mode == "h264_nvenc"
    assert resolved.provider == "CUDAExecutionProvider"

def test_default_status_detects_ubuntu_before_selecting_a_tracker(monkeypatch) -> None:
    monkeypatch.setattr(acceleration.platform_module, "system", lambda: "Linux")
    monkeypatch.setattr(
        acceleration,
        "_read_os_release",
        lambda: "ID=ubuntu\nID_LIKE=debian\n",
        raising=False,
    )
    status = acceleration.AccelerationStatus(
        engines={
            "mediapipe_gpu": ("ready", "GPUDelegate"),
            "yunet_cuda": ("ready", "CUDAExecutionProvider"),
        },
    )

    assert status.platform == "Ubuntu"
    assert status.resolve(acceleration.AccelerationSelection()).tracker_engine == "mediapipe_gpu"



def test_explicit_nvenc_never_becomes_cpu() -> None:
    status = AccelerationStatus.for_test(
        engines={"mediapipe_cpu": ("ready", "CPUDelegate")},
        encoders={"h264_nvenc": "failed"},
    )
    with pytest.raises(EncoderUnavailable, match="nvenc_error"):
        status.resolve(AccelerationSelection(encoder_mode="h264_nvenc"))


def test_auto_prefers_mediapipe_gpu_on_ubuntu() -> None:
    status = AccelerationStatus.for_test(platform="Ubuntu", engines={"mediapipe_gpu": ("ready", "GPUDelegate"), "yunet_cuda": ("ready", "CUDAExecutionProvider")})
    assert status.resolve(AccelerationSelection()).tracker_engine == "mediapipe_gpu"


def test_auto_uses_yunet_cuda_after_unavailable_ubuntu_mediapipe_gpu() -> None:
    status = AccelerationStatus.for_test(platform="Ubuntu", engines={"mediapipe_gpu": ("failed", "GPUDelegate", None, "delegate unavailable"), "yunet_cuda": ("ready", "CUDAExecutionProvider")})
    assert status.resolve(AccelerationSelection()).tracker_engine == "yunet_cuda"


def test_auto_uses_mediapipe_cpu_when_no_gpu_engine_is_ready() -> None:
    status = AccelerationStatus.for_test(engines={"mediapipe_cpu": ("ready", "CPUDelegate")})
    resolved = status.resolve(AccelerationSelection())
    assert resolved.tracker_engine == "mediapipe_cpu"
    assert resolved.encoder_mode == "libx264"


def test_auto_raises_when_no_tracker_engine_is_ready() -> None:
    with pytest.raises(TrackerUnavailable, match="no_tracker_engine"):
        AccelerationStatus.for_test().resolve(AccelerationSelection())


def test_explicit_unavailable_tracker_reports_engine_state_and_reason() -> None:
    status = AccelerationStatus.for_test(engines={"scrfd_cuda": ("failed", "CUDAExecutionProvider", None, "model load failed")})
    with pytest.raises(TrackerUnavailable, match=r"scrfd_cuda.*failed.*model load failed"):
        status.resolve(AccelerationSelection(tracker_engine="scrfd_cuda"))


def test_explicit_hevc_nvenc_resolves_when_ready() -> None:
    status = AccelerationStatus.for_test(engines={"yunet_cpu": ("ready", "CPUExecutionProvider")}, encoders={"hevc_nvenc": "ready"})
    assert status.resolve(AccelerationSelection(encoder_mode="hevc_nvenc")).encoder_mode == "hevc_nvenc"
