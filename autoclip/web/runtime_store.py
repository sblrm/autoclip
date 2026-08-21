"""Extended persistence used by the running local AutoClip studio."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, get_args
from urllib.parse import urlparse

from autoclip.web.acceleration import EncoderMode, ResolvedAcceleration, TrackerEngine
from autoclip.web.model_catalog import ModelPlan
from autoclip.web.studio_store import Job, StudioStore
from autoclip.web.store import Project


PerformanceProfile = Literal["auto", "cpu", "gpu"]


@dataclass(frozen=True)
class AppPreferences:
    locale: str = "id"
    last_project_id: str | None = None
    onboarding_complete: bool = False
    performance_profile: PerformanceProfile = "auto"
    updated_at: str = ""


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
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ProjectAcceleration:
    project_id: str
    tracker_engine: TrackerEngine
    encoder_mode: EncoderMode
    updated_at: str


@dataclass(frozen=True)
class ClipTrackingResolution:
    clip_id: str
    tracker_engine: TrackerEngine
    provider: str
    model_id: str | None
    trajectory_artifact_id: str | None
    verified_at: str


@dataclass(frozen=True)
class ModelAcknowledgement:
    plan_id: str
    source_url: str
    license: str
    acknowledged_at: str


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
                    path TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            artifact_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(artifacts)").fetchall()
            }
            if "metadata" not in artifact_columns:
                connection.execute(
                    "ALTER TABLE artifacts ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'",
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS project_acceleration (
                    project_id TEXT PRIMARY KEY,
                    tracker_engine TEXT NOT NULL,
                    encoder_mode TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clip_tracking_resolutions (
                    clip_id TEXT PRIMARY KEY,
                    tracker_engine TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model_id TEXT,
                    trajectory_artifact_id TEXT,
                    verified_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS model_acknowledgements (
                    plan_id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    license TEXT NOT NULL,
                    acknowledged_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_preferences (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    locale TEXT NOT NULL,
                    last_project_id TEXT,
                    onboarding_complete INTEGER NOT NULL,
                    performance_profile TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def get_app_preferences(self) -> AppPreferences:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_preferences (
                    id, locale, last_project_id, onboarding_complete,
                    performance_profile, updated_at
                ) VALUES (1, 'id', NULL, 0, 'auto', ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (_utc_now(),),
            )
            row = connection.execute(
                """
                SELECT locale, last_project_id, onboarding_complete,
                       performance_profile, updated_at
                FROM app_preferences WHERE id = 1
                """
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to initialize app preferences")
        return self._app_preferences_from_row(row)

    def update_app_preferences(self, **changes: object) -> AppPreferences:
        allowed = {"locale", "last_project_id", "onboarding_complete", "performance_profile"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unknown preference fields: {sorted(unknown)}")

        current = self.get_app_preferences()
        locale = changes.get("locale", current.locale)
        last_project_id = changes.get("last_project_id", current.last_project_id)
        onboarding_complete = changes.get("onboarding_complete", current.onboarding_complete)
        performance_profile = changes.get("performance_profile", current.performance_profile)

        if locale not in {"id", "en"}:
            raise ValueError("Invalid locale")
        if performance_profile not in {"auto", "cpu", "gpu"}:
            raise ValueError("Invalid performance_profile")
        if not isinstance(last_project_id, (str, type(None))):
            raise ValueError("Invalid last_project_id")
        if not isinstance(onboarding_complete, bool):
            raise ValueError("Invalid onboarding_complete")

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE app_preferences
                SET locale = ?, last_project_id = ?, onboarding_complete = ?,
                    performance_profile = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    locale,
                    last_project_id,
                    int(onboarding_complete),
                    performance_profile,
                    _utc_now(),
                ),
            )
        return self.get_app_preferences()

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

    def get_project_acceleration(self, project_id: str) -> ProjectAcceleration:
        self.get_project(project_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO project_acceleration (
                    project_id, tracker_engine, encoder_mode, updated_at
                ) VALUES (?, 'auto', 'auto', ?)
                ON CONFLICT(project_id) DO NOTHING
                """,
                (project_id, _utc_now()),
            )
            row = connection.execute(
                """
                SELECT project_id, tracker_engine, encoder_mode, updated_at
                FROM project_acceleration WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to initialize acceleration for project: {project_id}")
        return ProjectAcceleration(**dict(row))

    def set_project_acceleration(
        self,
        project_id: str,
        *,
        tracker_engine: TrackerEngine,
        encoder_mode: EncoderMode,
    ) -> ProjectAcceleration:
        self.get_project(project_id)
        _validate_engine_ids(tracker_engine, encoder_mode)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO project_acceleration (
                    project_id, tracker_engine, encoder_mode, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    tracker_engine = excluded.tracker_engine,
                    encoder_mode = excluded.encoder_mode,
                    updated_at = excluded.updated_at
                """,
                (project_id, tracker_engine, encoder_mode, _utc_now()),
            )
        return self.get_project_acceleration(project_id)

    def save_clip_tracking_resolution(
        self,
        clip_id: str,
        resolution: ResolvedAcceleration,
        trajectory_artifact_id: str | None,
    ) -> ClipTrackingResolution:
        clip = self.get_clip(clip_id)
        _validate_engine_ids(resolution.tracker_engine, resolution.encoder_mode)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if trajectory_artifact_id is not None:
                artifact = connection.execute(
                    "SELECT project_id, clip_id, kind FROM artifacts WHERE id = ?",
                    (trajectory_artifact_id,),
                ).fetchone()
                if artifact is None:
                    raise KeyError(f"Artifact not found: {trajectory_artifact_id}")
                if artifact["project_id"] != clip.project_id or artifact["clip_id"] != clip.id:
                    raise ValueError("Trajectory artifact does not belong to this clip")
                if artifact["kind"] != "tracking_trajectory":
                    raise ValueError("Artifact is not a tracking trajectory")

            connection.execute(
                """
                INSERT INTO clip_tracking_resolutions (
                    clip_id, tracker_engine, provider, model_id,
                    trajectory_artifact_id, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(clip_id) DO UPDATE SET
                    tracker_engine = excluded.tracker_engine,
                    provider = excluded.provider,
                    model_id = excluded.model_id,
                    trajectory_artifact_id = excluded.trajectory_artifact_id,
                    verified_at = excluded.verified_at
                """,
                (
                    clip.id,
                    resolution.tracker_engine,
                    resolution.provider,
                    resolution.model_id,
                    trajectory_artifact_id,
                    _utc_now(),
                ),
            )
            row = connection.execute(
                """
                SELECT clip_id, tracker_engine, provider, model_id,
                       trajectory_artifact_id, verified_at
                FROM clip_tracking_resolutions WHERE clip_id = ?
                """,
                (clip.id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to save tracking resolution for clip: {clip.id}")
        return ClipTrackingResolution(**dict(row))

    def get_clip_tracking_resolution(self, clip_id: str) -> ClipTrackingResolution | None:
        self.get_clip(clip_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT clip_id, tracker_engine, provider, model_id,
                       trajectory_artifact_id, verified_at
                FROM clip_tracking_resolutions WHERE clip_id = ?
                """,
                (clip_id,),
            ).fetchone()
        return None if row is None else ClipTrackingResolution(**dict(row))

    def save_model_acknowledgement(self, plan: ModelPlan) -> ModelAcknowledgement:
        acknowledged_at = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO model_acknowledgements (
                    plan_id, source_url, license, acknowledged_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    source_url = excluded.source_url,
                    license = excluded.license,
                    acknowledged_at = excluded.acknowledged_at
                """,
                (plan.id, plan.source_url, plan.license, acknowledged_at),
            )
        return ModelAcknowledgement(plan.id, plan.source_url, plan.license, acknowledged_at)

    def save_artifact(
        self,
        project_id: str,
        kind: str,
        path: Path,
        clip_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Artifact:
        self.get_project(project_id)
        if clip_id is not None:
            clip = self.get_clip(clip_id)
            if clip.project_id != project_id:
                raise ValueError("Artifact clip does not belong to this project")
        stored_metadata = _metadata_json(metadata)
        artifact = Artifact(
            id=__import__("uuid").uuid4().hex,
            project_id=project_id,
            clip_id=clip_id,
            kind=kind,
            path=str(path),
            metadata=json.loads(stored_metadata),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts (id, project_id, clip_id, kind, path, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.id,
                    artifact.project_id,
                    artifact.clip_id,
                    artifact.kind,
                    artifact.path,
                    stored_metadata,
                ),
            )
        return artifact

    def list_artifacts(self, project_id: str) -> list[Artifact]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, clip_id, kind, path, metadata
                FROM artifacts WHERE project_id = ? ORDER BY rowid
                """,
                (project_id,),
            ).fetchall()
        return [self._artifact_from_row(row) for row in rows]

    @staticmethod
    def _track_from_row(row: Any) -> FaceTrackRecord:
        values = dict(row)
        values["samples"] = json.loads(values["samples"])
        return FaceTrackRecord(**values)

    @staticmethod
    def _artifact_from_row(row: Any) -> Artifact:
        values = dict(row)
        values["metadata"] = json.loads(values["metadata"])
        return Artifact(**values)

    @staticmethod
    def _app_preferences_from_row(row: Any) -> AppPreferences:
        values = dict(row)
        values["onboarding_complete"] = bool(values["onboarding_complete"])
        return AppPreferences(**values)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_engine_ids(tracker_engine: str, encoder_mode: str) -> None:
    if tracker_engine not in get_args(TrackerEngine):
        raise ValueError(f"Unknown tracker engine: {tracker_engine}")
    if encoder_mode not in get_args(EncoderMode):
        raise ValueError(f"Unknown encoder mode: {encoder_mode}")


def _metadata_json(metadata: Mapping[str, Any] | None) -> str:
    return json.dumps(dict(metadata or {}), sort_keys=True)
