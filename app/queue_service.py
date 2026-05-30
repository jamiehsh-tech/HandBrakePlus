"""Sequential job queue for HandBrake batch encoding."""

from __future__ import annotations

import threading
from collections import deque
from typing import Callable

from .handbrake_cli import HandBrakeRunner, StopRequestedError
from .models import EncodeJob, JobProgress


class SequentialJobQueue:
    """Execute encode jobs one after another in a background thread."""

    def __init__(self, runner: HandBrakeRunner) -> None:
        self.runner = runner
        self._jobs: deque[EncodeJob] = deque()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stop_requested = threading.Event()

    def add_jobs(self, jobs: list[EncodeJob]) -> None:
        with self._lock:
            self._jobs.extend(jobs)

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()

    def request_stop(self) -> None:
        self._stop_requested.set()
        self.runner.request_stop()

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def start(self, progress_callback: Callable[[JobProgress], None]) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_requested.clear()
        self._worker = threading.Thread(
            target=self._run_worker,
            args=(progress_callback,),
            daemon=True,
        )
        self._worker.start()

    def _run_worker(self, progress_callback: Callable[[JobProgress], None]) -> None:
        total_jobs = len(self._jobs)
        completed_jobs = 0
        while True:
            if self._stop_requested.is_set():
                progress_callback(
                    JobProgress(
                        status="cancelled",
                        message="queue stopped",
                        completed_jobs=completed_jobs,
                        total_jobs=total_jobs,
                    )
                )
                return
            with self._lock:
                if not self._jobs:
                    break
                job = self._jobs.popleft()
            try:
                progress_callback(
                    JobProgress(
                        status="running",
                        message=f"encoding {job.display_name}",
                        current_job=job.display_name,
                        completed_jobs=completed_jobs,
                        total_jobs=total_jobs,
                    )
                )
                self.runner.run_job(job, progress_callback)
                completed_jobs += 1
            except StopRequestedError:
                progress_callback(
                    JobProgress(
                        status="cancelled",
                        message="queue stopped",
                        current_job=job.display_name,
                        completed_jobs=completed_jobs,
                        total_jobs=total_jobs,
                    )
                )
                return
            except Exception as exc:
                progress_callback(
                    JobProgress(
                        status="failed",
                        message=str(exc),
                        current_job=job.display_name,
                        completed_jobs=completed_jobs,
                        total_jobs=total_jobs,
                        extra={"job": job.display_name},
                    )
                )
                completed_jobs += 1
        progress_callback(
            JobProgress(
                status="idle",
                message="queue finished",
                completed_jobs=completed_jobs,
                total_jobs=total_jobs,
            )
        )
