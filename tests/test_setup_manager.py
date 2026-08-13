from __future__ import annotations

import sys

import pytest


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
    ) -> None:
        self.ffmpeg = ffmpeg
        self.opencv = opencv
        self.mediapipe = mediapipe
        self.whisper = whisper
        self.torch = torch
        self.cuda = cuda
        self.adapter = adapter
        self.driver = driver

    def executable_version(self, name: str) -> str | None:
        return {"ffmpeg": self.ffmpeg}.get(name)

    def package_version(self, name: str) -> str | None:
        return {
            "cv2": self.opencv,
            "mediapipe": self.mediapipe,
            "whisper": self.whisper,
            "torch": self.torch,
        }.get(name)

    def cuda_available(self) -> bool:
        return self.cuda

    def nvidia_adapter(self) -> tuple[str | None, str | None]:
        return self.adapter, self.driver


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


def test_gpu_install_plan_reinstalls_matching_torch_version_from_official_cuda_index() -> None:
    from autoclip.web.setup_manager import SetupManager

    plan = SetupManager(probe=FakeProbe()).install_plan("whisper_gpu")

    assert plan.requires_restart is True
    assert plan.command == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--force-reinstall",
        "torch==2.12.0",
        "torchaudio==2.12.0",
        "--index-url",
        "https://download.pytorch.org/whl/cu130",
    ]


def test_unknown_install_component_is_rejected() -> None:
    from autoclip.web.setup_manager import SetupManager

    with pytest.raises(ValueError, match="Unsupported setup component"):
        SetupManager(probe=FakeProbe()).install_plan("arbitrary-command")
