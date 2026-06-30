"""Tests for unified salary summary."""

from __future__ import annotations

import unittest

from salary_pipeline.app._salary_summary import build_salary_summary, family_pass_counts
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config


GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class SalarySummaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))

    def test_covers_all_families(self) -> None:
        frame = build_salary_summary(self.loader)
        families = set(frame["岗位族"].unique())
        self.assertEqual(
            families,
            {"新媒体", "邀约专员", "客户专员", "直营店经理", "招聘"},
        )

    def test_all_rows_match_golden(self) -> None:
        frame = build_salary_summary(self.loader)
        mismatches = frame[frame["一致"] == "✗"]
        self.assertTrue(mismatches.empty, f"mismatches:\n{mismatches}")

    def test_family_stats(self) -> None:
        frame = build_salary_summary(self.loader)
        stats = family_pass_counts(frame)
        self.assertEqual(len(stats), 5)
        self.assertTrue((stats["不一致"] == 0).all())


if __name__ == "__main__":
    unittest.main()
