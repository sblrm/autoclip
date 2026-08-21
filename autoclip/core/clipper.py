"""Video clipper — cuts and exports clips as 9:16 vertical video via FFmpeg."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from autoclip.models.clip import Clip
from autoclip.models.config import OutputConfig
from autoclip.utils.ffmpeg import (
    EncoderCapability,
    VideoEncoding,
    build_crop_filter,
    get_video_info,
    list_video_encoders,
    resolve_video_encoding,
    run_ffmpeg,
    smoke_test_encoder,
)
from autoclip.web.acceleration import (
    AccelerationSelection,
    ResolvedAcceleration,
    TrackerUnavailable,
)
from autoclip.web.acceleration_manager import AccelerationManager


def create_clips(
    video_path: Path,
    clips: list[Clip],
    output_dir: Path,
    output_config: OutputConfig,
    subtitle_paths: dict[int, Path] | None = None,
    tracker_config=None,
    progress_callback=None,
) -> list[Path]:
    """
    Cut and export video clips as 9:16 vertical videos.

    Args:
        video_path: Source video file
        clips: List of detected Clip objects (with timestamps)
        output_dir: Directory to save output clips
        output_config: Output format settings (resolution, codec, etc.)
        subtitle_paths: Optional dict mapping clip index -> ASS subtitle path
        tracker_config: Optional TrackerConfig; if enabled, uses face-tracking crop
        progress_callback: Optional callable(clip_num, total, percent) for progress

    Returns:
        List of output file paths (one per clip)

    Raises:
        FileNotFoundError: If source video doesn't exist
        RuntimeError: If FFmpeg processing fails
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Source video not found: {video_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Decide whether to use face-tracking or static crop
    use_tracker = (
        tracker_config is not None
        and getattr(tracker_config, "enabled", False)
        and output_config.width > 0
        and output_config.height > 0
    )

    resolved_acceleration: ResolvedAcceleration | None = None
    if use_tracker:
        status = AccelerationManager().status()
        requested_engine = getattr(tracker_config, "engine", "auto")
        try:
            resolved_acceleration = status.resolve(
                AccelerationSelection(
                    tracker_engine=requested_engine,
                    encoder_mode=output_config.encoder_mode,
                ),
            )
        except TrackerUnavailable as error:
            message = str(error)
            if not message.startswith("tracker_error:"):
                message = (
                    f"tracker_error: engine={requested_engine} state=unavailable "
                    f"reason={message}"
                )
            raise TrackerUnavailable(
                f"{message}; repair=run 'autoclip web' and recheck acceleration",
            ) from error

    encoding = resolve_video_encoding(
        output_config.encoder_mode,
        _probe_encoder_capabilities(),
    )
    if resolved_acceleration is not None:
        resolved_acceleration = ResolvedAcceleration(
            tracker_engine=resolved_acceleration.tracker_engine,
            encoder_mode=encoding.mode,
            provider=resolved_acceleration.provider,
            model_id=resolved_acceleration.model_id,
        )

    # Pre-compute static crop filter only for intentional tracker-disabled export.
    video_info = get_video_info(video_path)
    crop_filter = build_crop_filter(
        src_width=video_info.width,
        src_height=video_info.height,
        target_width=output_config.width,
        target_height=output_config.height,
    )

    output_paths = []

    for i, clip in enumerate(clips):
        clip_num = i + 1
        if progress_callback:
            progress_callback(clip_num, len(clips), 0.0)

        output_path = _build_output_path(output_dir, clip_num, clip)
        subtitle_path = (subtitle_paths or {}).get(i)

        try:
            if use_tracker:
                _export_clip_tracked(
                    video_path=video_path,
                    clip=clip,
                    output_path=output_path,
                    output_config=output_config,
                    tracker_config=tracker_config,
                    subtitle_path=subtitle_path,
                    encoding=encoding,
                    resolved_acceleration=resolved_acceleration,
                )
            else:
                _export_clip(
                    video_path=video_path,
                    clip=clip,
                    output_path=output_path,
                    crop_filter=crop_filter,
                    output_config=output_config,
                    subtitle_path=subtitle_path,
                    encoding=encoding,
                    progress_cb=lambda pct: progress_callback(clip_num, len(clips), pct)
                    if progress_callback else None,
                )
            output_paths.append(output_path)

            if progress_callback:
                progress_callback(clip_num, len(clips), 1.0)

        except RuntimeError as e:
            import traceback
            traceback.print_exc()
            continue

    return output_paths


def _export_clip_tracked(
    video_path: Path,
    clip: Clip,
    output_path: Path,
    output_config: OutputConfig,
    tracker_config,
    subtitle_path: Path | None = None,
    encoding: VideoEncoding | None = None,
    resolved_acceleration: ResolvedAcceleration | None = None,
) -> None:
    """Export a single clip using face-tracking smart crop."""
    try:
        from autoclip.core.tracker import smart_crop_clip
        smart_crop_clip(
            video_path=video_path,
            output_path=output_path,
            start_time=clip.start_time,
            duration=clip.duration,
            target_width=output_config.width,
            target_height=output_config.height,
            subtitle_path=subtitle_path,
            output_config=output_config,
            ema_alpha=getattr(tracker_config, "ema_alpha", 0.04),
            sample_every_n_frames=getattr(tracker_config, "sample_every_n_frames", 15),
            use_mediapipe=getattr(tracker_config, "use_mediapipe", True),
            deadzone_fraction=getattr(tracker_config, "deadzone_fraction", 0.04),
            encoding=encoding,
            resolved_acceleration=resolved_acceleration,
        )
    except ImportError as error:
        engine = getattr(tracker_config, "engine", "auto")
        raise TrackerUnavailable(
            f"tracker_error: engine={engine} state=missing reason={error}; "
            "repair=run 'autoclip web' and recheck acceleration",
        ) from error


def _export_clip(
    video_path: Path,
    clip: Clip,
    output_path: Path,
    crop_filter: str,
    output_config: OutputConfig,
    subtitle_path: Path | None = None,
    progress_cb=None,
    encoding: VideoEncoding | None = None,
) -> None:
    """Export a single clip with FFmpeg."""

    # Determine if the crop filter uses filter_complex (blurred BG) or vf (simple)
    use_filter_complex = "[bg]" in crop_filter or "[fg]" in crop_filter

    ffmpeg_args = [
        "-ss", str(clip.start_time),          # Seek BEFORE -i for fast seek
        "-i", str(video_path),
        "-t", str(clip.duration),              # Duration to cut
    ]

    if subtitle_path and subtitle_path.exists():
        # Add subtitle overlay. On Windows, escape the path backslashes
        sub_path_str = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
        if use_filter_complex:
            # Append subtitle to existing filter_complex
            vf = f"{crop_filter}[cropped];[cropped]ass='{sub_path_str}'"
            ffmpeg_args += ["-filter_complex", vf]
        else:
            vf = f"{crop_filter},ass='{sub_path_str}'"
            ffmpeg_args += ["-vf", vf]
    else:
        if use_filter_complex:
            ffmpeg_args += ["-filter_complex", crop_filter]
        else:
            ffmpeg_args += ["-vf", crop_filter]

    if encoding is None:
        encoding = VideoEncoding(
            mode="libx264",
            codec="libx264",
            arguments=["-c:v", "libx264", "-crf", "23", "-preset", "medium"],
        )
    ffmpeg_args += encoding.arguments + [
        "-c:a", output_config.audio_codec,
        "-b:a", output_config.audio_bitrate,
        "-movflags", "+faststart",      # Enable streaming-friendly MP4
        "-pix_fmt", "yuv420p",          # Compatibility with all players
        str(output_path),
    ]

    run_ffmpeg(
        ffmpeg_args,
        progress_callback=progress_cb,
        duration=clip.duration,
    )


def _probe_encoder_capabilities() -> Mapping[str, EncoderCapability]:
    """Require one real FFmpeg encode before NVENC can be selected."""
    listed = list_video_encoders()
    capabilities: dict[str, EncoderCapability] = {}
    for mode in ("h264_nvenc", "hevc_nvenc"):
        capabilities[mode] = (
            smoke_test_encoder(mode)
            if mode in listed
            else EncoderCapability.missing(f"{mode} is not listed by FFmpeg")
        )
    return capabilities


def _build_output_path(output_dir: Path, clip_num: int, clip: Clip) -> Path:
    """Build the output file path for a clip."""
    safe_title = _sanitize_title(clip.suggested_title)
    filename = f"clip_{clip_num:02d}_score{clip.score}_{safe_title}.mp4"
    return output_dir / filename


def _sanitize_title(title: str, max_len: int = 40) -> str:
    """Convert a clip title to a safe filename component."""
    safe = re.sub(r'[<>:"/\\|?*\s\x00-\x1f]', "_", title)
    safe = re.sub(r"_+", "_", safe)
    safe = safe[:max_len].strip("_")
    return safe or "clip"
