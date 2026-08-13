"""Setup-aware local studio server with guided, repairable prerequisites."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from autoclip.web.setup_manager import SetupManager
from autoclip.web.studio_server import JobResponse, create_studio_server
from autoclip.web.studio_store import Job


class SetupInstallRequest(BaseModel):
    component: str


def create_usable_studio(
    library_root: Path | None = None,
    *,
    dist: Path | None = None,
    setup_manager: SetupManager | Any | None = None,
):
    """Extend the editor API with a guided local setup surface."""
    app = create_studio_server(library_root)
    manager = setup_manager or SetupManager()
    app.state.setup_manager = manager
    static_root = dist or Path(__file__).parents[2] / "web" / "dist"
    entry = static_root / "ux.html"
    if not entry.is_file():
        raise FileNotFoundError("Setup studio is not built. Run autoclip-setup-studio.bat first.")

    @app.get("/api/setup/status")
    def setup_status() -> dict[str, object]:
        return manager.status().payload()

    @app.post("/api/setup/recheck")
    def recheck_setup() -> dict[str, object]:
        return manager.status().payload()

    @app.post("/api/setup/install", response_model=JobResponse, status_code=202)
    def install_setup_component(body: SetupInstallRequest) -> JobResponse:
        try:
            manager.install_plan(body.component)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        job = _create_setup_job(app.state.store, body.component)
        app.state.runner.submit(job, lambda report: manager.install(body.component, report))
        return JobResponse(job_id=job.id)

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def setup_index() -> HTMLResponse:
        return HTMLResponse(entry.read_text(encoding="utf-8"))

    assets = static_root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="setup-assets")
    return app


def _create_setup_job(store: Any, component: str) -> Job:
    """Use existing durable serial queue without creating a fake media project."""
    job = Job(
        id=uuid.uuid4().hex,
        project_id="__setup__",
        kind=f"setup:{component}",
        stage="queued",
        progress=0.0,
        message=f"Queued setup for {component}",
        error=None,
    )
    with store._connect() as connection:
        connection.execute(
            """
            INSERT INTO jobs (id, project_id, kind, stage, progress, message, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job.id, job.project_id, job.kind, job.stage, job.progress, job.message, job.error),
        )
    return job


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_usable_studio(), host="127.0.0.1", port=8765)
