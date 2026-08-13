from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_analysis_request_runs_through_the_local_serial_worker(tmp_path) -> None:
    from autoclip.web.runtime import create_runtime_app

    calls: list[str] = []

    class Pipeline:
        def analyze(self, project_id, report) -> None:
            report("analyzing", 0.5, "Fake analysis")
            calls.append(project_id)

    app = create_runtime_app(library_root=tmp_path / "library", pipeline_factory=lambda _: Pipeline())
    client = TestClient(app)
    imported = client.post(
        "/api/projects/import",
        files={"file": ("episode.mp4", b"video-bytes", "video/mp4")},
    )
    project_id = imported.json()["id"]
    queued = client.post(f"/api/projects/{project_id}/analyze")

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{queued.json()['job_id']}").json()
        if job["stage"] == "completed":
            break
        time.sleep(0.02)
    app.state.runner.stop()

    assert calls == [project_id]
    assert job["stage"] == "completed"
