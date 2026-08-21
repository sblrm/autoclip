from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def test_preview_and_export_share_one_saved_face_trajectory(tmp_path: Path) -> None:
    pytest.importorskip("cv2")
    from autoclip.utils.ffmpeg import EncoderCapability
    from autoclip.web.acceleration import AccelerationStatus
    from autoclip.web.full_store import FullStudioStore
    from autoclip.web.rendering import TrackingService
    from autoclip.web.tracking import FaceObservation

    fixture = Path(__file__).parent / "fixtures" / "two_people_pixabay.mp4"
    store = FullStudioStore(tmp_path / "projects")
    project = store.create_from_upload(fixture, original_name="two_people.mp4")
    clip = store.create_clip(project.id, start_time=0, end_time=1.5, title="Two people", score=90, language="en")
    store.set_project_acceleration(
        project.id,
        tracker_engine="yunet_cuda",
        encoder_mode="h264_nvenc",
    )

    class FakeDetector:
        engine = "yunet_cuda"
        provider = "CUDAExecutionProvider"
        model_id = "yunet_2023mar"

        def __enter__(self) -> "FakeDetector":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def detect(self, _frame: object, _timestamp_ms: int) -> list[FaceObservation]:
            return [
                FaceObservation(0.25, 0.5, 0.95),
                FaceObservation(0.75, 0.5, 0.90),
            ]

    class FakeDetectorFactory:
        def __init__(self) -> None:
            self.resolutions: list[object] = []

        def create(self, resolution: object) -> FakeDetector:
            self.resolutions.append(resolution)
            return FakeDetector()

    class FakeAccelerationManager:
        def status(self) -> AccelerationStatus:
            return AccelerationStatus.for_test(
                platform="Windows",
                engines={
                    "yunet_cuda": (
                        "ready",
                        "CUDAExecutionProvider",
                        "yunet_2023mar",
                    ),
                },
                encoders={"h264_nvenc": "ready"},
            )

    crop_calls: list[dict[str, Any]] = []

    def fake_cropper(**kwargs: Any) -> Path:
        crop_calls.append(kwargs)
        output = Path(kwargs["output_path"])
        output.write_bytes(b"mock mp4")
        return output

    detector_factory = FakeDetectorFactory()
    service = TrackingService(
        store,
        acceleration_manager=FakeAccelerationManager(),
        detector_factory=detector_factory,
        encoder_capabilities=lambda: {"h264_nvenc": EncoderCapability.ready()},
        cropper=fake_cropper,
    )

    tracks = service.detect_tracks(clip.id, lambda *_: None)
    assert tracks
    detected_resolution = store.get_clip_tracking_resolution(clip.id)
    assert detected_resolution is not None
    assert detected_resolution.trajectory_artifact_id is None
    assert len(detector_factory.resolutions) == 1
    store.select_face_track(clip.id, tracks[0].id)
    preview = service.render_preview(clip.id, lambda *_: None)
    assert preview is not None
    store.approve_clip(clip.id)
    exported = service.export_approved(clip.id, lambda *_: None)

    trajectory_artifacts = [item for item in store.list_artifacts(project.id) if item.kind == "tracking_trajectory"]
    trajectory = json.loads(Path(trajectory_artifacts[-1].path).read_text(encoding="utf-8"))
    saved_resolution = store.get_clip_tracking_resolution(clip.id)
    assert saved_resolution is not None
    assert saved_resolution.trajectory_artifact_id == trajectory_artifacts[-1].id
    assert trajectory["selected_face_track_id"] == tracks[0].id
    assert trajectory["tracker_engine"] == "yunet_cuda"
    assert trajectory["provider"] == "CUDAExecutionProvider"
    assert trajectory["model_id"] == "yunet_2023mar"
    assert len(trajectory["centers"]) > 0
    assert len(crop_calls) == 2
    assert crop_calls[0]["trajectory"].centers == crop_calls[1]["trajectory"].centers
    assert (crop_calls[0]["target_width"], crop_calls[1]["target_width"]) == (360, 1080)
    assert preview.metadata == {
        "encoder_mode": "h264_nvenc",
        "encoder": "h264_nvenc",
        "tracker_engine": "yunet_cuda",
        "provider": "CUDAExecutionProvider",
        "model_id": "yunet_2023mar",
        "trajectory_artifact_id": trajectory_artifacts[-1].id,
    }
    assert exported.metadata == preview.metadata


def test_preview_rejects_missing_saved_resolution_without_center_crop(tmp_path: Path) -> None:
    from autoclip.web.acceleration import TrackerUnavailable
    from autoclip.web.full_store import FullStudioStore
    from autoclip.web.rendering import TrackingService

    fixture = Path(__file__).parent / "fixtures" / "two_people_pixabay.mp4"
    store = FullStudioStore(tmp_path / "projects")
    project = store.create_from_upload(fixture, original_name="two_people.mp4")
    clip = store.create_clip(
        project.id,
        start_time=0,
        end_time=1.5,
        title="Two people",
        score=90,
        language="en",
    )
    track = store.save_face_track(
        clip.id,
        label="Subject 1",
        confidence=0.9,
        samples=[{"cx": 0.25, "cy": 0.5, "confidence": 0.9}],
    )
    store.select_face_track(clip.id, track.id)
    crop_calls: list[dict[str, Any]] = []
    service = TrackingService(store, cropper=lambda **kwargs: crop_calls.append(kwargs))

    with pytest.raises(TrackerUnavailable, match="tracker_error"):
        service.render_preview(clip.id, lambda *_: None)

    assert crop_calls == []


def test_preview_without_detection_run_fails_before_constructing_detector(tmp_path: Path) -> None:
    from autoclip.web.acceleration import AccelerationStatus, TrackerUnavailable
    from autoclip.web.full_store import FullStudioStore
    from autoclip.web.rendering import TrackingService

    fixture = Path(__file__).parent / "fixtures" / "two_people_pixabay.mp4"
    store = FullStudioStore(tmp_path / "projects")
    project = store.create_from_upload(fixture, original_name="two_people.mp4")
    clip = store.create_clip(
        project.id,
        start_time=0,
        end_time=1.5,
        title="Two people",
        score=90,
        language="en",
    )

    class FakeAccelerationManager:
        def status(self) -> AccelerationStatus:
            return AccelerationStatus.for_test(
                engines={"mediapipe_cpu": ("ready", "CPUDelegate")},
            )

    class DetectorSentinel:
        def __init__(self) -> None:
            self.create_calls = 0

        def create(self, _resolution: object) -> object:
            self.create_calls += 1
            raise AssertionError("preview must not construct a detector")

    detector = DetectorSentinel()
    before_clip = store.get_clip(clip.id)
    service = TrackingService(
        store,
        acceleration_manager=FakeAccelerationManager(),
        detector_factory=detector,
    )

    with pytest.raises(TrackerUnavailable, match="tracker_error") as caught:
        service.render_preview(clip.id, lambda *_: None)

    assert caught.value.error_code == "tracker_error"
    assert detector.create_calls == 0
    assert store.get_clip(clip.id) == before_clip
    assert store.list_face_tracks(clip.id) == []
    assert store.get_clip_tracking_resolution(clip.id) is None
    assert store.list_artifacts(project.id) == []
