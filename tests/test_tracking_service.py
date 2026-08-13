from __future__ import annotations

from pathlib import Path

import pytest


def test_saved_trajectory_holds_then_eases_to_center_without_leaving_crop_bounds() -> None:
    from autoclip.web.rendering import build_saved_trajectory
    from autoclip.web.runtime_store import FaceTrackRecord

    track = FaceTrackRecord(
        id="speaker-left",
        clip_id="clip-1",
        label="Subject 1",
        confidence=0.9,
        samples=[
            {"cx": 0.2, "cy": 0.4, "confidence": 0.9},
            None,
            None,
        ],
    )

    trajectory, gaps = build_saved_trajectory(
        track,
        fps=2,
        src_width=1920,
        src_height=1080,
        total_frames=6,
        sample_every_n_frames=2,
        hold_samples=1,
        ease_samples=2,
    )

    assert len(trajectory.centers) == 6
    assert trajectory.centers[0][0] == pytest.approx(384)
    assert trajectory.centers[3][0] == pytest.approx(384)
    assert 384 < trajectory.centers[4][0] < 960
    assert gaps == [(1, 2)]

    crop_width = int(1080 * (1080 / 1920))
    for center_x, center_y in trajectory.centers:
        assert crop_width / 2 <= center_x <= 1920 - crop_width / 2
        assert 540 <= center_y <= 540


def test_tracking_service_persists_subject_candidates_and_gaps(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    from autoclip.web.full_store import FullStudioStore
    from autoclip.web.rendering import TrackingService
    from autoclip.web.tracking import FaceObservation

    source = tmp_path / "source.mp4"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 4, (160, 90))
    for _ in range(8):
        writer.write(np.zeros((90, 160, 3), dtype=np.uint8))
    writer.release()

    store = FullStudioStore(tmp_path / "library")
    project = store.create_from_upload(source, original_name="source.mp4")
    clip = store.create_clip(
        project.id,
        start_time=0,
        end_time=1.5,
        title="Candidate",
        score=88,
        language="id",
    )
    observations = iter(
        [
            [FaceObservation(0.2, 0.5, 0.8), FaceObservation(0.8, 0.5, 0.99)],
            [FaceObservation(0.21, 0.5, 0.8), FaceObservation(0.79, 0.5, 0.99)],
            [FaceObservation(0.78, 0.5, 0.99)],
            [FaceObservation(0.77, 0.5, 0.99)],
        ]
    )

    class FakeDetector:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def detect(self, _frame: object, _timestamp_ms: int):
            return next(observations)

    service = TrackingService(
        store,
        detector_factory=lambda: FakeDetector(),
        sample_every_n_frames=2,
    )
    tracks = service.detect_tracks(clip.id, lambda *_: None)

    assert len(tracks) == 2
    assert tracks[0].samples[-2:] == [None, None]
    assert store.list_tracking_gaps(clip.id)[0].start_sample == 2
    assert store.get_clip(clip.id).tracking_status == "needs_subject"
