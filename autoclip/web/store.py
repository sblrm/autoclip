"""Durable local project storage for the AutoClip web application."""

from __future__ import annotations

import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Project:
    """A creator project stored on the local machine."""

    id: str
    title: str
    source_kind: str
    source_path: str
    status: str


class ProjectStore:
    """Store project metadata in SQLite and owned media beneath one root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "projects.sqlite3"
        self._initialize()

    def create_from_upload(self, source: Path, original_name: str) -> Project:
        """Copy an uploaded video into a new project owned by this library."""
        if not source.is_file():
            raise FileNotFoundError(f"Uploaded file not found: {source}")

        project_id = uuid.uuid4().hex
        project_root = self.root / project_id
        source_dir = project_root / "source"
        source_dir.mkdir(parents=True)
        extension = Path(original_name).suffix or source.suffix or ".mp4"
        destination = source_dir / f"source{extension.lower()}"
        shutil.copy2(source, destination)
        project = Project(
            id=project_id,
            title=Path(original_name).stem or "Untitled video",
            source_kind="upload",
            source_path=str(destination),
            status="draft",
        )
        self._save(project)
        return project

    def get_project(self, project_id: str) -> Project:
        """Load one project or raise KeyError when it does not exist."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, title, source_kind, source_path, status FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Project not found: {project_id}")
        return Project(**dict(row))

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )

    def _save(self, project: Project) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (id, title, source_kind, source_path, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.title,
                    project.source_kind,
                    project.source_path,
                    project.status,
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection
