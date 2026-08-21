from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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


def test_clip_tracking_resolution_rejects_trajectory_from_another_clip_and_project(
    store: FullStudioStore,
) -> None:
    project = store.create_from_url("https://example.test/video.mp4")
    clip = _create_clip(store, project.id)
    other_project = store.create_from_url("https://example.test/other.mp4")
    other_clip = _create_clip(store, other_project.id)
    other_trajectory = store.save_artifact(
        other_project.id,
        "tracking_trajectory",
        Path("other-trajectory.json"),
        clip_id=other_clip.id,
    )

    with pytest.raises(ValueError, match="does not belong"):
        store.save_clip_tracking_resolution(
            clip.id,
            ResolvedAcceleration("yunet_cpu", "libx264", "CPUExecutionProvider", "yunet_2023mar"),
            other_trajectory.id,
        )


def test_clip_tracking_resolution_locks_validation_and_upsert_transaction(
    store: FullStudioStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = store.create_from_url("https://example.test/video.mp4")
    clip = _create_clip(store, project.id)
    trajectory = store.save_artifact(
        project.id,
        "tracking_trajectory",
        Path("trajectory.json"),
        clip_id=clip.id,
    )
    state = {"interleaving_delete_was_locked": False}
    original_connect = store._connect

    class InterleavingConnection:
        def __init__(self) -> None:
            self.connection = original_connect()

        def __enter__(self) -> "InterleavingConnection":
            self.connection.__enter__()
            return self

        def __exit__(self, *args: Any) -> Any:
            return self.connection.__exit__(*args)

        def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
            cursor = self.connection.execute(sql, parameters)
            normalized = " ".join(sql.split())
            if normalized == "SELECT project_id, clip_id, kind FROM artifacts WHERE id = ?":
                row = cursor.fetchone()
                cursor.fetchall()
                competitor = sqlite3.connect(store.database_path, timeout=0)
                try:
                    competitor.execute("DELETE FROM artifacts WHERE id = ?", (trajectory.id,))
                    competitor.commit()
                except sqlite3.OperationalError as error:
                    if "locked" not in str(error).casefold():
                        raise
                    state["interleaving_delete_was_locked"] = True
                finally:
                    competitor.close()

                class CachedCursor:
                    @staticmethod
                    def fetchone() -> Any:
                        return row

                return CachedCursor()
            return cursor

    monkeypatch.setattr(store, "_connect", InterleavingConnection)

    saved = store.save_clip_tracking_resolution(
        clip.id,
        ResolvedAcceleration("yunet_cuda", "libx264", "CUDAExecutionProvider", "yunet_2023mar"),
        trajectory.id,
    )

    assert state["interleaving_delete_was_locked"] is True
    assert saved.trajectory_artifact_id == trajectory.id
    assert store.list_artifacts(project.id)[0].id == trajectory.id


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


def test_model_acknowledgement_persists_after_store_reopens(store: FullStudioStore) -> None:
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
    saved = store.save_model_acknowledgement(plan)

    reopened = FullStudioStore(store.root)
    with sqlite3.connect(reopened.database_path) as connection:
        row = connection.execute(
            """
            SELECT plan_id, source_url, license, acknowledged_at
            FROM model_acknowledgements WHERE plan_id = ?
            """,
            (plan.id,),
        ).fetchone()

    assert row == (plan.id, plan.source_url, plan.license, saved.acknowledged_at)


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
