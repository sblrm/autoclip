"""Local studio server with the corrected desktop editor grid layout."""

from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from autoclip.web.studio_server import create_studio_server

_LAYOUT_FIX = "<style id=\"autoclip-layout-fix\">.studio-grid{display:grid}</style>"


def create_layout_fixed_studio(
    library_root: Path | None = None,
    *,
    dist: Path | None = None,
):
    """Serve the built Vite app with its desktop grid layout explicitly enabled."""
    app = create_studio_server(library_root)
    static_root = dist or Path(__file__).parents[2] / "web" / "dist"
    index_path = static_root / "index.html"
    if not index_path.is_file():
        raise FileNotFoundError("Browser studio is not built. Run the launcher first.")

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def studio_index() -> HTMLResponse:
        html = index_path.read_text(encoding="utf-8")
        return HTMLResponse(html.replace("</head>", f"{_LAYOUT_FIX}</head>"))

    app.mount("/assets", StaticFiles(directory=static_root / "assets"), name="studio-assets")
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_layout_fixed_studio(), host="127.0.0.1", port=8765)
