"""Face tracking and smart crop for AutoClip.

Uses MediaPipe FaceDetection to detect the dominant speaker's face position
per frame, then applies Exponential Moving Average (EMA) smoothing to produce
a stable crop trajectory that follows the face — no more static center-crop.

Pipeline:
    video_path  →  extract clip segment  →  face-detect (sampled frames)
                →  EMA smooth trajectory  →  frame-by-frame crop
                →  OpenCV VideoWriter    →  FFmpeg re-encode with audio
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import numpy as np


# ─── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class FacePosition:
    """Detected face center position (0.0–1.0 normalized)."""
    cx: float  # Horizontal center (0 = left, 1 = right)
    cy: float  # Vertical center   (0 = top,  1 = bottom)
    confidence: float = 1.0


@dataclass
class CropTrajectory:
    """Per-frame crop center points (pixel coordinates in source video)."""
    centers: list[tuple[float, float]] = field(default_factory=list)
    fps: float = 30.0
    src_width: int = 0
    src_height: int = 0

    def __len__(self) -> int:
        return len(self.centers)


# ─── MediaPipe helpers ────────────────────────────────────────────────────────


def _is_mediapipe_available() -> bool:
    """Check if MediaPipe with the legacy solutions API is usable.

    MediaPipe >=0.10.14 removed mp.solutions — this guards against that.
    Falls back to OpenCV Haar cascade in that case.
    """
    try:
        import mediapipe as mp
        # Verify the specific sub-module we actually use exists
        return hasattr(mp, "solutions") and hasattr(mp.solutions, "face_detection")
    except ImportError:
        return False


def _detect_faces_mediapipe(frame_rgb) -> list[FacePosition]:
    """Detect faces in a single RGB frame using MediaPipe FaceDetection.

    Raises AttributeError if mp.solutions is not available (mediapipe >=0.10.14).
    Caller should catch and fall back to OpenCV.
    """
    import mediapipe as mp

    with mp.solutions.face_detection.FaceDetection(
        model_selection=1,       # 1 = full-range model (up to ~5m)
        min_detection_confidence=0.4,
    ) as detector:
        results = detector.process(frame_rgb)

    if not results.detections:
        return []

    faces = []
    for det in results.detections:
        bbox = det.location_data.relative_bounding_box
        cx = bbox.xmin + bbox.width / 2
        cy = bbox.ymin + bbox.height / 2
        conf = det.score[0] if det.score else 1.0
        faces.append(FacePosition(cx=cx, cy=cy, confidence=conf))

    return faces


def _detect_faces_opencv(frame_gray) -> list[FacePosition]:
    """Fallback face detection using OpenCV Haar cascades."""
    import cv2
    import numpy as np

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)

    h, w = frame_gray.shape[:2]
    faces_raw = cascade.detectMultiScale(
        frame_gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30),
    )

    if not isinstance(faces_raw, np.ndarray) or len(faces_raw) == 0:
        return []

    faces = []
    for (x, y, fw, fh) in faces_raw:
        cx = (x + fw / 2) / w
        cy = (y + fh / 2) / h
        faces.append(FacePosition(cx=cx, cy=cy))

    return faces


def detect_faces(frame_bgr, use_mediapipe: bool = True) -> list[FacePosition]:
    """
    Detect faces in a BGR frame.

    Args:
        frame_bgr: OpenCV BGR frame (numpy ndarray)
        use_mediapipe: Use MediaPipe (better); falls back to OpenCV Haar if False
                       or if MediaPipe is not installed / solutions API missing.

    Returns:
        List of FacePosition (may be empty if no face found).
    """
    import cv2

    if use_mediapipe and _is_mediapipe_available():
        try:
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            return _detect_faces_mediapipe(frame_rgb)
        except (AttributeError, Exception):
            # MediaPipe solutions API unavailable (e.g. mediapipe >=0.10.14)
            # or any runtime failure — silently fall through to OpenCV
            pass

    # Fallback: OpenCV Haar cascade
    frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return _detect_faces_opencv(frame_gray)


def dominant_face(faces: list[FacePosition]) -> Optional[FacePosition]:
    """Return the highest-confidence face from a detection list."""
    if not faces:
        return None
    return max(faces, key=lambda f: f.confidence)


# ─── Trajectory Builder ───────────────────────────────────────────────────────


def build_crop_trajectory(
    video_path: Path,
    start_time: float,
    duration: float,
    target_width: int = 1080,
    target_height: int = 1920,
    sample_every_n_frames: int = 15,
    ema_alpha: float = 0.04,
    use_mediapipe: bool = True,
    deadzone_fraction: float = 0.04,
) -> CropTrajectory:
    """
    Analyze a video segment and compute a smoothed face-following crop trajectory.

    To reduce jitter:
    - Lower ema_alpha (e.g. 0.02) = more inertia, smoother but slower to follow
    - Higher sample_every_n_frames = fewer EMA target changes per second
    - Higher deadzone_fraction = larger movement required before crop reacts

    Args:
        video_path: Source video file
        start_time: Clip start time in seconds
        duration: Clip duration in seconds
        target_width: Output crop width (pixels)
        target_height: Output crop height (pixels)
        sample_every_n_frames: Face detection every N frames (performance tradeoff)
        ema_alpha: EMA smoothing factor (smaller = smoother, 0.02–0.06 recommended)
        use_mediapipe: Use MediaPipe for detection (falls back to OpenCV Haar)
        deadzone_fraction: Fraction of frame size; face must move more than this to
                           update the EMA target. Prevents micro-jitter from detection
                           noise. 0.04 = 4% of frame width/height.

    Returns:
        CropTrajectory with one (cx, cy) pixel coordinate per frame
    """
    import cv2
    cap = cv2.VideoCapture(str(video_path))

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Seek to start_time
    cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)

    total_frames = int(duration * fps)

    # Compute minimum crop dimensions to achieve target ratio
    tgt_ratio = target_width / target_height
    src_ratio = src_width / src_height

    if src_ratio > tgt_ratio:
        crop_h = src_height
        crop_w = int(crop_h * tgt_ratio)
    else:
        crop_w = src_width
        crop_h = int(crop_w / tgt_ratio)

    # Half-sizes for boundary clamping
    half_w = crop_w / 2
    half_h = crop_h / 2

    # Deadzone in absolute pixels
    deadzone_px_w = src_width * deadzone_fraction
    deadzone_px_h = src_height * deadzone_fraction

    # Default center = video center
    smooth_cx = src_width / 2.0
    smooth_cy = src_height / 2.0

    centers: list[tuple[float, float]] = []
    last_known_face: Optional[FacePosition] = None
    # Stable EMA target (only updated when face moves beyond deadzone)
    ema_target_cx: float = src_width / 2.0
    ema_target_cy: float = src_height / 2.0

    for frame_idx in range(total_frames):
        ret, frame = cap.read()
        if not ret:
            break

        # Run face detection only on sampled frames
        if frame_idx % sample_every_n_frames == 0:
            faces = detect_faces(frame, use_mediapipe=use_mediapipe)
            face = dominant_face(faces)
            if face:
                new_cx = face.cx * src_width
                new_cy = face.cy * src_height

                # Only update EMA target if face moved beyond deadzone
                # This prevents micro-jitter from detection noise
                if last_known_face is None:
                    ema_target_cx = new_cx
                    ema_target_cy = new_cy
                    last_known_face = face
                else:
                    prev_cx = last_known_face.cx * src_width
                    prev_cy = last_known_face.cy * src_height
                    moved_x = abs(new_cx - prev_cx)
                    moved_y = abs(new_cy - prev_cy)

                    if moved_x > deadzone_px_w or moved_y > deadzone_px_h:
                        # Significant movement — update EMA target
                        # Bias: nudge crop up slightly for better headroom above face
                        ema_target_cx = new_cx
                        ema_target_cy = new_cy - crop_h * 0.08
                        last_known_face = face
                    # else: within deadzone — keep ema_target unchanged

        # Apply EMA toward the stable EMA target
        smooth_cx = ema_alpha * ema_target_cx + (1 - ema_alpha) * smooth_cx
        smooth_cy = ema_alpha * ema_target_cy + (1 - ema_alpha) * smooth_cy

        # Clamp so crop stays within source frame
        clamped_cx = max(half_w, min(src_width - half_w, smooth_cx))
        clamped_cy = max(half_h, min(src_height - half_h, smooth_cy))

        centers.append((clamped_cx, clamped_cy))

    cap.release()

    return CropTrajectory(
        centers=centers,
        fps=fps,
        src_width=src_width,
        src_height=src_height,
    )


# ─── Video Exporter ───────────────────────────────────────────────────────────


def apply_face_crop(
    video_path: Path,
    output_path: Path,
    trajectory: CropTrajectory,
    start_time: float,
    duration: float,
    target_width: int = 1080,
    target_height: int = 1920,
    subtitle_path: Optional[Path] = None,
    output_config=None,
) -> Path:
    """
    Apply a face-tracked crop trajectory to a video segment and write output.

    Strategy:
        1. Read frames with OpenCV, apply per-frame crop + resize
        2. Write cropped frames to a temp video (no audio)
        3. Use FFmpeg to mux audio from the original and burn subtitles

    Args:
        video_path: Source video file
        output_path: Final output MP4 path
        trajectory: Pre-computed CropTrajectory
        start_time: Clip start in seconds
        duration: Clip duration in seconds
        target_width: Output width
        target_height: Output height
        subtitle_path: Optional ASS subtitle file to burn in
        output_config: OutputConfig (for codec/crf settings)

    Returns:
        Path to final output file
    """
    import cv2
    from autoclip.utils.ffmpeg import run_ffmpeg

    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)

    fps = trajectory.fps
    src_width = trajectory.src_width
    src_height = trajectory.src_height

    tgt_ratio = target_width / target_height
    src_ratio = src_width / src_height

    if src_ratio > tgt_ratio:
        crop_h = src_height
        crop_w = int(crop_h * tgt_ratio)
    else:
        crop_w = src_width
        crop_h = int(crop_w / tgt_ratio)

    half_w = crop_w // 2
    half_h = crop_h // 2

    # Write cropped frames to a temp file
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_f:
        tmp_path = Path(tmp_f.name)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_path), fourcc, fps, (target_width, target_height))

    for frame_idx, (cx, cy) in enumerate(trajectory.centers):
        ret, frame = cap.read()
        if not ret:
            break

        # Compute crop coordinates
        x1 = int(cx - half_w)
        y1 = int(cy - half_h)
        x2 = x1 + crop_w
        y2 = y1 + crop_h

        # Clamp to source bounds
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(src_width, x2)
        y2 = min(src_height, y2)

        cropped = frame[y1:y2, x1:x2]

        # Pad if crop is smaller than expected (boundary case)
        pad_w = crop_w - (x2 - x1)
        pad_h = crop_h - (y2 - y1)
        if pad_w > 0 or pad_h > 0:
            cropped = cv2.copyMakeBorder(
                cropped, 0, pad_h, 0, pad_w,
                cv2.BORDER_CONSTANT, value=(0, 0, 0),
            )

        # Resize to target dimensions
        resized = cv2.resize(cropped, (target_width, target_height),
                             interpolation=cv2.INTER_LANCZOS4)
        writer.write(resized)

    writer.release()
    cap.release()

    # ── FFmpeg: mux audio + subtitle ─────────────────────────────────────────
    crf = getattr(output_config, "crf", 23) if output_config else 23
    video_codec = getattr(output_config, "video_codec", "libx264") if output_config else "libx264"
    audio_codec = getattr(output_config, "audio_codec", "aac") if output_config else "aac"
    audio_bitrate = getattr(output_config, "audio_bitrate", "128k") if output_config else "128k"

    ffmpeg_args = [
        "-i", str(tmp_path),              # Cropped video (no audio)
        "-ss", str(start_time),
        "-i", str(video_path),            # Original (for audio)
        "-t", str(duration),
        "-map", "0:v:0",                  # Video from cropped temp
        "-map", "1:a:0",                  # Audio from original
    ]

    if subtitle_path and subtitle_path.exists():
        sub_str = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
        ffmpeg_args += ["-vf", f"ass='{sub_str}'"]

    ffmpeg_args += [
        "-c:v", video_codec,
        "-crf", str(crf),
        "-preset", "fast",
        "-c:a", audio_codec,
        "-b:a", audio_bitrate,
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    try:
        run_ffmpeg(ffmpeg_args, duration=duration)
    finally:
        tmp_path.unlink(missing_ok=True)

    return output_path


# ─── High-level entry point ───────────────────────────────────────────────────


def smart_crop_clip(
    video_path: Path,
    output_path: Path,
    start_time: float,
    duration: float,
    target_width: int = 1080,
    target_height: int = 1920,
    subtitle_path: Optional[Path] = None,
    output_config=None,
    ema_alpha: float = 0.04,
    sample_every_n_frames: int = 15,
    use_mediapipe: bool = True,
    deadzone_fraction: float = 0.04,
) -> Path:
    """
    Full face-tracking smart crop pipeline for a single clip.

    1. Builds a smoothed face trajectory from sampled frames
    2. Applies per-frame crop using the trajectory
    3. Muxes audio and burns subtitles via FFmpeg

    Args:
        video_path: Source video
        output_path: Output file path
        start_time: Clip start (seconds)
        duration: Clip duration (seconds)
        target_width: Output width (default 1080)
        target_height: Output height (default 1920)
        subtitle_path: Optional ASS subtitle to burn in
        output_config: OutputConfig for codec settings
        ema_alpha: Smoothing factor (0.02=very stable, 0.08=more responsive)
        sample_every_n_frames: Face detection interval (higher=smoother, less accurate)
        use_mediapipe: Prefer MediaPipe over OpenCV Haar
        deadzone_fraction: Min face movement (fraction of frame) to trigger crop update

    Returns:
        Path to output file
    """
    trajectory = build_crop_trajectory(
        video_path=video_path,
        start_time=start_time,
        duration=duration,
        target_width=target_width,
        target_height=target_height,
        sample_every_n_frames=sample_every_n_frames,
        ema_alpha=ema_alpha,
        use_mediapipe=use_mediapipe,
        deadzone_fraction=deadzone_fraction,
    )

    return apply_face_crop(
        video_path=video_path,
        output_path=output_path,
        trajectory=trajectory,
        start_time=start_time,
        duration=duration,
        target_width=target_width,
        target_height=target_height,
        subtitle_path=subtitle_path,
        output_config=output_config,
    )
