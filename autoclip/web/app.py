"""FastAPI application for the local AutoClip studio."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, status

from autoclip.web.store import Project, ProjectStore


def create_app(library_root: Path | None = None) -> FastAPI:
    """Create a local-only AutoClip web application."""
    root = library_root or Path.home() / ".autoclip" / "projects"
    store = ProjectStore(root)
    app = FastAPI(title="AutoClip Local Studio", version="0.2.0")
    app.state.store = store

    @app.post("/api/projects/import", response_model=Project, status_code=status.HTTP_201_CREATED)
    async def import_project(file: UploadFile = File(...)) -> Project:
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File name required")

        suffix = Path(file.filename).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(dir=root, suffix=suffix, delete=False) as incoming:
            incoming_path = Path(incoming.name)
            while chunk := await file.read(1024 * 1024):
                incoming.write(chunk)

        try:
            return store.create_from_upload(incoming_path, original_name=file.filename)
        finally:
            incoming_path.unlink(missing_ok=True)

    @app.get("/api/projects/{project_id}", response_model=Project)
    def get_project(project_id: str) -> Project:
        try:
            return store.get_project(project_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return app


app = create_app()
