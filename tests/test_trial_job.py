"""Unit tests for background trial job state."""

from __future__ import annotations

import threading
import unittest
from unittest import mock

from salary_pipeline.ingestion_upload.progress import TrialProgressReporter
from salary_pipeline.ingestion_upload.trial_job import TrialJob
from salary_pipeline.ingestion_upload.trial_run import TrialRunResult


class TrialJobStateTests(unittest.TestCase):
    def test_start_and_report_updates_snapshot(self) -> None:
        job = TrialJob()
        reporter = TrialProgressReporter(mode="full", start_time=0.0)
        job.start(reporter)

        with mock.patch(
            "salary_pipeline.ingestion_upload.progress.time.perf_counter",
            side_effect=[0.0, 50.0],
        ):
            snap = job.report_progress("check_cache", "检查 Hub 缓存…")

        view = job.read_view()
        self.assertEqual(view["status"], "running")
        self.assertIs(view["snapshot"], snap)
        self.assertAlmostEqual(view["percent"], 5.0)
        self.assertEqual(snap.stage_key, "check_cache")

    def test_mark_done_sets_result_and_percent(self) -> None:
        job = TrialJob()
        job.start(TrialProgressReporter(mode="incremental", start_time=0.0))
        result = TrialRunResult(month_id="2026-05", staging_dir=mock.Mock(), config_path=mock.Mock())

        with mock.patch(
            "salary_pipeline.ingestion_upload.progress.time.perf_counter",
            return_value=120.0,
        ):
            job.mark_done(result, completion_label="试算完成（增量）")

        view = job.read_view()
        self.assertEqual(view["status"], "done")
        self.assertIs(view["result"], result)
        self.assertEqual(view["percent"], 100.0)
        self.assertIsNotNone(view["snapshot"])

    def test_mark_done_with_errors_becomes_error_status(self) -> None:
        job = TrialJob()
        job.start()
        result = TrialRunResult(
            month_id="2026-05",
            staging_dir=mock.Mock(),
            config_path=mock.Mock(),
            errors=["绩效整理表未生成"],
        )
        job.mark_done(result, completion_label="试算完成")
        view = job.read_view()
        self.assertEqual(view["status"], "error")
        self.assertIn("绩效整理表未生成", view["error"] or "")

    def test_mark_exception_captures_traceback(self) -> None:
        job = TrialJob()
        job.start()
        try:
            raise ValueError("hub cache inspect failed")
        except ValueError as exc:
            job.mark_exception(exc)

        view = job.read_view()
        self.assertEqual(view["status"], "error")
        self.assertEqual(view["error"], "hub cache inspect failed")
        self.assertIn("ValueError", view["traceback_text"] or "")

    def test_concurrent_report_progress_is_thread_safe(self) -> None:
        job = TrialJob()
        job.start(TrialProgressReporter(mode="full", start_time=0.0))
        stages = [
            ("merge_topology", "合并…"),
            ("check_cache", "检查缓存…"),
            ("performance_sheet", "绩效…"),
        ]

        def worker(stage_key: str, label: str) -> None:
            job.report_progress(stage_key, label)

        threads = [
            threading.Thread(target=worker, args=stage)
            for stage in stages
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        view = job.read_view()
        self.assertEqual(view["status"], "running")
        self.assertIsNotNone(view["snapshot"])
        self.assertGreaterEqual(view["percent"], 0.0)

    def test_start_is_noop_while_already_running(self) -> None:
        job = TrialJob()
        first = TrialProgressReporter(mode="full", start_time=0.0)
        second = TrialProgressReporter(mode="incremental", start_time=99.0)
        job.start(first)
        job.report_progress("check_cache", "检查缓存…")
        job.start(second)

        view = job.read_view()
        self.assertEqual(view["status"], "running")
        self.assertIs(job.reporter, first)
        self.assertEqual(view["snapshot"].stage_key, "check_cache")

    def test_reset_clears_running_state(self) -> None:
        job = TrialJob()
        job.start()
        job.report_progress("check_cache", "检查缓存…")
        job.reset()
        view = job.read_view()
        self.assertEqual(view["status"], "idle")
        self.assertIsNone(view["snapshot"])
        self.assertFalse(job.is_running())


if __name__ == "__main__":
    unittest.main()
