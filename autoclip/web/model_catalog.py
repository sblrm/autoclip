"""Pinned, application-owned model download plans.

No caller can supply an alternate URL or destination: adding a model means
reviewing and extending this catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ModelPlan:
    id: str
    label: str
    source_url: str
    sha256: str
    bytes: int
    license: str
    research_only: bool
    destination_relative_path: str
    archive_member: str | None = None


MODEL_PLANS: Mapping[str, ModelPlan] = MappingProxyType(
    {
        "yunet_2023mar": ModelPlan(
            id="yunet_2023mar",
            label="YuNet 2023mar",
            source_url=(
                "https://github.com/opencv/opencv_zoo/raw/4.10.0/models/face_detection_yunet/"
                "face_detection_yunet_2023mar.onnx"
            ),
            sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
            bytes=232589,
            license="MIT",
            research_only=False,
            destination_relative_path="yunet/face_detection_yunet_2023mar.onnx",
        ),
        "insightface_buffalo_m_retinaface": ModelPlan(
            "insightface_buffalo_m_retinaface",
            "InsightFace buffalo_m RetinaFace detector",
            "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_m.zip",
            "d98264bd8f2dc75cbc2ddce2a14e636e02bb857b3051c234b737bf3b614edca9",
            275951529,
            "Non-commercial research only (InsightFace pretrained asset)",
            True,
            "insightface/buffalo_m/det_2.5g.onnx",
            "det_2.5g.onnx",
        ),
        "insightface_antelopev2_scrfd": ModelPlan(
            "insightface_antelopev2_scrfd",
            "InsightFace antelopev2 SCRFD detector",
            "https://github.com/deepinsight/insightface/releases/download/v0.7/antelopev2.zip",
            "8e182f14fc6e80b3bfa375b33eb6cff7ee05d8ef7633e738d1c89021dcf0c5c5",
            360662982,
            "Non-commercial research only (InsightFace pretrained asset)",
            True,
            "insightface/antelopev2/scrfd_10g_bnkps.onnx",
            "scrfd_10g_bnkps.onnx",
        ),
    },
)
