"""Unit tests for trial progress ETA helpers."""

from __future__ import annotations

import unittest
from unittest import mock

from salary_pipeline.ingestion_upload.progress import (
    FULL_STAGE_WEIGHTS,
    INCREMENTAL_STAGE_WEIGHTS,
    TrialProgressReporter,
    completed_fraction,
    estimate_remaining_seconds,
    format_duration,
)


class TrialProgressEtaTests(unittest.TestCase):
    def test_full_stage_weights_sum_to_100(self) -> None:
        total = sum(w for w, _ in FULL_STAGE_WEIGHTS.values())
        self.assertAlmostEqual(total, 100.0)

    def test_incremental_stage_weights_sum_to_100(self) -> None:
        total = sum(w for w, _ in INCREMENTAL_STAGE_WEIGHTS.values())
        self.assertAlmostEqual(total, 100.0)

    def test_completed_fraction_at_stage_start(self) -> None:
        # Entering hub_formula: merge + cache + performance done = 5+2+25 = 32%
        frac = completed_fraction("full", "hub_formula", stage_started=True)
        self.assertAlmostEqual(frac, 0.32)

    def test_completed_fraction_after_stage(self) -> None:
        frac = completed_fraction("full", "hub_formula", stage_started=False)
        self.assertAlmostEqual(frac, 0.77)

    def test_estimate_remaining_uses_elapsed_ratio(self) -> None:
        # 32% done in 320s -> ~1000s total -> ~680s remaining
        remaining = estimate_remaining_seconds(320.0, 0.32, "full")
        self.assertAlmostEqual(remaining, 680.0, delta=1.0)

    def test_estimate_remaining_default_when_no_progress(self) -> None:
        remaining = estimate_remaining_seconds(0.0, 0.0, "full")
        self.assertAlmostEqual(remaining, 600.0)  # 10 min default

    def test_estimate_remaining_zero_when_done(self) -> None:
        self.assertEqual(estimate_remaining_seconds(500.0, 1.0, "full"), 0.0)

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(125), "2m 5s")
        self.assertEqual(format_duration(45), "45s")

    def test_reporter_advances_percent(self) -> None:
        reporter = TrialProgressReporter(mode="full", start_time=0.0)
        with mock.patch(
            "salary_pipeline.ingestion_upload.progress.time.perf_counter",
            side_effect=[0.0, 100.0, 200.0],
        ):
            snap1 = reporter.report("merge_topology", "合并…")
            self.assertAlmostEqual(snap1.percent, 0.0)
            snap2 = reporter.report("check_cache", "检查缓存…")
            self.assertAlmostEqual(snap2.percent, 5.0)
            self.assertGreater(snap2.elapsed_seconds, 0)

    def test_reporter_mode_switch(self) -> None:
        reporter = TrialProgressReporter(mode="full")
        reporter.set_mode("incremental")
        frac = completed_fraction("incremental", "overlay", stage_started=True)
        self.assertAlmostEqual(frac, 0.20)  # 8+4+8 = 20%


if __name__ == "__main__":
    unittest.main()
