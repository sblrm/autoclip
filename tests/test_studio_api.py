from __future__ import annotations

from fastapi.testclient import TestClient


def _import_project(client: TestClient) -> str:
    response = client.post(
        "/api/projects/import",
        files={"file": ("episode.mp4", b"video-bytes", "video/mp4")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_clip_edit_preview_and_approval_api_flow(tmp_path) -> None:
    from autoclip.web.studio import create_studio_app

    app = create_studio_app(library_root=tmp_path / "library")
    client = TestClient(app)
    project_id = _import_project(client)
    clip = app.state.store.create_clip(
        project_id,
        start_time=10.0,
        end_time=35.0,
        title="Original title",
        score=8,
        language="en",
    )

    edited = client.patch(
        f"/api/clips/{clip.id}",
        json={
            "start_time": 12.0,
            "end_time": 42.0,
            "title": "Edited title",
            "subtitle_config": {"uppercase": True},
        },
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Edited title"
    assert edited.json()["start_time"] == 12.0

    blocked = client.post(f"/api/clips/{clip.id}/approve")
    assert blocked.status_code == 409

    preview = client.post(f"/api/clips/{clip.id}/tracking-preview")
    assert preview.status_code == 202
    assert preview.json()["job_id"]
    app.state.store.mark_preview_ready(clip.id)

    approved = client.post(f"/api/clips/{clip.id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_project_detail_includes_persisted_clips_and_jobs(tmp_path) -> None:
    from autoclip.web.studio import create_studio_app

    app = create_studio_app(library_root=tmp_path / "library")
    client = TestClient(app)
    project_id = _import_project(client)
    app.state.store.create_clip(
        project_id,
        start_time=10.0,
        end_time=35.0,
        title="Candidate",
        score=8,
        language="en",
    )
    analysis = client.post(f"/api/projects/{project_id}/analyze")
    assert analysis.status_code == 202

    detail = client.get(f"/api/projects/{project_id}")
    assert detail.status_code == 200
    assert detail.json()["project"]["id"] == project_id
    assert [clip["title"] for clip in detail.json()["clips"]] == ["Candidate"]
    assert detail.json()["jobs"][0]["id"] == analysis.json()["job_id"]
