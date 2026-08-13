"""FFmpeg helper utilities."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VideoInfo:
    """Basic video metadata from FFprobe."""

    path: Path
    width: int
    height: int
    duration: float
    fps: float
    video_codec: str
    audio_codec: str
    size_bytes: int

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 0

    @property
    def is_vertical(self) -> bool:
        return self.height > self.width

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)

    def __repr__(self) -> str:
        return (
            f"VideoInfo({self.width}x{self.height}, {self.duration:.1f}s, "
            f"{self.fps:.1f}fps, {self.size_mb:.1f}MB)"
        )


def check_ffmpeg() -> tuple[bool, str]:
    """
    Check if FFmpeg is installed and return version.

    Returns:
        (available, version_string)
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return False, ""

    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        first_line = result.stdout.split("\n")[0]
        version = first_line.replace("ffmpeg version ", "").split(" ")[0]
        return True, version
    except (subprocess.SubprocessError, FileNotFoundError, TimeoutError):
        return False, ""


def check_ffprobe() -> bool:
    """Check if FFprobe is available (usually bundled with FFmpeg)."""
    return shutil.which("ffprobe") is not None


def get_video_info(video_path: Path) -> VideoInfo:
    """
    Get video metadata via FFprobe.

    Args:
        video_path: Path to video file

    Returns:
        VideoInfo dataclass

    Raises:
        FileNotFoundError: If video file doesn't exist
        RuntimeError: If FFprobe fails
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(video_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"FFprobe error: {result.stderr}")

        data = json.loads(result.stdout)
    except (subprocess.SubprocessError, TimeoutError) as e:
        raise RuntimeError(f"FFprobe failed: {e}") from e

    # Parse streams
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"), {}
    )
    audio_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {}
    )
    fmt = data.get("format", {})

    # Parse FPS (can be fraction like "30000/1001")
    fps_raw = video_stream.get("r_frame_rate", "30/1")
    try:
        num, den = fps_raw.split("/")
        fps = float(num) / float(den) if float(den) else 30.0
    except (ValueError, ZeroDivisionError):
        fps = 30.0

    return VideoInfo(
        path=video_path,
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        duration=float(fmt.get("duration", 0)),
        fps=fps,
        video_codec=video_stream.get("codec_name", "unknown"),
        audio_codec=audio_stream.get("codec_name", "unknown"),
        size_bytes=int(fmt.get("size", 0)),
    )


def build_crop_filter(
    src_width: int,
    src_height: int,
    target_width: int = 1080,
    target_height: int = 1920,
) -> str:
    """
    Build FFmpeg crop+scale filter to convert any aspect ratio to 9:16.

    Strategy:
    - If source is wider than target ratio: crop sides, scale to target height
    - If source is taller than target ratio: letterbox with blurred background

    Returns:
        FFmpeg filter_complex string
    """
    src_ratio = src_width / src_height
    tgt_ratio = target_width / target_height

    if src_ratio > tgt_ratio:
        # Source is wider (e.g. 16:9) → crop and center
        crop_w = int(src_height * tgt_ratio)
        crop_h = src_height
        x_offset = (src_width - crop_w) // 2
        scale = f"crop={crop_w}:{crop_h}:{x_offset}:0,scale={target_width}:{target_height}"
        return scale
    elif src_ratio < tgt_ratio:
        # Source is taller → letterbox with blurred background
        scale_h = target_height
        scale_w = int(src_width * (target_height / src_height))
        pad_x = (target_width - scale_w) // 2

        # Create blurred background + overlay sharp center
        blur_bg = (
            f"[0:v]scale={target_width}:{target_height},boxblur=20:20[bg];"
            f"[0:v]scale={scale_w}:{scale_h}[fg];"
            f"[bg][fg]overlay={pad_x}:0"
        )
        return blur_bg
    else:
        # Already correct ratio
        return f"scale={target_width}:{target_height}"


def run_ffmpeg(
    args: list[str],
    progress_callback: Callable[[float], None] | None = None,
    duration: float | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    """
    Run an FFmpeg command with optional progress tracking.

    Args:
        args: FFmpeg arguments (without 'ffmpeg' prefix)
        progress_callback: Called with progress 0.0-1.0 during processing
        duration: Total duration in seconds (needed for progress calculation)
        timeout: Max seconds to wait

    Returns:
        CompletedProcess result

    Raises:
        RuntimeError: If FFmpeg exits with non-zero code
    """
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + args

    if progress_callback and duration:
        # Add progress output
        cmd = ["ffmpeg", "-y", "-progress", "pipe:2", "-loglevel", "quiet"] + args[1:] \
            if args[0] == "-y" else ["ffmpeg", "-y", "-progress", "pipe:2", "-loglevel", "quiet"] + args

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def _read_progress():
            assert process.stderr
            current_time = 0.0
            for line in process.stderr:
                line = line.strip()
                if line.startswith("out_time_ms="):
                    try:
                        ms = int(line.split("=")[1])
                        current_time = ms / 1_000_000
                        if duration > 0:
                            progress_callback(min(current_time / duration, 1.0))
                    except (ValueError, IndexError):
                        pass

        t = threading.Thread(target=_read_progress, daemon=True)
        t.start()
        stdout, stderr = process.communicate(timeout=timeout)
        t.join(timeout=5)

        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg failed (code {process.returncode}): {stderr}")

        return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)

    # Simple run without progress
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed (code {result.returncode}):\n{result.stderr}"
        )

    return result


def extract_audio(video_path: Path, output_path: Path) -> Path:
    """
    Extract audio from video as WAV (16kHz mono — optimal for Whisper).

    Args:
        video_path: Source video file
        output_path: Output WAV file path

    Returns:
        Path to extracted audio file
    """
    run_ffmpeg([
        "-i", str(video_path),
        "-ar", "16000",       # 16kHz sample rate (Whisper requirement)
        "-ac", "1",           # Mono
        "-vn",                # No video
        "-f", "wav",
        str(output_path),
    ])
    return output_path
