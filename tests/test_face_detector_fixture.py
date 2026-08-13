from __future__ import annotations

from pathlib import Path

import pytest


def test_tasks_detector_finds_multiple_people_in_the_licensed_video_fixture() -> None:
    cv2 = pytest.importorskip("cv2")
    from autoclip.web.tracking import MediaPipeTasksDetector

    fixture = Path(__file__).parent / "fixtures" / "two_people_pixabay.mp4"
    capture = cv2.VideoCapture(str(fixture))
    ok, frame = capture.read()
    capture.release()
    assert ok, "licensed fixture must be decodable"
    with MediaPipeTasksDetector() as detector:
        faces = detector.detect(frame, 1)
    assert len(faces) >= 2
