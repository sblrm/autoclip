from __future__ import annotations

import pytest


def test_tasks_detector_initializes_once_and_accepts_monotonic_video_timestamps() -> None:
    numpy = pytest.importorskip("numpy")
    from autoclip.web.tracking import MediaPipeTasksDetector

    frame = numpy.zeros((72, 128, 3), dtype=numpy.uint8)
    with MediaPipeTasksDetector() as detector:
        first = detector.detect(frame, 1)
        second = detector.detect(frame, 2)

    assert first == []
    assert second == []
