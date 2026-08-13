from __future__ import annotations


def test_selected_face_track_never_switches_to_a_higher_confidence_person() -> None:
    from autoclip.web.tracking import FaceObservation, build_face_tracks

    tracks = build_face_tracks(
        [
            [FaceObservation(cx=0.20, cy=0.50, confidence=0.60), FaceObservation(cx=0.80, cy=0.50, confidence=0.95)],
            [FaceObservation(cx=0.79, cy=0.50, confidence=0.99), FaceObservation(cx=0.21, cy=0.50, confidence=0.70)],
            [FaceObservation(cx=0.78, cy=0.50, confidence=0.99)],
        ]
    )

    selected = min(tracks, key=lambda track: track.samples[0].cx)
    assert [sample.cx if sample else None for sample in selected.samples] == [0.20, 0.21, None]


def test_lost_subject_holds_then_eases_toward_center() -> None:
    from autoclip.web.tracking import FaceObservation, FaceTrack, build_crop_targets

    track = FaceTrack(
        id="left",
        samples=[FaceObservation(cx=0.20, cy=0.50, confidence=0.9), None, None, None],
    )

    targets = build_crop_targets(track, hold_samples=1, ease_samples=2)

    assert targets[0].cx == 0.20
    assert targets[1].cx == 0.20
    assert 0.20 < targets[2].cx < 0.50
    assert targets[3].cx == 0.50


def test_missing_tasks_model_reports_unavailable_instead_of_using_a_fallback(tmp_path) -> None:
    from autoclip.web.tracking import get_tracker_capability

    capability = get_tracker_capability(tmp_path / "missing.task")

    assert capability.available is False
    assert "model" in capability.reason.lower()
