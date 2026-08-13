"""Extended persistence used by the running local AutoClip studio."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from autoclip.web.studio_store import Job, StudioStore
from autoclip.web.store import Project


@dataclass(frozen=True)
class FaceTrackRecord:
    id: str
    clip_id: str
    label: str
    confidence: float
    samples: list[dict[str, float] | None]


@dataclass(frozen=True)
class Artifact:
    id: str
    project_id: str
    clip_id: str | None
    kind: str
    path: str


class RuntimeStore(StudioStore):
    """Adds job lists, URL projects, face tracks, and export artifacts."""

    def _initialize(self) -> None:
        super()._initialize()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS face_tracks (
                    id TEXT PRIMARY KEY,
                    clip_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    samples TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    clip_id TEXT,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL
                )
                """
            )

    def create_from_url(self, url: str) -> Project:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("A valid HTTP(S) video URL is required")
        project_id = __import__("uuid").uuid4().hex
        title = parsed.netloc.removeprefix("www.")
        project_root = self.root / project_id
        (project_root / "source").mkdir(parents=True)
        project = Project(
            id=project_id,
            title=title,
            source_kind="url",
            source_path=url,
            status="draft",
        )
        self._save(project)
        return project

    def list_projects(self) -> list[Project]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, title, source_kind, source_path, status FROM projects ORDER BY rowid DESC"
            ).fetchall()
        return [Project(**dict(row)) for row in rows]

    def list_jobs(self, project_id: str) -> list[Job]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, kind, stage, progress, message, error
                FROM jobs WHERE project_id = ? ORDER BY rowid
                """,
                (project_id,),
            ).fetchall()
        return [Job(**dict(row)) for row in rows]

    def set_project_status(self, project_id: str, status: str) -> Project:
        self.get_project(project_id)
        with self._connect() as connection:
            connection.execute("UPDATE projects SET status = ? WHERE id = ?", (status, project_id))
        return self.get_project(project_id)

    def save_face_track(
        self,
        clip_id: str,
        *,
        label: str,
        confidence: float,
        samples: list[dict[str, float] | None],
    ) -> FaceTrackRecord:
        clip = self.get_clip(clip_id)
        record = FaceTrackRecord(
            id=__import__("uuid").uuid4().hex,
            clip_id=clip.id,
            label=label,
            confidence=confidence,
            samples=samples,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO face_tracks (id, clip_id, label, confidence, samples) VALUES (?, ?, ?, ?, ?)",
                (record.id, record.clip_id, record.label, record.confidence, json.dumps(record.samples)),
            )
        return record

    def list_face_tracks(self, clip_id: str) -> list[FaceTrackRecord]:
        self.get_clip(clip_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, clip_id, label, confidence, samples FROM face_tracks WHERE clip_id = ? ORDER BY rowid",
                (clip_id,),
            ).fetchall()
        return [self._track_from_row(row) for row in rows]

    def save_artifact(self, project_id: str, kind: str, path: Path, clip_id: str | None = None) -> Artifact:
        self.get_project(project_id)
        artifact = Artifact(
            id=__import__("uuid").uuid4().hex,
            project_id=project_id,
            clip_id=clip_id,
            kind=kind,
            path=str(path),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO artifacts (id, project_id, clip_id, kind, path) VALUES (?, ?, ?, ?, ?)",
                (artifact.id, artifact.project_id, artifact.clip_id, artifact.kind, artifact.path),
            )
        return artifact

    def list_artifacts(self, project_id: str) -> list[Artifact]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, project_id, clip_id, kind, path FROM artifacts WHERE project_id = ? ORDER BY rowid",
                (project_id,),
            ).fetchall()
        return [Artifact(**dict(row)) for row in rows]

    @staticmethod
    def _track_from_row(row: Any) -> FaceTrackRecord:
        values = dict(row)
        values["samples"] = json.loads(values["samples"])
        return FaceTrackRecord(**values)
