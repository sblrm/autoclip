"""Serve the production React studio and local FastAPI API from one origin."""

from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from autoclip.web.studio_server import create_studio_server


def create_local_studio(
    library_root: Path | None = None,
    *,
    dist: Path | None = None,
):
    """Create the localhost-only application after the Vite UI has been built."""
    app = create_studio_server(library_root)
    static_root = dist or Path(__file__).parents[2] / "web" / "dist"
    if not (static_root / "index.html").is_file():
        raise FileNotFoundError("Browser studio is not built. Run the AutoClip Studio launcher first.")
    app.mount("/", StaticFiles(directory=static_root, html=True), name="studio-ui")
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_local_studio(), host="127.0.0.1", port=8765)
