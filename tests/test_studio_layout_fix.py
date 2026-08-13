from pathlib import Path

from fastapi.testclient import TestClient


def test_layout_fixed_studio_injects_the_desktop_grid_rule(tmp_path: Path) -> None:
    from autoclip.web.layout_fixed_studio import create_layout_fixed_studio

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><head></head><body><div id='root'></div></body></html>", encoding="utf-8")
    app = create_layout_fixed_studio(tmp_path / "projects", dist=dist)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert ".studio-grid{display:grid" in response.text
    app.state.runner.stop()
