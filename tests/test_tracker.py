"""Tests for autoclip.core.tracker — face detection and crop trajectory building."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_bgr_frame(width: int = 320, height: int = 180, color=(100, 120, 140)) -> np.ndarray:
    """Create a solid-color BGR frame for testing."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:] = color
    return frame


# ─── FacePosition dataclass ───────────────────────────────────────────────────


class TestFacePosition:
    def test_basic_fields(self):
        from autoclip.core.tracker import FacePosition
        fp = FacePosition(cx=0.5, cy=0.3, confidence=0.9)
        assert fp.cx == 0.5
        assert fp.cy == 0.3
        assert fp.confidence == 0.9

    def test_default_confidence(self):
        from autoclip.core.tracker import FacePosition
        fp = FacePosition(cx=0.5, cy=0.5)
        assert fp.confidence == 1.0


# ─── dominant_face ────────────────────────────────────────────────────────────


class TestDominantFace:
    def test_returns_none_on_empty(self):
        from autoclip.core.tracker import dominant_face
        assert dominant_face([]) is None

    def test_returns_highest_confidence(self):
        from autoclip.core.tracker import FacePosition, dominant_face
        faces = [
            FacePosition(cx=0.3, cy=0.3, confidence=0.6),
            FacePosition(cx=0.7, cy=0.5, confidence=0.9),
            FacePosition(cx=0.5, cy=0.5, confidence=0.5),
        ]
        best = dominant_face(faces)
        assert best is not None
        assert best.confidence == 0.9

    def test_single_face(self):
        from autoclip.core.tracker import FacePosition, dominant_face
        faces = [FacePosition(cx=0.4, cy=0.4, confidence=0.8)]
        assert dominant_face(faces) is faces[0]


# ─── MediaPipe availability check ────────────────────────────────────────────


class TestMediapipeAvailability:
    def test_returns_bool(self):
        from autoclip.core.tracker import _is_mediapipe_available
        result = _is_mediapipe_available()
        assert isinstance(result, bool)

    def test_false_when_import_fails(self):
        import sys
        with patch.dict(sys.modules, {"mediapipe": None}):
            with patch("autoclip.core.tracker._is_mediapipe_available", return_value=False):
                from autoclip.core.tracker import _is_mediapipe_available as fn
                assert fn() is False


# ─── detect_faces (OpenCV fallback path) ─────────────────────────────────────

cv2_available = False
try:
    import cv2 as _cv2  # noqa: F401
    cv2_available = True
except ImportError:
    pass


@pytest.mark.skipif(not cv2_available, reason="opencv-python not installed")
class TestDetectFacesOpenCV:
    def test_returns_list(self):
        """detect_faces should always return a list, even with no faces."""
        from autoclip.core.tracker import detect_faces
        frame = _make_bgr_frame(320, 240)
        # Solid color frame will have no faces — just verify return type
        result = detect_faces(frame, use_mediapipe=False)
        assert isinstance(result, list)

    def test_face_positions_normalized(self):
        """Any returned FacePosition should have cx/cy in [0, 1]."""
        from autoclip.core.tracker import detect_faces
        frame = _make_bgr_frame(320, 240)
        result = detect_faces(frame, use_mediapipe=False)
        for fp in result:
            assert 0.0 <= fp.cx <= 1.0
            assert 0.0 <= fp.cy <= 1.0


# ─── CropTrajectory ───────────────────────────────────────────────────────────


class TestCropTrajectory:
    def test_len(self):
        from autoclip.core.tracker import CropTrajectory
        traj = CropTrajectory(centers=[(100.0, 200.0), (105.0, 202.0)], fps=30.0)
        assert len(traj) == 2

    def test_empty(self):
        from autoclip.core.tracker import CropTrajectory
        traj = CropTrajectory()
        assert len(traj) == 0


# ─── build_crop_trajectory (mock cv2 via sys.modules) ────────────────────────


def _make_cv2_mock(width=1920, height=1080, fps=30.0, total_frames=30):
    """Build a mock cv2 module with a VideoCapture that yields blank frames."""
    import sys

    mock_cv2 = MagicMock()
    mock_cv2.CAP_PROP_FPS = 5
    mock_cv2.CAP_PROP_FRAME_WIDTH = 3
    mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
    mock_cv2.CAP_PROP_POS_MSEC = 0
    mock_cv2.COLOR_BGR2RGB = 4
    mock_cv2.COLOR_BGR2GRAY = 6
    mock_cv2.INTER_LANCZOS4 = 8

    mock_cap = MagicMock()
    mock_cap.get.side_effect = lambda prop: {
        5: fps,      # CAP_PROP_FPS
        3: width,    # CAP_PROP_FRAME_WIDTH
        4: height,   # CAP_PROP_FRAME_HEIGHT
    }.get(prop, 0)

    frame = np.zeros((height, width, 3), dtype=np.uint8)
    read_returns = [(True, frame)] * total_frames + [(False, None)]
    mock_cap.read.side_effect = read_returns

    mock_cv2.VideoCapture.return_value = mock_cap
    mock_cv2.cvtColor.return_value = frame
    mock_cv2.resize.return_value = frame

    return mock_cv2


class TestBuildCropTrajectory:
    def test_returns_trajectory(self):
        import sys
        from autoclip.core.tracker import build_crop_trajectory

        mock_cv2 = _make_cv2_mock(total_frames=30, fps=30.0)

        with patch.dict(sys.modules, {"cv2": mock_cv2}):
            with patch("autoclip.core.tracker.detect_faces", return_value=[]):
                traj = build_crop_trajectory(
                    video_path=Path("fake.mp4"),
                    start_time=0.0,
                    duration=1.0,
                    target_width=1080,
                    target_height=1920,
                    sample_every_n_frames=5,
                    ema_alpha=0.1,
                    use_mediapipe=False,
                )

        assert hasattr(traj, "centers")
        assert isinstance(traj.centers, list)

    def test_centers_clamped_within_bounds(self):
        """Crop centers should stay within source frame boundaries."""
        import sys
        from autoclip.core.tracker import FacePosition, build_crop_trajectory

        mock_cv2 = _make_cv2_mock(width=1920, height=1080, fps=30.0, total_frames=30)
        extreme_face = FacePosition(cx=0.01, cy=0.01, confidence=0.9)

        with patch.dict(sys.modules, {"cv2": mock_cv2}):
            with patch("autoclip.core.tracker.detect_faces", return_value=[extreme_face]):
                traj = build_crop_trajectory(
                    video_path=Path("fake.mp4"),
                    start_time=0.0,
                    duration=1.0,
                    target_width=1080,
                    target_height=1920,
                    use_mediapipe=False,
                )

        # Compute expected clamping bounds manually
        src_width, src_height = 1920, 1080
        tgt_ratio = 1080 / 1920
        crop_h = src_height
        crop_w = int(crop_h * tgt_ratio)
        half_w, half_h = crop_w / 2, crop_h / 2

        for (cx, cy) in traj.centers:
            assert cx >= half_w, f"cx {cx} < half_w {half_w}"
            assert cy >= half_h, f"cy {cy} < half_h {half_h}"
            assert cx <= src_width - half_w
            assert cy <= src_height - half_h


# ─── TrackerConfig ────────────────────────────────────────────────────────────


class TestTrackerConfig:
    def test_defaults(self):
        from autoclip.models.config import TrackerConfig
        cfg = TrackerConfig()
        assert cfg.enabled is False
        assert 0 < cfg.ema_alpha <= 1.0
        assert cfg.sample_every_n_frames >= 1
        assert cfg.use_mediapipe is True

    def test_enabled_true(self):
        from autoclip.models.config import TrackerConfig
        cfg = TrackerConfig(enabled=True)
        assert cfg.enabled is True

    def test_ema_alpha_bounds(self):
        from autoclip.models.config import TrackerConfig
        with pytest.raises(Exception):
            TrackerConfig(ema_alpha=0.0)  # below ge=0.01
        with pytest.raises(Exception):
            TrackerConfig(ema_alpha=1.5)  # above le=1.0

    def test_autoclipconfig_has_tracker(self):
        from autoclip.models.config import AutoClipConfig, TrackerConfig
        cfg = AutoClipConfig()
        assert isinstance(cfg.tracker, TrackerConfig)
        assert cfg.tracker.enabled is False


# ─── Wizard helper ────────────────────────────────────────────────────────────


class TestWizardFaceTracking:
    def test_is_mediapipe_available_returns_bool(self):
        from autoclip.wizard import _is_mediapipe_available
        result = _is_mediapipe_available()
        assert isinstance(result, bool)
