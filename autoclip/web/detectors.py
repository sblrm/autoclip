"""Strict, injectable face-detector adapters for local video inference."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from autoclip.web.acceleration import ResolvedAcceleration, TrackerEngine, TrackerUnavailable
from autoclip.web.model_catalog import MODEL_PLANS
from autoclip.web.tracking import FaceObservation, MediaPipeTasksDetector


class VideoFaceDetector(Protocol):
    engine: TrackerEngine
    provider: str
    model_id: str | None

    def __enter__(self) -> "VideoFaceDetector": ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def detect(
        self,
        frame_bgr: NDArray[np.uint8],
        timestamp_ms: int,
    ) -> list[FaceObservation]: ...


class OnnxSession(Protocol):
    def get_providers(self) -> Sequence[str]: ...

    def get_inputs(self) -> Sequence[Any]: ...

    def run(self, output_names: object, feeds: Mapping[str, NDArray[np.float32]]) -> Sequence[Any]: ...


SessionFactory = Callable[[Path, list[str]], OnnxSession]


def _create_ort_session(model_path: Path, providers: list[str]) -> OnnxSession:
    try:
        import onnxruntime
    except ImportError as exc:
        raise TrackerUnavailable("onnxruntime is not installed") from exc

    onnxruntime.preload_dlls()
    return cast(
        OnnxSession,
        onnxruntime.InferenceSession(str(model_path), providers=providers),
    )


@dataclass(frozen=True)
class _Letterbox:
    tensor: NDArray[np.float32]
    scale: float
    pad_x: float
    pad_y: float


@dataclass(frozen=True)
class _Box:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


class YuNetDecoder:
    """Decode YuNet output, reverse letterboxing, and apply deterministic NMS."""

    def __init__(self, *, score_threshold: float = 0.5, nms_iou: float = 0.3) -> None:
        self.score_threshold = score_threshold
        self.nms_iou = nms_iou

    def decode(
        self,
        outputs: Sequence[Any] | Mapping[str, Any],
        *,
        source_width: int,
        source_height: int,
        scale: float = 1.0,
        pad_x: float = 0.0,
        pad_y: float = 0.0,
    ) -> list[FaceObservation]:
        boxes = self._boxes(outputs)
        restored = [
            _Box(
                x1=(box.x1 - pad_x) / scale,
                y1=(box.y1 - pad_y) / scale,
                x2=(box.x2 - pad_x) / scale,
                y2=(box.y2 - pad_y) / scale,
                confidence=box.confidence,
            )
            for box in boxes
            if box.confidence >= self.score_threshold
        ]
        return _observations(_nms(restored, self.nms_iou), source_width, source_height)

    def _boxes(self, outputs: Sequence[Any] | Mapping[str, Any]) -> list[_Box]:
        if isinstance(outputs, Mapping):
            raw_boxes = self._raw_stride_boxes(outputs)
            if raw_boxes is not None:
                return raw_boxes
            arrays = list(outputs.values())
        else:
            arrays = list(outputs)

        for output in arrays:
            array = np.asarray(output)
            if array.size == 0:
                continue
            rows = array.reshape(-1, array.shape[-1])
            if rows.shape[1] >= 5:
                return [
                    _Box(
                        x1=float(row[0]),
                        y1=float(row[1]),
                        x2=float(row[0] + max(0.0, float(row[2]))),
                        y2=float(row[1] + max(0.0, float(row[3]))),
                        confidence=float(row[-1]),
                    )
                    for row in rows
                ]
        return []

    @staticmethod
    def _raw_stride_boxes(outputs: Mapping[str, Any]) -> list[_Box] | None:
        boxes: list[_Box] = []
        found = False
        for stride in (8, 16, 32):
            cls = _named_output(outputs, f"cls_{stride}")
            obj = _named_output(outputs, f"obj_{stride}")
            bbox = _named_output(outputs, f"bbox_{stride}")
            if cls is None or obj is None or bbox is None:
                continue
            found = True
            cls_rows = np.asarray(cls, dtype=np.float32).reshape(-1)
            obj_rows = np.asarray(obj, dtype=np.float32).reshape(-1)
            bbox_rows = np.asarray(bbox, dtype=np.float32).reshape(-1, 4)
            count = min(len(cls_rows), len(obj_rows), len(bbox_rows))
            grid_width = max(1, 320 // stride)
            for index in range(count):
                score = float(
                    np.sqrt(
                        np.clip(cls_rows[index], 0, 1) * np.clip(obj_rows[index], 0, 1)
                    )
                )
                dx, dy, dw, dh = bbox_rows[index]
                grid_x = index % grid_width
                grid_y = index // grid_width
                center_x = (grid_x + float(dx)) * stride
                center_y = (grid_y + float(dy)) * stride
                width = float(np.exp(np.clip(dw, -10, 10))) * stride
                height = float(np.exp(np.clip(dh, -10, 10))) * stride
                boxes.append(
                    _Box(
                        center_x - width / 2,
                        center_y - height / 2,
                        center_x + width / 2,
                        center_y + height / 2,
                        score,
                    )
                )
        return boxes if found else None


class InsightFaceDecoder:
    """Decode detector-only SCRFD/RetinaFace anchor-stride ONNX outputs."""

    def __init__(self, *, score_threshold: float = 0.5, nms_iou: float = 0.3) -> None:
        self.score_threshold = score_threshold
        self.nms_iou = nms_iou

    def decode(
        self,
        outputs: Sequence[Any],
        *,
        source_width: int,
        source_height: int,
        input_size: int,
        scale: float,
        pad_x: float,
        pad_y: float,
    ) -> list[FaceObservation]:
        arrays = [np.asarray(output) for output in outputs]
        if len(arrays) not in (6, 9):
            raise ValueError("InsightFace detector outputs require three score and bbox tensors")

        scores = arrays[:3]
        distances = arrays[3:6]
        strides = (8, 16, 32)
        boxes: list[_Box] = []
        for score_output, distance_output, stride in zip(scores, distances, strides):
            try:
                score_rows = score_output.reshape(-1)
                distance_rows = distance_output.reshape(-1, 4)
            except ValueError as exc:
                raise ValueError("InsightFace detector outputs have invalid score or bbox shapes") from exc
            feature_width = input_size // stride
            cells = feature_width * feature_width
            if (
                len(score_rows) not in (cells, cells * 2)
                or len(distance_rows) != len(score_rows)
            ):
                raise ValueError("InsightFace detector outputs do not match anchor-stride layout")
            anchors_per_cell = len(score_rows) // cells
            for index, (score, distance) in enumerate(zip(score_rows, distance_rows)):
                confidence = float(score)
                if confidence < self.score_threshold:
                    continue
                cell = index // anchors_per_cell
                anchor_x = (cell % feature_width) * stride
                anchor_y = (cell // feature_width) * stride
                left, top, right, bottom = distance.astype(np.float32) * stride
                boxes.append(
                    _Box(
                        x1=(anchor_x - float(left) - pad_x) / scale,
                        y1=(anchor_y - float(top) - pad_y) / scale,
                        x2=(anchor_x + float(right) - pad_x) / scale,
                        y2=(anchor_y + float(bottom) - pad_y) / scale,
                        confidence=confidence,
                    )
                )
        return _observations(_nms(boxes, self.nms_iou), source_width, source_height)


class _OnnxDetector:
    input_size = 320

    def __init__(
        self,
        *,
        engine: TrackerEngine,
        provider: str,
        model_id: str,
        model_path: Path,
        session_factory: SessionFactory,
    ) -> None:
        self.engine = engine
        self.provider = provider
        self.model_id = model_id
        self.model_path = model_path
        self._session = session_factory(model_path, [provider])
        if provider not in self._session.get_providers():
            raise TrackerUnavailable(f"{engine} did not create {provider}")
        inputs = self._session.get_inputs()
        if not inputs:
            raise TrackerUnavailable(f"{engine} has no ONNX input")
        self._input_name = str(inputs[0].name)
        self._last_timestamp_ms: int | None = None

    def __enter__(self) -> "_OnnxDetector":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def _infer(
        self,
        frame_bgr: NDArray[np.uint8],
        timestamp_ms: int,
    ) -> tuple[Sequence[Any], _Letterbox]:
        if self._last_timestamp_ms is not None and timestamp_ms < self._last_timestamp_ms:
            raise ValueError("timestamp_ms must be monotonic")
        self._last_timestamp_ms = timestamp_ms
        letterbox = self._preprocess(frame_bgr)
        outputs = self._session.run(None, {self._input_name: letterbox.tensor})
        return outputs, letterbox

    def _preprocess(self, frame_bgr: NDArray[np.uint8]) -> _Letterbox:
        return _letterbox(frame_bgr, self.input_size)


class YuNetOnnxDetector(_OnnxDetector):
    """YuNet ONNX adapter with strict single-provider execution."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._decoder = YuNetDecoder()

    def detect(
        self,
        frame_bgr: NDArray[np.uint8],
        timestamp_ms: int,
    ) -> list[FaceObservation]:
        outputs, letterbox = self._infer(frame_bgr, timestamp_ms)
        height, width = frame_bgr.shape[:2]
        named_outputs: Sequence[Any] | Mapping[str, Any] = outputs
        get_outputs = getattr(self._session, "get_outputs", None)
        if callable(get_outputs):
            names = [str(item.name) for item in get_outputs()]
            if len(names) == len(outputs):
                named_outputs = dict(zip(names, outputs))
        return self._decoder.decode(
            named_outputs,
            source_width=width,
            source_height=height,
            scale=letterbox.scale,
            pad_x=letterbox.pad_x,
            pad_y=letterbox.pad_y,
        )


class InsightFaceOnnxDetector(_OnnxDetector):
    """Extraction-only InsightFace detector adapter; no recognition state exists."""

    input_size = 640

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._decoder = InsightFaceDecoder()

    def _preprocess(self, frame_bgr: NDArray[np.uint8]) -> _Letterbox:
        return _letterbox(frame_bgr, self.input_size, normalization="insightface")

    def detect(
        self,
        frame_bgr: NDArray[np.uint8],
        timestamp_ms: int,
    ) -> list[FaceObservation]:
        outputs, letterbox = self._infer(frame_bgr, timestamp_ms)
        height, width = frame_bgr.shape[:2]
        return self._decoder.decode(
            outputs,
            source_width=width,
            source_height=height,
            input_size=self.input_size,
            scale=letterbox.scale,
            pad_x=letterbox.pad_x,
            pad_y=letterbox.pad_y,
        )


class DetectorFactory:
    """Create only the exact engine/provider selected by verified status."""

    _MODEL_IDS = {
        "yunet_cpu": "yunet_2023mar",
        "yunet_cuda": "yunet_2023mar",
        "scrfd_cpu": "insightface_antelopev2_scrfd",
        "scrfd_cuda": "insightface_antelopev2_scrfd",
        "retinaface_cpu": "insightface_buffalo_m_retinaface",
        "retinaface_cuda": "insightface_buffalo_m_retinaface",
    }

    def __init__(
        self,
        *,
        session_factory: SessionFactory | None = None,
        models_root: Path | None = None,
    ) -> None:
        self._session_factory = session_factory or _create_ort_session
        self._models_root = (models_root or Path.home() / ".autoclip" / "models").expanduser()

    def create(self, resolution: ResolvedAcceleration) -> VideoFaceDetector:
        engine = resolution.tracker_engine
        if engine == "auto":
            raise TrackerUnavailable("auto must be resolved before detector creation")

        if engine in ("mediapipe_cpu", "mediapipe_gpu"):
            expected_provider = "GPUDelegate" if engine == "mediapipe_gpu" else "CPUDelegate"
            _require_provider(resolution, expected_provider)
            delegate: Any | None = None
            if engine == "mediapipe_gpu":
                try:
                    import mediapipe as mp

                    delegate = mp.tasks.BaseOptions.Delegate.GPU
                except (AttributeError, ImportError) as exc:
                    raise TrackerUnavailable("MediaPipe GPU delegate is unavailable") from exc
            return MediaPipeTasksDetector(
                delegate=delegate,
                engine=engine,
                provider=expected_provider,
                model_id=resolution.model_id,
            )

        expected_provider = (
            "CUDAExecutionProvider" if engine.endswith("_cuda") else "CPUExecutionProvider"
        )
        _require_provider(resolution, expected_provider)
        expected_model_id = self._MODEL_IDS[engine]
        if resolution.model_id != expected_model_id:
            raise TrackerUnavailable(f"{engine} requires detector model {expected_model_id}")
        plan = MODEL_PLANS[expected_model_id]
        model_path = self._models_root / Path(*plan.destination_relative_path.split("/"))
        detector_type = YuNetOnnxDetector if engine.startswith("yunet_") else InsightFaceOnnxDetector
        return detector_type(
            engine=engine,
            provider=expected_provider,
            model_id=expected_model_id,
            model_path=model_path,
            session_factory=self._session_factory,
        )


def _require_provider(resolution: ResolvedAcceleration, expected_provider: str) -> None:
    if resolution.provider != expected_provider:
        raise TrackerUnavailable(f"{resolution.tracker_engine} requires {expected_provider}")


def _letterbox(
    frame_bgr: NDArray[np.uint8],
    input_size: int,
    *,
    normalization: str = "yunet",
) -> _Letterbox:
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise ValueError("frame_bgr must have shape (height, width, 3)")
    source_height, source_width = frame_bgr.shape[:2]
    if source_height <= 0 or source_width <= 0:
        raise ValueError("frame_bgr dimensions must be positive")
    scale = min(input_size / source_width, input_size / source_height)
    resized_width = max(1, min(input_size, round(source_width * scale)))
    resized_height = max(1, min(input_size, round(source_height * scale)))
    resized = _resize_nearest(frame_bgr, resized_width, resized_height)
    pad_x = (input_size - resized_width) // 2
    pad_y = (input_size - resized_height) // 2
    canvas = np.zeros((input_size, input_size, 3), dtype=np.uint8)
    canvas[pad_y : pad_y + resized_height, pad_x : pad_x + resized_width] = resized
    rgb = canvas[:, :, ::-1]
    tensor = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32)
    if normalization == "yunet":
        tensor /= 255.0
    elif normalization == "insightface":
        tensor = (tensor - 127.5) / 128.0
    else:
        raise ValueError(f"unknown detector normalization: {normalization}")
    return _Letterbox(tensor=tensor, scale=scale, pad_x=float(pad_x), pad_y=float(pad_y))


def _resize_nearest(
    image: NDArray[np.uint8],
    width: int,
    height: int,
) -> NDArray[np.uint8]:
    if image.shape[1] == width and image.shape[0] == height:
        return image
    y_indices = np.minimum(
        (np.arange(height, dtype=np.float64) * image.shape[0] / height).astype(np.intp),
        image.shape[0] - 1,
    )
    x_indices = np.minimum(
        (np.arange(width, dtype=np.float64) * image.shape[1] / width).astype(np.intp),
        image.shape[1] - 1,
    )
    return image[y_indices[:, None], x_indices[None, :]]


def _named_output(outputs: Mapping[str, Any], wanted: str) -> Any | None:
    wanted_folded = wanted.casefold()
    for name, value in outputs.items():
        if str(name).casefold() == wanted_folded:
            return value
    return None


def _nms(boxes: Sequence[_Box], threshold: float) -> list[_Box]:
    ordered = sorted(boxes, key=lambda box: (-box.confidence, box.x1, box.y1))
    kept: list[_Box] = []
    for candidate in ordered:
        if all(_iou(candidate, previous) <= threshold for previous in kept):
            kept.append(candidate)
    return kept


def _iou(left: _Box, right: _Box) -> float:
    intersection_width = max(0.0, min(left.x2, right.x2) - max(left.x1, right.x1))
    intersection_height = max(0.0, min(left.y2, right.y2) - max(left.y1, right.y1))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left.x2 - left.x1) * max(0.0, left.y2 - left.y1)
    right_area = max(0.0, right.x2 - right.x1) * max(0.0, right.y2 - right.y1)
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _observations(
    boxes: Sequence[_Box],
    source_width: int,
    source_height: int,
) -> list[FaceObservation]:
    observations = [
        FaceObservation(
            cx=_clamp(((box.x1 + box.x2) / 2) / source_width),
            cy=_clamp(((box.y1 + box.y2) / 2) / source_height),
            confidence=_clamp(box.confidence),
        )
        for box in boxes
    ]
    return sorted(observations, key=lambda face: (-face.confidence, face.cx, face.cy))


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
