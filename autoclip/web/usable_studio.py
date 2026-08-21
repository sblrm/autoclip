"""Setup-aware local studio server with guided, repairable prerequisites."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from autoclip.web.onboarding import OnboardingService
from autoclip.web.setup_manager import SetupManager
from autoclip.web.studio_server import JobResponse, _create_setup_job, create_studio_server


class SetupInstallRequest(BaseModel):
    component: str


def create_usable_studio(
    library_root: Path | None = None,
    *,
    dist: Path | None = None,
    setup_manager: SetupManager | Any | None = None,
    pipeline_factory: Any | None = None,
    tracking_factory: Any | None = None,
):
    """Extend the editor API with a guided local setup surface."""
    factories = {
        key: value
        for key, value in {
            "pipeline_factory": pipeline_factory,
            "tracking_factory": tracking_factory,
        }.items()
        if value is not None
    }
    app = create_studio_server(library_root, **factories)
    manager = setup_manager or app.state.setup_manager
    app.state.setup_manager = manager
    app.state.onboarding = OnboardingService(
        store=app.state.store,
        setup_manager=manager,
        acceleration_manager=app.state.acceleration_manager,
    )
    static_root = dist or Path(__file__).resolve().parent / "static"
    entry = static_root / "index.html"
    if not entry.is_file():
        raise FileNotFoundError(
            "Studio assets are missing; build frontend assets with `npm.cmd run build` from web/."
        )

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

    @app.get("/{path:path}", include_in_schema=False, response_class=HTMLResponse)
    def studio_route(path: str) -> HTMLResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        return HTMLResponse(entry.read_text(encoding="utf-8"))

    return app
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_usable_studio(), host="127.0.0.1", port=8765)
