from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from autoclip.web.runtime_store import RuntimeStore


@pytest.fixture
def store(tmp_path: Path) -> RuntimeStore:
    return RuntimeStore(tmp_path / "projects")


def _create_pre_acceleration_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_path TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE artifacts (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                clip_id TEXT,
                kind TEXT NOT NULL,
                path TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?)",
            ("project-1", "Legacy project", "url", "https://example.test/legacy.mp4", "draft"),
        )
        connection.execute(
            "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?)",
            ("artifact-1", "project-1", None, "transcript", "legacy.json"),
        )


def test_old_artifact_table_receives_empty_metadata(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _create_pre_acceleration_database(root / "projects.sqlite3")

    migrated = RuntimeStore(root)

    assert migrated.list_artifacts("project-1")[0].metadata == {}


def test_artifact_metadata_round_trips_without_sharing_input_mapping(store: RuntimeStore) -> None:
    project = store.create_from_url("https://example.test/video.mp4")
    metadata = {
        "encoder_mode": "h264_nvenc",
        "tracker": {"engine": "yunet_cuda", "model_id": "yunet_2023mar"},
    }

    saved = store.save_artifact(project.id, "preview", Path("preview.mp4"), metadata=metadata)
    metadata["encoder_mode"] = "libx264"

    assert saved.metadata["encoder_mode"] == "h264_nvenc"
    assert store.list_artifacts(project.id)[0].metadata == {
        "encoder_mode": "h264_nvenc",
        "tracker": {"engine": "yunet_cuda", "model_id": "yunet_2023mar"},
    }


def test_artifact_rejects_unknown_or_cross_project_clip(store: RuntimeStore) -> None:
    first_project = store.create_from_url("https://example.test/first.mp4")
    second_project = store.create_from_url("https://example.test/second.mp4")
    clip = store.create_clip(
        first_project.id,
        start_time=0,
        end_time=1,
        title="First",
        score=90,
        language="en",
    )

    with pytest.raises(KeyError, match="Clip not found"):
        store.save_artifact(first_project.id, "preview", Path("preview.mp4"), clip_id="missing")
    with pytest.raises(ValueError, match="does not belong"):
        store.save_artifact(second_project.id, "preview", Path("preview.mp4"), clip_id=clip.id)
