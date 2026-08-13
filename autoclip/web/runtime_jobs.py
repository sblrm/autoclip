"""Single-worker local job queue for CPU/GPU-heavy creator tasks."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable

from autoclip.web.runtime_store import RuntimeStore
from autoclip.web.studio_store import Job

ProgressReporter = Callable[[str, float, str], None]
JobTask = Callable[[ProgressReporter], None]


class SerialJobRunner:
    """Run one local processing task at a time and persist each state change."""

    def __init__(self, store: RuntimeStore) -> None:
        self.store = store
        self._queue: queue.Queue[tuple[Job, JobTask] | None] = queue.Queue()
        self._worker = threading.Thread(target=self._work, name="autoclip-web-worker", daemon=True)
        self._worker.start()

    def submit(self, job: Job, task: JobTask) -> None:
        self._queue.put((job, task))

    def stop(self) -> None:
        self._queue.put(None)
        self._worker.join(timeout=2)

    def _work(self) -> None:
        while item := self._queue.get():
            job, task = item
            self.store.update_job(job.id, stage="running", progress=0.01, message="Processing locally")
            try:
                task(lambda stage, progress, message: self.store.update_job(
                    job.id,
                    stage=stage,
                    progress=progress,
                    message=message,
                ))
            except Exception as error:  # Persist errors for UI retry, then continue queue.
                self.store.update_job(
                    job.id,
                    stage="failed",
                    progress=1.0,
                    message="Processing failed",
                    error=str(error),
                )
            else:
                self.store.update_job(job.id, stage="completed", progress=1.0, message="Completed")
