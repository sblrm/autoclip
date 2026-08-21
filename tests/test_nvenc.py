from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_list_video_encoders_ignores_audio_and_subtitle_rows() -> None:
    from autoclip.utils.ffmpeg import list_video_encoders

    output = """
Encoders:
 V..... = Video
 A..... = Audio
 S..... = Subtitle
 V....D h264_nvenc          NVIDIA NVENC H.264 encoder
 V..... hevc_nvenc          NVIDIA NVENC hevc encoder
 A..... h264_nvenc_audio    misleading audio encoder
 S..... h264_nvenc_subtitle misleading subtitle encoder
"""

    encoders = list_video_encoders(lambda _command: SimpleNamespace(returncode=0, output=output))

    assert encoders == {"h264_nvenc", "hevc_nvenc"}


def test_smoke_test_encoder_runs_one_frame_ffmpeg_probe() -> None:
    from autoclip.utils.ffmpeg import EncoderCapability, smoke_test_encoder

    commands: list[list[str]] = []

    def runner(command: list[str]) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=0, output="")

    capability = smoke_test_encoder("h264_nvenc", runner)

    assert capability == EncoderCapability.ready()
    assert commands == [[
        "ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i",
        "color=c=black:s=640x360:d=0.1", "-frames:v", "1", "-c:v",
        "h264_nvenc", "-f", "null", "-",
    ]]


def test_auto_selects_verified_h264_nvenc() -> None:
    from autoclip.utils.ffmpeg import EncoderCapability, resolve_video_encoding

    encoding = resolve_video_encoding(
        "auto",
        {"h264_nvenc": EncoderCapability.ready()},
    )

    assert encoding.mode == "h264_nvenc"
    assert encoding.codec == "h264_nvenc"
    assert encoding.arguments == [
        "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-b:v", "0",
    ]


def test_auto_uses_libx264_when_nvenc_smoke_test_failed() -> None:
    from autoclip.utils.ffmpeg import EncoderCapability, resolve_video_encoding

    encoding = resolve_video_encoding(
        "auto",
        {"h264_nvenc": EncoderCapability.failed("No NVENC capable devices found")},
    )

    assert encoding.mode == "libx264"
    assert encoding.arguments == [
        "-c:v", "libx264", "-crf", "23", "-preset", "medium",
    ]


def test_explicit_nvenc_smoke_failure_stays_structured() -> None:
    from autoclip.utils.ffmpeg import EncoderCapability, resolve_video_encoding
    from autoclip.web.acceleration import EncoderUnavailable

    with pytest.raises(EncoderUnavailable, match=r"nvenc_error.*No NVENC capable devices found"):
        resolve_video_encoding(
            "h264_nvenc",
            {"h264_nvenc": EncoderCapability.failed("No NVENC capable devices found")},
        )


@pytest.mark.parametrize(
    ("mode", "arguments"),
    [
        ("libx264", ["-c:v", "libx264", "-crf", "23", "-preset", "medium"]),
        ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-b:v", "0"]),
        ("hevc_nvenc", ["-c:v", "hevc_nvenc", "-preset", "p5", "-cq", "25", "-b:v", "0"]),
    ],
)
def test_resolved_video_encoding_has_strict_ffmpeg_arguments(
    mode: str,
    arguments: list[str],
) -> None:
    from autoclip.utils.ffmpeg import EncoderCapability, resolve_video_encoding

    encoding = resolve_video_encoding(  # type: ignore[arg-type]
        mode,
        {mode: EncoderCapability.ready()},
    )

    assert encoding.arguments == arguments


def test_apply_face_crop_uses_resolved_video_arguments_and_preserves_aac(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autoclip.core.tracker import CropTrajectory, apply_face_crop
    from autoclip.utils.ffmpeg import EncoderCapability, resolve_video_encoding

    cv2 = MagicMock()
    cv2.CAP_PROP_POS_MSEC = 0
    cv2.VideoCapture.return_value = MagicMock()
    cv2.VideoWriter_fourcc.return_value = 1
    cv2.VideoWriter.return_value = MagicMock()
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    captured: list[str] = []

    def fake_run_ffmpeg(arguments: list[str], **_kwargs: object) -> None:
        captured.extend(arguments)

    monkeypatch.setattr("autoclip.utils.ffmpeg.run_ffmpeg", fake_run_ffmpeg)
    encoding = resolve_video_encoding(
        "h264_nvenc",
        {"h264_nvenc": EncoderCapability.ready()},
    )

    apply_face_crop(
        video_path=tmp_path / "source.mp4",
        output_path=tmp_path / "output.mp4",
        trajectory=CropTrajectory([], 30.0, 1920, 1080),
        start_time=0,
        duration=1,
        encoding=encoding,
    )

    video_start = captured.index("-c:v")
    assert captured[video_start:video_start + len(encoding.arguments)] == encoding.arguments
    audio_start = captured.index("-c:a")
    assert captured[audio_start:audio_start + 2] == ["-c:a", "aac"]
