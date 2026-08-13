from __future__ import annotations


def test_bundled_face_detector_model_is_ready_for_mediapipe_tasks() -> None:
    from autoclip.web.tracking import default_model_path, get_tracker_capability

    capability = get_tracker_capability(default_model_path())

    assert default_model_path().is_file()
    assert capability.available is True
