"""Explicit MediaPipe Tasks tracking primitives for studio previews."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FaceObservation:
    """A normalized face-center observation from one sampled video frame."""

    cx: float
    cy: float
    confidence: float


@dataclass
class FaceTrack:
    """One stable face candidate across sampled frames."""

    id: str
    samples: list[FaceObservation | None] = field(default_factory=list)


@dataclass(frozen=True)
class TrackerCapability:
    available: bool
    engine: str
    reason: str


class FaceTrackingUnavailable(RuntimeError):
    """Raised when tracking was requested but no supported detector is ready."""


def build_face_tracks(
    sampled_observations: list[list[FaceObservation]],
    maximum_distance: float = 0.18,
) -> list[FaceTrack]:
    """Associate faces by spatial continuity, never by confidence ranking alone."""
    tracks: list[FaceTrack] = []
    for sample_index, observations in enumerate(sampled_observations):
        for track in tracks:
            track.samples.append(None)

        remaining = list(observations)
        for track in tracks:
            previous = _last_observation(track, sample_index)
            if previous is None or not remaining:
                continue
            candidate = min(remaining, key=lambda face: _distance(previous, face))
            if _distance(previous, candidate) <= maximum_distance:
                track.samples[-1] = candidate
                remaining.remove(candidate)

        for observation in remaining:
            tracks.append(
                FaceTrack(
                    id=f"track_{len(tracks) + 1}",
                    samples=[None] * sample_index + [observation],
                )
            )

    return tracks


def build_crop_targets(
    track: FaceTrack,
    *,
    hold_samples: int = 1,
    ease_samples: int = 3,
) -> list[FaceObservation]:
    """Turn a selected track into targets that visibly recover lost subjects."""
    targets: list[FaceObservation] = []
    last_visible = FaceObservation(cx=0.5, cy=0.5, confidence=0.0)
    missing = 0
    for sample in track.samples:
        if sample is not None:
            last_visible = sample
            missing = 0
            targets.append(sample)
            continue

        missing += 1
        if missing <= hold_samples:
            targets.append(last_visible)
            continue
        progress = min(1.0, (missing - hold_samples) / max(1, ease_samples))
        targets.append(
            FaceObservation(
                cx=_lerp(last_visible.cx, 0.5, progress),
                cy=_lerp(last_visible.cy, 0.5, progress),
                confidence=0.0,
            )
        )
    return targets


def default_model_path() -> Path:
    """Return the bundled MediaPipe Tasks detector asset location."""
    return Path(__file__).with_name("assets") / "face_detector.task"


def get_tracker_capability(model_path: Path | None = None) -> TrackerCapability:
    """Report readiness; callers must show this rather than applying a fallback."""
    resolved_model = model_path or default_model_path()
    if not resolved_model.is_file():
        return TrackerCapability(False, "mediapipe_tasks", "Face detector model file is unavailable")
    try:
        import mediapipe as mp
    except ImportError:
        return TrackerCapability(False, "mediapipe_tasks", "MediaPipe is not installed")
    if not hasattr(mp, "tasks") or not hasattr(mp.tasks, "vision"):
        return TrackerCapability(False, "mediapipe_tasks", "MediaPipe Tasks API is unavailable")
    return TrackerCapability(True, "mediapipe_tasks", "Face detector ready")


class MediaPipeTasksDetector:
    """Keep one supported detector alive for one ordered video pass."""

    def __init__(
        self,
        model_path: Path | None = None,
        min_confidence: float = 0.5,
        *,
        delegate: Any | None = None,
        engine: str = "mediapipe_cpu",
        provider: str = "CPUDelegate",
        model_id: str | None = None,
    ) -> None:
        self.model_path = model_path or default_model_path()
        self.min_confidence = min_confidence
        self.delegate = delegate
        self.engine = engine
        self.provider = provider
        self.model_id = model_id
        capability = get_tracker_capability(self.model_path)
        if not capability.available:
            raise FaceTrackingUnavailable(capability.reason)
        self._detector: Any | None = None
        self._mp: Any | None = None

    def __enter__(self) -> "MediaPipeTasksDetector":
        import mediapipe as mp

        options = mp.tasks.vision.FaceDetectorOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(self.model_path),
                delegate=self.delegate,
            ),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            min_detection_confidence=self.min_confidence,
        )
        self._mp = mp
        self._detector = mp.tasks.vision.FaceDetector.create_from_options(options)
        return self

    def __exit__(self, *_: object) -> None:
        if self._detector is not None:
            self._detector.close()
        self._detector = None

    def detect(self, frame_bgr: Any, timestamp_ms: int) -> list[FaceObservation]:
        """Detect every face in a monotonically timestamped video frame."""
        if self._detector is None or self._mp is None:
            raise RuntimeError("Detector must be entered before use")
        import cv2

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect_for_video(image, timestamp_ms)
        height, width = frame_bgr.shape[:2]
        observations: list[FaceObservation] = []
        for detection in result.detections:
            box = detection.bounding_box
            categories = detection.categories
            confidence = float(categories[0].score) if categories else 1.0
            observations.append(
                FaceObservation(
                    cx=(box.origin_x + box.width / 2) / width,
                    cy=(box.origin_y + box.height / 2) / height,
                    confidence=confidence,
                )
            )
        return observations


def _last_observation(track: FaceTrack, sample_index: int) -> FaceObservation | None:
    for sample in reversed(track.samples[:sample_index]):
        if sample is not None:
            return sample
    return None


def _distance(left: FaceObservation, right: FaceObservation) -> float:
    return math.hypot(left.cx - right.cx, left.cy - right.cy)


def _lerp(start: float, end: float, amount: float) -> float:
    return start + (end - start) * amount
