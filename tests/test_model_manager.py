"""Tests for the pinned, checksum-verified local face-model installer."""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

import autoclip.web.model_manager as model_manager
from autoclip.web.model_catalog import MODEL_PLANS, ModelPlan
from autoclip.web.model_manager import (
    ModelChecksumError,
    ModelManager,
    ModelSizeError,
    ResearchAcknowledgementRequired,
    UnknownModelPlan,
    UnsafeArchiveMember,
)


class FakeDownloader:
    """Deterministic streaming substitute for the external downloader."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        return iter((self.payload[:2], self.payload[2:]))


def _plan_for(payload: bytes, *, archive_member: str | None = None) -> ModelPlan:
    return ModelPlan(
        id="test_model",
        label="Test model",
        source_url="https://models.example.invalid/test-model",
        sha256=hashlib.sha256(payload).hexdigest(),
        bytes=len(payload),
        license="Test",
        research_only=archive_member is not None,
        destination_relative_path="models/test.onnx",
        archive_member=archive_member,
    )


def _install_test_plan(monkeypatch: pytest.MonkeyPatch, plan: ModelPlan) -> None:
    monkeypatch.setattr(model_manager, "MODEL_PLANS", {plan.id: plan})


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return output.getvalue()


def test_yunet_plan_is_fixed_and_commercial_safe() -> None:
    plan = MODEL_PLANS["yunet_2023mar"]

    assert plan.research_only is False
    assert plan.sha256 == "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
    assert plan.destination_relative_path == "yunet/face_detection_yunet_2023mar.onnx"


def test_research_model_requires_acknowledgement(tmp_path: Path) -> None:
    manager = ModelManager(tmp_path, downloader=FakeDownloader(b"wrong"))

    with pytest.raises(ResearchAcknowledgementRequired):
        manager.install("insightface_buffalo_m_retinaface", False, lambda *_: None)


def test_bad_checksum_removes_partial_file(tmp_path: Path) -> None:
    manager = ModelManager(tmp_path, downloader=FakeDownloader(b"wrong"))

    with pytest.raises(ModelChecksumError):
        manager.install("yunet_2023mar", False, lambda *_: None)

    assert not list(tmp_path.rglob("*.part"))
    assert not (tmp_path / "yunet" / "face_detection_yunet_2023mar.onnx").exists()


def test_unknown_model_id_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnknownModelPlan, match="unknown_model"):
        ModelManager(tmp_path, downloader=FakeDownloader(b"")).install(
            "unknown_model", False, lambda *_: None,
        )


def test_install_accepts_only_the_server_selected_plan_id(tmp_path: Path) -> None:
    parameters = inspect.signature(ModelManager.install).parameters

    assert tuple(parameters) == ("self", "plan_id", "acknowledged", "report")


def test_valid_cached_model_returns_without_downloading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"verified model"
    plan = _plan_for(payload)
    _install_test_plan(monkeypatch, plan)
    destination = tmp_path / plan.destination_relative_path
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload)
    downloader = FakeDownloader(b"should never be consumed")

    installed = ModelManager(tmp_path, downloader=downloader).install(plan.id, False, lambda *_: None)

    assert installed.path == destination
    assert installed.cached is True
    assert downloader.calls == []


def test_is_installed_validates_direct_model_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"verified model"
    plan = _plan_for(payload)
    _install_test_plan(monkeypatch, plan)
    destination = tmp_path / plan.destination_relative_path
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload)
    manager = ModelManager(tmp_path, downloader=FakeDownloader(b"unused"))

    assert manager.is_installed(plan.id) is True

    destination.write_bytes(b"tampered model")
    assert manager.is_installed(plan.id) is False


def test_acknowledged_research_archive_is_extracted_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = b"archive model"
    archive = _zip_bytes({"det_2.5g.onnx": model})
    plan = _plan_for(archive, archive_member="det_2.5g.onnx")
    _install_test_plan(monkeypatch, plan)
    downloader = FakeDownloader(archive)
    manager = ModelManager(tmp_path, downloader=downloader)

    installed = manager.install(plan.id, True, lambda *_: None)
    cached = manager.install(plan.id, True, lambda *_: None)

    assert installed.path.read_bytes() == model
    assert installed.cached is False
    assert cached.path == installed.path
    assert cached.cached is True
    assert downloader.calls == [plan.source_url]
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("*.zip"))


def test_is_installed_validates_archive_manifest_and_extracted_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = b"archive model"
    archive = _zip_bytes({"det_2.5g.onnx": model})
    plan = _plan_for(archive, archive_member="det_2.5g.onnx")
    _install_test_plan(monkeypatch, plan)
    manager = ModelManager(tmp_path, downloader=FakeDownloader(archive))

    installed = manager.install(plan.id, True, lambda *_: None)
    assert manager.is_installed(plan.id) is True

    installed.path.write_bytes(b"tampered payload")
    assert manager.is_installed(plan.id) is False


def test_archive_cache_requires_matching_identity_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = b"archive model"
    archive = _zip_bytes({"det_2.5g.onnx": model})
    plan = _plan_for(archive, archive_member="det_2.5g.onnx")
    _install_test_plan(monkeypatch, plan)
    downloader = FakeDownloader(archive)
    manager = ModelManager(tmp_path, downloader=downloader)

    installed = manager.install(plan.id, True, lambda *_: None)
    manifest = installed.path.with_name(f"{installed.path.name}.autoclip.json")

    assert manifest.is_file()
    assert json.loads(manifest.read_text(encoding="utf-8")) == {
        "archive_bytes": len(archive),
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "destination_relative_path": "models/test.onnx",
        "extracted_bytes": len(model),
        "extracted_sha256": hashlib.sha256(model).hexdigest(),
        "plan_id": "test_model",
        "source_url": "https://models.example.invalid/test-model",
    }

    manifest.write_text("{}", encoding="utf-8")
    reinstalled = manager.install(plan.id, True, lambda *_: None)

    assert reinstalled.cached is False
    assert downloader.calls == [plan.source_url, plan.source_url]


def test_archive_cache_redownloads_if_extracted_payload_is_tampered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = b"archive model"
    archive = _zip_bytes({"det_2.5g.onnx": model})
    plan = _plan_for(archive, archive_member="det_2.5g.onnx")
    _install_test_plan(monkeypatch, plan)
    downloader = FakeDownloader(archive)
    manager = ModelManager(tmp_path, downloader=downloader)

    installed = manager.install(plan.id, True, lambda *_: None)
    installed.path.write_bytes(b"tampered payload")

    reinstalled = manager.install(plan.id, True, lambda *_: None)

    assert reinstalled.cached is False
    assert reinstalled.path.read_bytes() == model
    assert downloader.calls == [plan.source_url, plan.source_url]


def test_overlarge_stream_is_deleted_before_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"12345"
    plan = replace(_plan_for(payload), bytes=4)
    _install_test_plan(monkeypatch, plan)

    with pytest.raises(ModelSizeError):
        ModelManager(tmp_path, downloader=FakeDownloader(payload)).install(plan.id, False, lambda *_: None)

    assert not list(tmp_path.rglob("*.part"))
    assert not (tmp_path / plan.destination_relative_path).exists()


def test_archive_with_unsafe_member_cannot_escape_models_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _zip_bytes({"det_2.5g.onnx": b"model", "../escaped.onnx": b"unsafe"})
    plan = _plan_for(archive, archive_member="det_2.5g.onnx")
    _install_test_plan(monkeypatch, plan)

    with pytest.raises(UnsafeArchiveMember):
        ModelManager(tmp_path, downloader=FakeDownloader(archive)).install(plan.id, True, lambda *_: None)

    assert not (tmp_path.parent / "escaped.onnx").exists()
    assert not (tmp_path / plan.destination_relative_path).exists()
    assert not list(tmp_path.rglob("*.part"))
