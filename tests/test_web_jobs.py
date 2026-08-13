from __future__ import annotations

import threading
from pathlib import Path


def test_serial_runner_executes_jobs_in_submission_order(tmp_path: Path) -> None:
    from autoclip.web.runtime_jobs import SerialJobRunner
    from autoclip.web.runtime_store import RuntimeStore

    source = tmp_path / "episode.mp4"
    source.write_bytes(b"video")
    store = RuntimeStore(tmp_path / "library")
    project = store.create_from_upload(source, original_name="Episode.mp4")
    first = store.create_job(project.id, "analysis", "Queued")
    second = store.create_job(project.id, "tracking_preview", "Queued")
    done = threading.Event()
    order: list[str] = []
    runner = SerialJobRunner(store)

    try:
        runner.submit(first, lambda report: order.append("first"))
        runner.submit(second, lambda report: (order.append("second"), done.set()))
        assert done.wait(timeout=2)
    finally:
        runner.stop()

    assert order == ["first", "second"]
    assert store.get_job(first.id).stage == "completed"
    assert store.get_job(second.id).stage == "completed"
