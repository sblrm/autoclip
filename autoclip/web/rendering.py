"""Saved, subject-locked MediaPipe Tasks trajectories for web studio renders."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from autoclip.core.tracker import CropTrajectory, apply_face_crop
from autoclip.web.full_store import FullStudioStore
from autoclip.web.runtime_store import Artifact, FaceTrackRecord
from autoclip.web.tracking import (
    FaceObservation,
    FaceTrack,
    MediaPipeTasksDetector,
    build_crop_targets,
    build_face_tracks,
)

ProgressReporter = Callable[[str, float, str], None]
DetectorFactory = Callable[[], AbstractContextManager[Any]]
Cropper = Callable[..., Path]


def build_saved_trajectory(
    track: FaceTrackRecord,
    *,
    fps: float,
    src_width: int,
    src_height: int,
    total_frames: int,
    sample_every_n_frames: int,
    hold_samples: int = 1,
    ease_samples: int = 3,
) -> tuple[CropTrajectory, list[tuple[int, int]]]:
    """Create a clamped per-frame crop from one persisted, locked subject."""
    selected = FaceTrack(
        id=track.id,
        samples=[_observation_from_sample(sample) for sample in track.samples],
    )
    targets = build_crop_targets(selected, hold_samples=hold_samples, ease_samples=ease_samples)
    centers: list[tuple[float, float]] = []
    for frame_index in range(total_frames):
        sample_index = min(len(targets) - 1, frame_index // max(1, sample_every_n_frames))
        target = targets[sample_index] if targets else FaceObservation(0.5, 0.5, 0.0)
        centers.append(_clamp_crop_center(target, src_width, src_height))
    return (
        CropTrajectory(centers=centers, fps=fps, src_width=src_width, src_height=src_height),
        _gap_ranges(selected.samples),
    )


class TrackingService:
    """Detect once, let the editor lock a subject, then reuse its saved path."""

    def __init__(
        self,
        store: FullStudioStore,
        *,
        detector_factory: DetectorFactory = MediaPipeTasksDetector,
        cropper: Cropper = apply_face_crop,
        sample_every_n_frames: int = 8,
        hold_samples: int = 1,
        ease_samples: int = 3,
    ) -> None:
        self.store = store
        self._detector_factory = detector_factory
        self._cropper = cropper
        self.sample_every_n_frames = sample_every_n_frames
        self.hold_samples = hold_samples
        self.ease_samples = ease_samples

    def detect_tracks(self, clip_id: str, report: ProgressReporter) -> list[FaceTrackRecord]:
        """Run exactly one VIDEO-mode detector through a clip and save candidates."""
        import cv2

        clip = self.store.get_clip(clip_id)
        source_path = self._source_path(clip.project_id)
        capture = cv2.VideoCapture(str(source_path))
        if not capture.isOpened():
            raise FileNotFoundError("Project source video cannot be opened")
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        capture.set(cv2.CAP_PROP_POS_MSEC, clip.start_time * 1000)
        total_frames = max(1, int((clip.end_time - clip.start_time) * fps) + 1)
        sampled: list[list[FaceObservation]] = []
        last_timestamp = -1
        report("detecting_faces", 0.12, "Detecting stable subject candidates")
        try:
            with self._detector_factory() as detector:
                for frame_index in range(total_frames):
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if frame_index % self.sample_every_n_frames != 0:
                        continue
                    timestamp_ms = max(last_timestamp + 1, int((clip.start_time + frame_index / fps) * 1000))
                    sampled.append(detector.detect(frame, timestamp_ms))
                    last_timestamp = timestamp_ms
                    report(
                        "detecting_faces",
                        min(0.75, 0.12 + 0.63 * (frame_index + 1) / total_frames),
                        "Following face candidates without automatic subject switching",
                    )
        finally:
            capture.release()

        tracks = build_face_tracks(sampled)
        self.store.clear_tracking_data(clip_id)
        records: list[FaceTrackRecord] = []
        for index, track in enumerate(tracks, start=1):
            record = self.store.save_face_track(
                clip_id,
                label=f"Subject {index}",
                confidence=_mean_confidence(track.samples),
                samples=[_sample_from_observation(sample) for sample in track.samples],
            )
            records.append(record)
            for start_sample, end_sample in _gap_ranges(track.samples):
                self.store.save_tracking_gap(clip_id, start_sample, end_sample)

        tracking_status = "needs_subject" if records else "no_faces"
        self.store.update_clip(clip_id, tracking_status=tracking_status)
        message = "Select a subject to render the preview" if records else "No face candidate detected; center crop was not used"
        report(tracking_status, 0.95, message)
        return records

    def render_preview(self, clip_id: str, report: ProgressReporter) -> Artifact | None:
        """Detect candidates first; render only after the editor locks one subject."""
        clip = self.store.get_clip(clip_id)
        if not self.store.list_face_tracks(clip_id):
            self.detect_tracks(clip_id, report)
            return None
        if not clip.selected_face_track_id:
            self.store.update_clip(clip_id, tracking_status="needs_subject")
            report("needs_subject", 0.95, "Select a detected face before rendering preview")
            return None
        report("building_trajectory", 0.15, "Building saved crop trajectory for locked subject")
        trajectory_path = self._write_trajectory(clip_id)
        report("rendering_preview", 0.45, "Rendering 9:16 tracking preview")
        artifact = self._render(clip_id, trajectory_path, kind="tracking_preview", width=360, height=640)
        self.store.update_clip(clip_id, tracking_status="preview_ready")
        self.store.mark_preview_ready(clip_id)
        report("preview_ready", 0.95, "Preview ready for approval")
        return artifact

    def export_approved(self, clip_id: str, report: ProgressReporter) -> Artifact:
        """Export the already-approved preview using the exact saved trajectory."""
        clip = self.store.get_clip(clip_id)
        if clip.status != "approved":
            raise ValueError("Approve the tracking preview before exporting")
        trajectory_path = self._find_saved_trajectory(clip_id, clip.selected_face_track_id)
        report("exporting", 0.3, "Rendering approved 1080×1920 export")
        artifact = self._render(clip_id, trajectory_path, kind="export", width=1080, height=1920)
        self.store.update_clip(clip_id, tracking_status="exported")
        self.store.set_clip_status(clip_id, "exported")
        self.store.set_project_status(clip.project_id, "completed")
        report("completed", 0.95, "Approved vertical MP4 export is ready")
        return artifact

    def _write_trajectory(self, clip_id: str) -> Path:
        import cv2

        clip = self.store.get_clip(clip_id)
        if not clip.selected_face_track_id:
            raise ValueError("A selected face track is required")
        track = next(
            (item for item in self.store.list_face_tracks(clip_id) if item.id == clip.selected_face_track_id),
            None,
        )
        if track is None:
            raise ValueError("Selected face track does not belong to this clip")
        capture = cv2.VideoCapture(str(self._source_path(clip.project_id)))
        if not capture.isOpened():
            raise FileNotFoundError("Project source video cannot be opened")
        try:
            fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        finally:
            capture.release()
        total_frames = max(1, int((clip.end_time - clip.start_time) * fps) + 1)
        trajectory, gaps = build_saved_trajectory(
            track,
            fps=fps,
            src_width=width,
            src_height=height,
            total_frames=total_frames,
            sample_every_n_frames=self.sample_every_n_frames,
            hold_samples=self.hold_samples,
            ease_samples=self.ease_samples,
        )
        destination = self._project_root(clip.project_id) / "artifacts" / f"{clip.id}-trajectory.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "selected_face_track_id": track.id,
            "start_time": clip.start_time,
            "duration": clip.end_time - clip.start_time,
            "fps": trajectory.fps,
            "src_width": trajectory.src_width,
            "src_height": trajectory.src_height,
            "centers": trajectory.centers,
            "gaps": gaps,
        }
        destination.write_text(json.dumps(payload), encoding="utf-8")
        self.store.save_artifact(clip.project_id, "tracking_trajectory", destination, clip_id=clip.id)
        return destination

    def _render(self, clip_id: str, trajectory_path: Path, *, kind: str, width: int, height: int) -> Artifact:
        clip = self.store.get_clip(clip_id)
        payload = json.loads(trajectory_path.read_text(encoding="utf-8"))
        trajectory = CropTrajectory(
            centers=[tuple(center) for center in payload["centers"]],
            fps=float(payload["fps"]),
            src_width=int(payload["src_width"]),
            src_height=int(payload["src_height"]),
        )
        filename = f"{clip.id}-preview.mp4" if kind == "tracking_preview" else f"{clip.id}-export.mp4"
        output_path = self._project_root(clip.project_id) / "artifacts" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._cropper(
            video_path=self._source_path(clip.project_id),
            output_path=output_path,
            trajectory=trajectory,
            start_time=float(payload["start_time"]),
            duration=float(payload["duration"]),
            target_width=width,
            target_height=height,
        )
        return self.store.save_artifact(clip.project_id, kind, output_path, clip_id=clip.id)

    def _find_saved_trajectory(self, clip_id: str, selected_track_id: str | None) -> Path:
        clip = self.store.get_clip(clip_id)
        for artifact in reversed(self.store.list_artifacts(clip.project_id)):
            if artifact.clip_id != clip_id or artifact.kind != "tracking_trajectory":
                continue
            path = Path(artifact.path)
            if not path.is_file():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("selected_face_track_id") == selected_track_id:
                return path
        raise ValueError("No saved preview trajectory exists for the selected face")

    def _source_path(self, project_id: str) -> Path:
        project = self.store.get_project(project_id)
        source = Path(project.source_path)
        if source.is_file():
            return source
        candidates = sorted((self._project_root(project_id) / "source").glob("*"), key=lambda path: path.stat().st_mtime)
        if candidates:
            return candidates[-1]
        raise FileNotFoundError("Project source video is unavailable; analyze the URL import first")

    def _project_root(self, project_id: str) -> Path:
        return self.store.root / project_id


def _observation_from_sample(sample: dict[str, float] | None) -> FaceObservation | None:
    if sample is None:
        return None
    return FaceObservation(float(sample["cx"]), float(sample["cy"]), float(sample.get("confidence", 0.0)))


def _sample_from_observation(sample: FaceObservation | None) -> dict[str, float] | None:
    if sample is None:
        return None
    return {"cx": sample.cx, "cy": sample.cy, "confidence": sample.confidence}


def _gap_ranges(samples: list[FaceObservation | None]) -> list[tuple[int, int]]:
    gaps: list[tuple[int, int]] = []
    start: int | None = None
    for index, sample in enumerate(samples):
        if sample is None and start is None:
            start = index
        elif sample is not None and start is not None:
            gaps.append((start, index - 1))
            start = None
    if start is not None:
        gaps.append((start, len(samples) - 1))
    return gaps


def _mean_confidence(samples: list[FaceObservation | None]) -> float:
    visible = [sample.confidence for sample in samples if sample is not None]
    return sum(visible) / len(visible) if visible else 0.0


def _clamp_crop_center(observation: FaceObservation, width: int, height: int) -> tuple[float, float]:
    target_ratio = 9 / 16
    source_ratio = width / height
    if source_ratio > target_ratio:
        crop_width = int(height * target_ratio)
        crop_height = height
    else:
        crop_width = width
        crop_height = int(width / target_ratio)
    half_width = crop_width / 2
    half_height = crop_height / 2
    center_x = max(half_width, min(width - half_width, observation.cx * width))
    center_y = max(half_height, min(height - half_height, observation.cy * height))
    return center_x, center_y
