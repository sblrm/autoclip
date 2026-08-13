from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient


def test_studio_api_locks_a_project_face_track_and_runs_preview_job(tmp_path: Path) -> None:
    from autoclip.web.full_store import FullStudioStore
    from autoclip.web.studio_server import create_studio_server

    class FakePipeline:
        def __init__(self, _store: FullStudioStore) -> None:
            pass

        def analyze(self, _project_id: str, _report: object) -> None:
            pass

    class FakeTracking:
        def __init__(self, store: FullStudioStore) -> None:
            self.store = store
            self.previewed: list[str] = []

        def render_preview(self, clip_id: str, report: object) -> None:
            self.previewed.append(clip_id)
            self.store.mark_preview_ready(clip_id)

        def export_approved(self, _clip_id: str, _report: object) -> None:
            pass

    app = create_studio_server(
        tmp_path / "library",
        pipeline_factory=FakePipeline,
        tracking_factory=FakeTracking,
    )
    client = TestClient(app)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    response = client.post("/api/projects/import", files={"file": ("source.mp4", source.read_bytes(), "video/mp4")})
    assert response.status_code == 201
    project = response.json()
    clip = app.state.store.create_clip(
        project["id"], start_time=1, end_time=5, title="Moment", score=91, language="id"
    )
    track = app.state.store.save_face_track(
        clip.id,
        label="Subject 1",
        confidence=0.9,
        samples=[{"cx": 0.4, "cy": 0.5, "confidence": 0.9}],
    )

    selected = client.patch(f"/api/clips/{clip.id}", json={"selected_face_track_id": track.id})
    assert selected.status_code == 200
    assert selected.json()["selected_face_track_id"] == track.id

    queued = client.post(f"/api/clips/{clip.id}/tracking-preview")
    assert queued.status_code == 202
    job_id = queued.json()["job_id"]
    for _ in range(30):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["stage"] == "completed":
            break
        time.sleep(0.02)
    assert job["stage"] == "completed"
    assert app.state.tracking.previewed == [clip.id]
    app.state.runner.stop()


def test_studio_api_rejects_cross_clip_face_selection_and_non_video_import(tmp_path: Path) -> None:
    from autoclip.web.studio_server import create_studio_server

    app = create_studio_server(tmp_path / "library")
    client = TestClient(app)
    rejected = client.post("/api/projects/import", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert rejected.status_code == 422

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    project = client.post("/api/projects/import", files={"file": ("source.mp4", b"video", "video/mp4")}).json()
    first = app.state.store.create_clip(project["id"], start_time=0, end_time=1, title="First", score=80, language="id")
    second = app.state.store.create_clip(project["id"], start_time=1, end_time=2, title="Second", score=80, language="id")
    track = app.state.store.save_face_track(second.id, label="Subject 1", confidence=0.8, samples=[])

    response = client.patch(f"/api/clips/{first.id}", json={"selected_face_track_id": track.id})
    assert response.status_code == 422
    app.state.runner.stop()
