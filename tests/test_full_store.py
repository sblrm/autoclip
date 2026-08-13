from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from autoclip.web.acceleration import ResolvedAcceleration
from autoclip.web.full_store import FullStudioStore
from autoclip.web.model_catalog import ModelPlan


@pytest.fixture
def store(tmp_path: Path) -> FullStudioStore:
    return FullStudioStore(tmp_path / "projects")


def _create_clip(store: FullStudioStore, project_id: str):
    return store.create_clip(
        project_id,
        start_time=0,
        end_time=1,
        title="Candidate",
        score=90,
        language="en",
    )


def test_project_selection_defaults_to_auto_and_round_trips(store: FullStudioStore) -> None:
    project = store.create_from_url("https://example.test/video.mp4")

    default = store.get_project_acceleration(project.id)
    saved = store.set_project_acceleration(
        project.id,
        tracker_engine="yunet_cuda",
        encoder_mode="h264_nvenc",
    )

    assert (default.tracker_engine, default.encoder_mode) == ("auto", "auto")
    assert saved.tracker_engine == "yunet_cuda"
    assert store.get_project_acceleration(project.id).encoder_mode == "h264_nvenc"


def test_project_selection_rejects_unknown_project(store: FullStudioStore) -> None:
    with pytest.raises(KeyError, match="Project not found"):
        store.get_project_acceleration("missing")
    with pytest.raises(KeyError, match="Project not found"):
        store.set_project_acceleration("missing", tracker_engine="auto", encoder_mode="auto")


@pytest.mark.parametrize(
    ("tracker_engine", "encoder_mode"),
    [("bogus", "auto"), ("auto", "bogus")],
)
def test_project_selection_rejects_invalid_engine_ids(
    store: FullStudioStore,
    tracker_engine: str,
    encoder_mode: str,
) -> None:
    project = store.create_from_url("https://example.test/video.mp4")

    with pytest.raises(ValueError, match="Unknown"):
        store.set_project_acceleration(  # type: ignore[arg-type]
            project.id,
            tracker_engine=tracker_engine,
            encoder_mode=encoder_mode,
        )


def test_clip_tracking_resolution_replaces_verified_run(store: FullStudioStore) -> None:
    project = store.create_from_url("https://example.test/video.mp4")
    clip = _create_clip(store, project.id)
    trajectory = store.save_artifact(
        project.id,
        "tracking_trajectory",
        Path("trajectory.json"),
        clip_id=clip.id,
    )

    store.save_clip_tracking_resolution(
        clip.id,
        ResolvedAcceleration("mediapipe_cpu", "libx264", "MediaPipe", None),
        trajectory.id,
    )
    replaced = store.save_clip_tracking_resolution(
        clip.id,
        ResolvedAcceleration("yunet_cuda", "h264_nvenc", "CUDAExecutionProvider", "yunet_2023mar"),
        trajectory.id,
    )

    assert replaced.tracker_engine == "yunet_cuda"
    assert replaced.provider == "CUDAExecutionProvider"
    assert replaced.model_id == "yunet_2023mar"
    assert store.get_clip_tracking_resolution(clip.id) == replaced


def test_clip_tracking_resolution_validates_clip_and_trajectory_ids(store: FullStudioStore) -> None:
    project = store.create_from_url("https://example.test/video.mp4")
    clip = _create_clip(store, project.id)
    export = store.save_artifact(project.id, "export", Path("export.mp4"), clip_id=clip.id)
    resolution = ResolvedAcceleration("yunet_cpu", "libx264", "CPUExecutionProvider", "yunet_2023mar")

    with pytest.raises(KeyError, match="Clip not found"):
        store.get_clip_tracking_resolution("missing")
    with pytest.raises(KeyError, match="Clip not found"):
        store.save_clip_tracking_resolution("missing", resolution, None)
    with pytest.raises(KeyError, match="Artifact not found"):
        store.save_clip_tracking_resolution(clip.id, resolution, "missing")
    with pytest.raises(ValueError, match="tracking trajectory"):
        store.save_clip_tracking_resolution(clip.id, resolution, export.id)


def test_model_acknowledgement_records_plan_source_and_utc_timestamp(store: FullStudioStore) -> None:
    plan = ModelPlan(
        id="research-model",
        label="Research model",
        source_url="https://models.example.test/research.zip",
        sha256="a" * 64,
        bytes=10,
        license="Non-commercial research only",
        research_only=True,
        destination_relative_path="research/model.onnx",
    )

    acknowledgement = store.save_model_acknowledgement(plan)
    timestamp = datetime.fromisoformat(acknowledgement.acknowledged_at)

    assert acknowledgement.plan_id == plan.id
    assert acknowledgement.source_url == plan.source_url
    assert acknowledgement.license == plan.license
    assert timestamp.utcoffset() == timedelta(0)


def test_clear_tracking_data_removes_resolution_and_tracking_artifacts(store: FullStudioStore) -> None:
    project = store.create_from_url("https://example.test/video.mp4")
    clip = _create_clip(store, project.id)
    preview = store.save_artifact(project.id, "tracking_preview", Path("preview.mp4"), clip_id=clip.id)
    trajectory = store.save_artifact(
        project.id,
        "tracking_trajectory",
        Path("trajectory.json"),
        clip_id=clip.id,
    )
    exported = store.save_artifact(project.id, "export", Path("export.mp4"), clip_id=clip.id)
    store.save_clip_tracking_resolution(
        clip.id,
        ResolvedAcceleration("yunet_cuda", "libx264", "CUDAExecutionProvider", "yunet_2023mar"),
        trajectory.id,
    )

    store.clear_tracking_data(clip.id)

    assert store.get_clip_tracking_resolution(clip.id) is None
    assert {artifact.id for artifact in store.list_artifacts(project.id)} == {exported.id}
    assert preview.id != exported.id
