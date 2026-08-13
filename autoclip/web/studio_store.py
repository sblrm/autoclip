"""Project, clip, tracking, and job records for the local web studio."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from autoclip.web.store import Project, ProjectStore


@dataclass(frozen=True)
class StudioClip:
    id: str
    project_id: str
    start_time: float
    end_time: float
    title: str
    score: int
    language: str
    status: str
    subtitle_config: dict[str, Any]
    selected_face_track_id: str | None
    tracking_status: str


@dataclass(frozen=True)
class Job:
    id: str
    project_id: str
    kind: str
    stage: str
    progress: float
    message: str
    error: str | None


class StudioStore(ProjectStore):
    """Extends project storage with creator-editing and background-job state."""

    def _initialize(self) -> None:
        super()._initialize()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clips (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    title TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    language TEXT NOT NULL,
                    status TEXT NOT NULL,
                    subtitle_config TEXT NOT NULL,
                    selected_face_track_id TEXT,
                    tracking_status TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress REAL NOT NULL,
                    message TEXT NOT NULL,
                    error TEXT
                )
                """
            )

    def create_clip(
        self,
        project_id: str,
        *,
        start_time: float,
        end_time: float,
        title: str,
        score: int,
        language: str,
    ) -> StudioClip:
        self.get_project(project_id)
        self._validate_range(start_time, end_time)
        clip = StudioClip(
            id=uuid.uuid4().hex,
            project_id=project_id,
            start_time=start_time,
            end_time=end_time,
            title=title.strip() or "Untitled clip",
            score=score,
            language=language,
            status="draft",
            subtitle_config={},
            selected_face_track_id=None,
            tracking_status="not_requested",
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO clips (
                    id, project_id, start_time, end_time, title, score, language, status,
                    subtitle_config, selected_face_track_id, tracking_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clip.id,
                    clip.project_id,
                    clip.start_time,
                    clip.end_time,
                    clip.title,
                    clip.score,
                    clip.language,
                    clip.status,
                    json.dumps(clip.subtitle_config),
                    clip.selected_face_track_id,
                    clip.tracking_status,
                ),
            )
        return clip

    def list_clips(self, project_id: str) -> list[StudioClip]:
        self.get_project(project_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, start_time, end_time, title, score, language, status,
                       subtitle_config, selected_face_track_id, tracking_status
                FROM clips WHERE project_id = ? ORDER BY start_time
                """,
                (project_id,),
            ).fetchall()
        return [self._clip_from_row(row) for row in rows]

    def get_clip(self, clip_id: str) -> StudioClip:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, start_time, end_time, title, score, language, status,
                       subtitle_config, selected_face_track_id, tracking_status
                FROM clips WHERE id = ?
                """,
                (clip_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Clip not found: {clip_id}")
        return self._clip_from_row(row)

    def update_clip(self, clip_id: str, **changes: Any) -> StudioClip:
        current = self.get_clip(clip_id)
        values = {
            "start_time": changes.get("start_time", current.start_time),
            "end_time": changes.get("end_time", current.end_time),
            "title": changes.get("title", current.title),
            "subtitle_config": changes.get("subtitle_config", current.subtitle_config),
            "selected_face_track_id": changes.get("selected_face_track_id", current.selected_face_track_id),
            "tracking_status": changes.get("tracking_status", current.tracking_status),
        }
        self._validate_range(float(values["start_time"]), float(values["end_time"]))
        values["title"] = str(values["title"]).strip() or "Untitled clip"
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE clips
                SET start_time = ?, end_time = ?, title = ?, subtitle_config = ?,
                    selected_face_track_id = ?, tracking_status = ?
                WHERE id = ?
                """,
                (
                    values["start_time"],
                    values["end_time"],
                    values["title"],
                    json.dumps(values["subtitle_config"]),
                    values["selected_face_track_id"],
                    values["tracking_status"],
                    clip_id,
                ),
            )
        return self.get_clip(clip_id)

    def mark_preview_ready(self, clip_id: str) -> StudioClip:
        return self._set_clip_status(clip_id, "preview_ready")

    def approve_clip(self, clip_id: str) -> StudioClip:
        clip = self.get_clip(clip_id)
        if clip.status != "preview_ready":
            raise ValueError("A tracking preview must be approved before export")
        return self._set_clip_status(clip_id, "approved")

    def create_job(self, project_id: str, kind: str, message: str) -> Job:
        self.get_project(project_id)
        job = Job(
            id=uuid.uuid4().hex,
            project_id=project_id,
            kind=kind,
            stage="queued",
            progress=0.0,
            message=message,
            error=None,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (id, project_id, kind, stage, progress, message, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job.id, job.project_id, job.kind, job.stage, job.progress, job.message, job.error),
            )
        return job

    def update_job(
        self,
        job_id: str,
        *,
        stage: str,
        progress: float,
        message: str,
        error: str | None = None,
    ) -> Job:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET stage = ?, progress = ?, message = ?, error = ? WHERE id = ?
                """,
                (stage, max(0.0, min(1.0, progress)), message, error, job_id),
            )
            row = connection.execute(
                "SELECT id, project_id, kind, stage, progress, message, error FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        return Job(**dict(row))

    def get_job(self, job_id: str) -> Job:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, project_id, kind, stage, progress, message, error FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        return Job(**dict(row))

    def _set_clip_status(self, clip_id: str, status: str) -> StudioClip:
        self.get_clip(clip_id)
        with self._connect() as connection:
            connection.execute("UPDATE clips SET status = ? WHERE id = ?", (status, clip_id))
        return self.get_clip(clip_id)

    @staticmethod
    def _validate_range(start_time: float, end_time: float) -> None:
        if start_time < 0 or end_time <= start_time:
            raise ValueError("Clip end time must be greater than start time")

    @staticmethod
    def _clip_from_row(row: Any) -> StudioClip:
        values = dict(row)
        values["subtitle_config"] = json.loads(values["subtitle_config"])
        return StudioClip(**values)
