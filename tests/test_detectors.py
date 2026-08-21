from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from autoclip.web.acceleration import ResolvedAcceleration, TrackerUnavailable


class FakeSession:
    def __init__(self, providers: tuple[str, ...], outputs: list[np.ndarray] | None = None) -> None:
        self._providers = providers
        self._outputs = outputs or [np.empty((0, 5), dtype=np.float32)]
        self.feeds: list[dict[str, np.ndarray]] = []

    def get_providers(self) -> list[str]:
        return list(self._providers)

    def get_inputs(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name="input")]

    def run(self, _: object, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        self.feeds.append(feeds)
        return self._outputs


class FakeSessionFactory:
    def __init__(
        self,
        providers: tuple[str, ...],
        outputs: list[np.ndarray] | None = None,
    ) -> None:
        self.providers = providers
        self.outputs = outputs
        self.requested_providers: list[str] = []
        self.session: FakeSession | None = None

    def __call__(self, model_path: object, providers: list[str]) -> FakeSession:
        del model_path
        self.requested_providers = list(providers)
        self.session = FakeSession(self.providers, self.outputs)
        return self.session


def test_yunet_cuda_requests_cuda_and_no_cpu_provider() -> None:
    from autoclip.web.detectors import DetectorFactory

    sessions = FakeSessionFactory(providers=("CUDAExecutionProvider",))
    detector = DetectorFactory(session_factory=sessions).create(
        ResolvedAcceleration(
            "yunet_cuda",
            "libx264",
            "CUDAExecutionProvider",
            "yunet_2023mar",
        )
    )

    assert sessions.requested_providers == ["CUDAExecutionProvider"]
    assert detector.engine == "yunet_cuda"


def test_yunet_cuda_rejects_session_that_did_not_create_cuda() -> None:
    from autoclip.web.detectors import DetectorFactory

    sessions = FakeSessionFactory(providers=("CPUExecutionProvider",))

    with pytest.raises(TrackerUnavailable, match="did not create CUDAExecutionProvider"):
        DetectorFactory(session_factory=sessions).create(
            ResolvedAcceleration(
                "yunet_cuda",
                "libx264",
                "CUDAExecutionProvider",
                "yunet_2023mar",
            )
        )

    assert sessions.requested_providers == ["CUDAExecutionProvider"]


def test_detector_returns_normalized_centres() -> None:
    from autoclip.web.detectors import YuNetDecoder
    from autoclip.web.tracking import FaceObservation

    outputs = [np.array([[160.0, 90.0, 320.0, 180.0, 0.95]], dtype=np.float32)]

    result = YuNetDecoder().decode(outputs, source_width=640, source_height=360)

    assert result == [FaceObservation(cx=0.5, cy=0.5, confidence=pytest.approx(0.95))]


def test_yunet_decoder_applies_nms_and_stable_confidence_order() -> None:
    from autoclip.web.detectors import YuNetDecoder

    outputs = [
        np.array(
            [
                [64.0, 36.0, 128.0, 72.0, 0.70],
                [320.0, 180.0, 64.0, 36.0, 0.90],
                [66.0, 37.0, 128.0, 72.0, 0.60],
            ],
            dtype=np.float32,
        )
    ]

    result = YuNetDecoder().decode(outputs, source_width=640, source_height=360)

    assert [(face.confidence, face.cx, face.cy) for face in result] == [
        (pytest.approx(0.90), 0.55, 0.55),
        (pytest.approx(0.70), 0.20, 0.20),
    ]


def test_yunet_detector_runs_rgb_float32_nchw_inference() -> None:
    from autoclip.web.detectors import DetectorFactory

    outputs = [np.array([[80.0, 80.0, 160.0, 160.0, 0.8]], dtype=np.float32)]
    sessions = FakeSessionFactory(("CPUExecutionProvider",), outputs)
    detector = DetectorFactory(session_factory=sessions).create(
        ResolvedAcceleration(
            "yunet_cpu",
            "libx264",
            "CPUExecutionProvider",
            "yunet_2023mar",
        )
    )
    frame = np.zeros((320, 320, 3), dtype=np.uint8)
    frame[:, :] = [0, 64, 255]

    faces = detector.detect(frame, 7)

    assert faces[0].cx == 0.5
    assert sessions.session is not None
    tensor = sessions.session.feeds[0]["input"]
    assert tensor.shape == (1, 3, 320, 320)
    assert tensor.dtype == np.float32
    assert tensor[0, :, 0, 0].tolist() == pytest.approx([1.0, 64 / 255, 0.0])


def test_scrfd_detector_uses_insightface_input_and_anchored_output() -> None:
    from autoclip.web.detectors import DetectorFactory

    score_8 = np.zeros((1, 6400), dtype=np.float32)
    score_8[0, 3240] = 0.95
    bbox_8 = np.ones((1, 6400, 4), dtype=np.float32)
    score_16 = np.zeros((1, 1600), dtype=np.float32)
    score_32 = np.zeros((1, 400), dtype=np.float32)
    bbox_16 = np.zeros((1, 1600, 4), dtype=np.float32)
    bbox_32 = np.zeros((1, 400, 4), dtype=np.float32)
    sessions = FakeSessionFactory(
        ("CPUExecutionProvider",),
        [score_8, score_16, score_32, bbox_8, bbox_16, bbox_32],
    )
    detector = DetectorFactory(session_factory=sessions).create(
        ResolvedAcceleration(
            "scrfd_cpu",
            "libx264",
            "CPUExecutionProvider",
            "insightface_antelopev2_scrfd",
        )
    )
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    frame[:, :] = [0, 64, 255]

    faces = detector.detect(frame, 7)

    assert sessions.session is not None
    tensor = sessions.session.feeds[0]["input"]
    assert tensor.shape == (1, 3, 640, 640)
    assert tensor[0, :, 0, 0].tolist() == pytest.approx(
        [0.99609375, -0.49609375, -0.99609375],
    )
    assert [(face.cx, face.cy, face.confidence) for face in faces] == [
        (0.5, 0.5, pytest.approx(0.95)),
    ]


def test_scrfd_detector_rejects_malformed_outputs_instead_of_no_face() -> None:
    from autoclip.web.detectors import DetectorFactory

    sessions = FakeSessionFactory(
        ("CPUExecutionProvider",),
        [np.empty((0, 5), dtype=np.float32)],
    )
    detector = DetectorFactory(session_factory=sessions).create(
        ResolvedAcceleration(
            "scrfd_cpu",
            "libx264",
            "CPUExecutionProvider",
            "insightface_antelopev2_scrfd",
        )
    )

    with pytest.raises(ValueError, match="InsightFace detector outputs"):
        detector.detect(np.zeros((640, 640, 3), dtype=np.uint8), 7)


def test_mediapipe_detector_passes_optional_delegate_and_keeps_video_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    from pathlib import Path

    from autoclip.web.tracking import MediaPipeTasksDetector

    captured: dict[str, object] = {}
    delegate = object()

    class FakeCreatedDetector:
        def detect_for_video(self, image: object, timestamp_ms: int) -> SimpleNamespace:
            captured["image"] = image
            captured["timestamp_ms"] = timestamp_ms
            return SimpleNamespace(detections=[])

        def close(self) -> None:
            captured["closed"] = True

    class FakeFaceDetector:
        @staticmethod
        def create_from_options(options: object) -> FakeCreatedDetector:
            captured["options"] = options
            return FakeCreatedDetector()

    def base_options(**kwargs: object) -> SimpleNamespace:
        captured["base_options"] = kwargs
        return SimpleNamespace(**kwargs)

    def detector_options(**kwargs: object) -> SimpleNamespace:
        captured["detector_options"] = kwargs
        return SimpleNamespace(**kwargs)

    fake_mp = SimpleNamespace(
        tasks=SimpleNamespace(
            BaseOptions=base_options,
            vision=SimpleNamespace(
                FaceDetector=FakeFaceDetector,
                FaceDetectorOptions=detector_options,
                RunningMode=SimpleNamespace(VIDEO="VIDEO"),
            ),
        ),
        Image=lambda **kwargs: SimpleNamespace(**kwargs),
        ImageFormat=SimpleNamespace(SRGB="SRGB"),
    )
    fake_cv2 = SimpleNamespace(COLOR_BGR2RGB=1, cvtColor=lambda frame, _: frame[:, :, ::-1])
    monkeypatch.setitem(sys.modules, "mediapipe", fake_mp)
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    model_path = Path(str(tmp_path)) / "face.task"
    model_path.write_bytes(b"model")

    with MediaPipeTasksDetector(model_path=model_path, delegate=delegate) as detector:
        detector.detect(np.zeros((4, 4, 3), dtype=np.uint8), 9)

    assert captured["base_options"] == {
        "model_asset_path": str(model_path),
        "delegate": delegate,
    }
    assert captured["detector_options"] == {
        "base_options": captured["options"].base_options,  # type: ignore[union-attr]
        "running_mode": "VIDEO",
        "min_detection_confidence": 0.5,
    }
    assert captured["timestamp_ms"] == 9
    assert captured["closed"] is True
