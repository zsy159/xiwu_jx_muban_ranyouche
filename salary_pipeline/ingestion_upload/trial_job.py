"""Background trial job state for upload UI progress polling."""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from salary_pipeline.ingestion_upload.progress import (
    TrialProgressReporter,
    TrialProgressSnapshot,
)

if TYPE_CHECKING:
    from salary_pipeline.ingestion_upload.trial_run import TrialRunResult

TrialJobStatus = Literal["idle", "running", "done", "error"]


@dataclass
class TrialJob:
    """Thread-safe trial compute job tracked in Streamlit session_state."""

    status: TrialJobStatus = "idle"
    reporter: TrialProgressReporter | None = None
    snapshot: TrialProgressSnapshot | None = None
    percent: float = 0.0
    result: TrialRunResult | None = None
    error: str | None = None
    traceback_text: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def start(self, reporter: TrialProgressReporter | None = None) -> None:
        with self._lock:
            if self.status == "running":
                return
            self.status = "running"
            self.reporter = reporter or TrialProgressReporter(mode="full")
            self.snapshot = None
            self.percent = 0.0
            self.result = None
            self.error = None
            self.traceback_text = None

    def report_progress(self, stage_key: str, label: str) -> TrialProgressSnapshot:
        with self._lock:
            if self.reporter is None:
                raise RuntimeError("trial job reporter not initialized")
            snap = self.reporter.report(stage_key, label)
            self.snapshot = snap
            self.percent = snap.percent
            return snap

    def mark_done(self, result: TrialRunResult, *, completion_label: str) -> None:
        with self._lock:
            self.result = result
            if result.errors:
                self.status = "error"
                self.error = "; ".join(result.errors)
                self.traceback_text = None
            else:
                self.status = "done"
                self.error = None
                self.traceback_text = None
                if self.reporter is not None:
                    self.snapshot = self.reporter.complete(completion_label)
                    self.percent = 100.0

    def mark_exception(self, exc: BaseException) -> None:
        with self._lock:
            self.status = "error"
            self.error = str(exc)
            self.traceback_text = traceback.format_exc()
            self.result = None

    def reset(self) -> None:
        with self._lock:
            self.status = "idle"
            self.reporter = None
            self.snapshot = None
            self.percent = 0.0
            self.result = None
            self.error = None
            self.traceback_text = None

    def is_running(self) -> bool:
        with self._lock:
            return self.status == "running"

    def read_view(self) -> dict:
        """Snapshot fields safe for UI rendering on the main thread."""
        with self._lock:
            return {
                "status": self.status,
                "snapshot": self.snapshot,
                "percent": self.percent,
                "result": self.result,
                "error": self.error,
                "traceback_text": self.traceback_text,
            }
