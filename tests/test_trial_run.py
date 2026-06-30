"""Tests for upload trial cache selection and topology freshness."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salary_pipeline.ingestion_upload.topology import (
    record_topology_workbook_fingerprint,
    topology_is_current,
    topology_source_fingerprint_path,
)
from salary_pipeline.ingestion_upload.trial_run import (
    bootstrap_staging_cache_from_formal,
    inspect_trial_cache,
    resolve_trial_from_stage,
)
from salary_pipeline.pipelines.run_cache import (
    compute_input_fingerprint,
    resolve_cache_dir,
    save_hub_snapshot,
    write_manifest,
)


def _trial_month_config(tmp: Path, month_id: str = "2026-05") -> dict:
    sales = tmp / "sales.xlsx"
    topo = tmp / "sales.topology.json"
    sales.write_bytes(b"sales-workbook-v1")
    topo.write_bytes(b"topology-v1")
    staging = tmp / "output" / month_id / ".staging"
    return {
        "month": month_id,
        "workbooks": {"sales": str(sales)},
        "topology": {"sales": str(topo)},
        "outputs": {
            "commission_summary_file": str(staging / "提成汇总.xlsx"),
            "cache_dir": str(staging / "cache"),
        },
        "performance_sheet": {"use_computed": True},
        "hub": {"bootstrap_from_golden": False},
    }


class TrialCacheSelectionTests(unittest.TestCase):
    def test_inspect_staging_cache_hit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = _trial_month_config(tmp)
            cache_dir = resolve_cache_dir(cfg)
            summary = __import__("pandas").DataFrame(
                {"店别": ["A"], "职务": ["X"], "姓名": ["Y"]}
            )
            artifacts = save_hub_snapshot(cache_dir, summary, __import__("pandas").DataFrame())
            fp = compute_input_fingerprint(cfg)
            write_manifest(cache_dir, fp, stage="hub", artifacts=artifacts)

            status = inspect_trial_cache(cfg)
            self.assertTrue(status.staging_valid)
            self.assertEqual(status.recommended_from_stage, "hub")
            self.assertEqual(status.cache_source, "staging")

    def test_resolve_from_stage_uses_staging(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = _trial_month_config(tmp)
            cache_dir = resolve_cache_dir(cfg)
            summary = __import__("pandas").DataFrame(
                {"店别": ["A"], "职务": ["X"], "姓名": ["Y"]}
            )
            artifacts = save_hub_snapshot(cache_dir, summary, __import__("pandas").DataFrame())
            fp = compute_input_fingerprint(cfg)
            write_manifest(cache_dir, fp, stage="hub", artifacts=artifacts)

            from_stage, source, _ = resolve_trial_from_stage(cfg)
            self.assertEqual(from_stage, "hub")
            self.assertEqual(source, "staging")

    def test_resolve_from_stage_full_when_no_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = _trial_month_config(Path(td))
            from_stage, source, msg = resolve_trial_from_stage(cfg)
            self.assertEqual(from_stage, "full")
            self.assertIsNone(source)
            self.assertIn("全量", msg)

    def test_inspect_formal_cache_when_staging_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = _trial_month_config(tmp)
            month_id = cfg["month"]
            fp = compute_input_fingerprint(cfg)
            summary = __import__("pandas").DataFrame(
                {"店别": ["A"], "职务": ["X"], "姓名": ["Y"]}
            )
            formal_cache = tmp / "output" / month_id / "cache"
            artifacts = save_hub_snapshot(formal_cache, summary, __import__("pandas").DataFrame())
            write_manifest(formal_cache, fp, stage="hub", artifacts=artifacts)

            with patch(
                "salary_pipeline.ingestion_upload.trial_run.output_month_dir",
                return_value=tmp / "output" / month_id,
            ):
                status = inspect_trial_cache(cfg)
                self.assertFalse(status.staging_valid)
                self.assertTrue(status.formal_valid)
                self.assertEqual(status.cache_source, "formal")

    def test_bootstrap_formal_cache_into_staging(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = _trial_month_config(tmp)
            month_id = cfg["month"]
            fp = compute_input_fingerprint(cfg)
            summary = __import__("pandas").DataFrame(
                {"店别": ["A"], "职务": ["X"], "姓名": ["Y"]}
            )

            formal_cache = tmp / "output" / month_id / "cache"
            artifacts = save_hub_snapshot(formal_cache, summary, __import__("pandas").DataFrame())
            write_manifest(formal_cache, fp, stage="hub", artifacts=artifacts)

            staging_cache = resolve_cache_dir(cfg)
            self.assertFalse((staging_cache / "run_manifest.json").exists())

            with patch(
                "salary_pipeline.ingestion_upload.trial_run.output_month_dir",
                return_value=tmp / "output" / month_id,
            ):
                from_stage, source, _ = resolve_trial_from_stage(cfg)
                self.assertEqual(from_stage, "hub")
                self.assertEqual(source, "formal")
                self.assertTrue((staging_cache / "run_manifest.json").exists())

    def test_cache_invalid_after_workbook_change(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = _trial_month_config(tmp)
            cache_dir = resolve_cache_dir(cfg)
            summary = __import__("pandas").DataFrame(
                {"店别": ["A"], "职务": ["X"], "姓名": ["Y"]}
            )
            artifacts = save_hub_snapshot(cache_dir, summary, __import__("pandas").DataFrame())
            fp = compute_input_fingerprint(cfg)
            write_manifest(cache_dir, fp, stage="hub", artifacts=artifacts)

            Path(cfg["workbooks"]["sales"]).write_bytes(b"sales-workbook-v2")
            status = inspect_trial_cache(cfg)
            self.assertFalse(status.staging_valid)
            self.assertEqual(status.recommended_from_stage, "full")


class TopologyFreshnessTests(unittest.TestCase):
    def test_topology_is_current_when_fingerprint_matches(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            wb = tmp / "book.xlsx"
            topo = tmp / "book.topology.json"
            wb.write_bytes(b"wb-content")
            topo.write_text("{}", encoding="utf-8")
            record_topology_workbook_fingerprint(wb, topo)
            self.assertTrue(topology_is_current(wb, str(topo)))

    def test_topology_stale_after_workbook_change(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            wb = tmp / "book.xlsx"
            topo = tmp / "book.topology.json"
            wb.write_bytes(b"wb-content")
            topo.write_text("{}", encoding="utf-8")
            record_topology_workbook_fingerprint(wb, topo)
            wb.write_bytes(b"wb-content-changed")
            self.assertFalse(topology_is_current(wb, str(topo)))

    def test_topology_missing_fingerprint_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            wb = tmp / "book.xlsx"
            topo = tmp / "book.topology.json"
            wb.write_bytes(b"wb")
            topo.write_text("{}", encoding="utf-8")
            self.assertFalse(topology_is_current(wb, str(topo)))
            self.assertFalse(topology_source_fingerprint_path(topo).exists())


if __name__ == "__main__":
    unittest.main()
