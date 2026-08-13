from __future__ import annotations

from fastapi.testclient import TestClient


def test_import_endpoint_creates_a_project_owned_video(tmp_path) -> None:
    from autoclip.web.app import create_app

    client = TestClient(create_app(library_root=tmp_path / "library"))

    response = client.post(
        "/api/projects/import",
        files={"file": ("episode.mp4", b"video-bytes", "video/mp4")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "episode"
    assert body["source_kind"] == "upload"
    project = client.get(f"/api/projects/{body['id']}")
    assert project.status_code == 200
    assert project.json() == body
