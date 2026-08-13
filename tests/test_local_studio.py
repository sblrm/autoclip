from pathlib import Path

from fastapi.testclient import TestClient


def test_local_studio_serves_the_built_browser_app_and_api(tmp_path: Path) -> None:
    from autoclip.web.local_studio import create_local_studio

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<main>AutoClip Studio</main>", encoding="utf-8")
    app = create_local_studio(tmp_path / "projects", dist=dist)
    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.get("/api/runtime-health").status_code == 200
    app.state.runner.stop()
