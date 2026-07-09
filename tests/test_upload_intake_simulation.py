"""Integration tests: local raw workbook intake against real 2026-05 sales file."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from salary_pipeline.ingestion_upload.file_intake import (
    SheetMatchStatus,
    discover_local_raw_workbooks,
    intake_local_raw,
    scan_workbook_sheets,
)
from salary_pipeline.ingestion_upload.manifest import (
    FAMILY_SALES,
    group_manifest_by_family,
    is_mandatory_input,
    required_input_sheets,
)
from salary_pipeline.ingestion_upload.sheet_merge import build_consolidated_workbook
from salary_pipeline.paths import PROJECT_ROOT

GOLDEN_SALES = (
    PROJECT_ROOT
    / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"
)
GOLDEN_RULES = PROJECT_ROOT / "data/raw/2026-05/提成依据.xlsx"


@unittest.skipUnless(GOLDEN_SALES.exists(), "golden sales workbook missing")
class UploadIntakeSimulationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_discover_local_workbooks_2026_05(self) -> None:
        sales, rules = discover_local_raw_workbooks("2026-05")
        self.assertIsNotNone(sales)
        self.assertEqual(sales, GOLDEN_SALES)
        self.assertIsNotNone(rules)
        self.assertEqual(rules, GOLDEN_RULES)

    def test_sales_workbook_all_required_sheets_ready(self) -> None:
        intake = intake_local_raw(
            "2026-05",
            staging_root=self.tmp / "staging",
        )
        self.assertFalse(intake.errors, msg="; ".join(intake.errors))
        self.assertTrue(intake.all_required_ready)
        self.assertIsNone(intake.rules_workbook)

        required = [m for m in intake.matches if is_mandatory_input(m.required)]
        ready = [m for m in required if m.status == SheetMatchStatus.READY]
        self.assertEqual(len(ready), len(required))
        self.assertEqual(len(required), len(required_input_sheets()))

        self.assertIsNotNone(intake.sales_workbook)
        self.assertEqual(intake.sales_workbook.name, GOLDEN_SALES.name)
        staged = intake.staging_dir / "uploads" / GOLDEN_SALES.name
        self.assertTrue(staged.exists(), "sales workbook should be copied to staging")

    def test_sales_workbook_covers_role_families(self) -> None:
        intake = intake_local_raw(
            "2026-05",
            staging_root=self.tmp / "staging2",
        )
        match_by_name = {m.required.name: m for m in intake.matches}
        role_sheets = {
            "新媒体": "新媒体",
            "邀约专员提成": "邀约专员",
            "客户部提成": "客户专员",
            "直营店经理提成 (财务)": "直营店经理",
            "招聘": "招聘",
        }
        for sheet_name in role_sheets:
            match = match_by_name[sheet_name]
            self.assertEqual(
                match.status,
                SheetMatchStatus.READY,
                msg=f"{sheet_name} should be ready",
            )
            self.assertIn(GOLDEN_SALES.name, match.sources)

    def test_sales_workbook_scans_many_sheets(self) -> None:
        sheets = scan_workbook_sheets(GOLDEN_SALES)
        self.assertGreaterEqual(len(sheets), 70)

    def test_include_rules_causes_role_family_conflicts(self) -> None:
        if not GOLDEN_RULES.exists():
            self.skipTest("rules workbook missing")
        intake = intake_local_raw(
            "2026-05",
            include_rules_workbook=True,
            staging_root=self.tmp / "staging3",
        )
        self.assertFalse(intake.errors)
        self.assertIsNotNone(intake.rules_workbook)
        conflict_names = set(intake.conflict_sheets)
        self.assertTrue(
            conflict_names
            & {"新媒体", "邀约专员提成", "客户部提成", "直营店经理提成 (财务)"}
        )
        # Role-family sheets are optional; mandatory sales inputs can still be ready.
        self.assertTrue(intake.all_required_ready)
        self.assertFalse(intake.can_proceed())
        sales_name = GOLDEN_SALES.name
        resolutions = {
            "新媒体": sales_name,
            "邀约专员提成": sales_name,
            "客户部提成": sales_name,
            "直营店经理提成 (财务)": sales_name,
        }
        self.assertTrue(intake.can_proceed(resolutions))
        self.assertEqual(intake.proceed_blockers(resolutions), [])
        self.assertFalse(intake.can_proceed())
        sales_name = GOLDEN_SALES.name
        rules_name = GOLDEN_RULES.name
        resolutions = {
            "新媒体": sales_name,
            "邀约专员提成": sales_name,
            "客户部提成": sales_name,
            "直营店经理提成 (财务)": sales_name,
        }
        self.assertTrue(intake.can_proceed(resolutions))
        self.assertEqual(intake.proceed_blockers(resolutions), [])

    def test_grouped_manifest_sales_family_present(self) -> None:
        intake = intake_local_raw(
            "2026-05",
            staging_root=self.tmp / "staging4",
        )
        match_by_name = {m.required.name: m for m in intake.matches}
        groups = dict(group_manifest_by_family())
        sales_sheets = [s for s in groups[FAMILY_SALES] if is_mandatory_input(s)]
        missing_in_sales = [
            s.name
            for s in sales_sheets
            if match_by_name[s.name].status != SheetMatchStatus.READY
        ]
        self.assertEqual(missing_in_sales, [])

    def test_consolidated_merge_preserves_sales_task_values(self) -> None:
        import pandas as pd

        intake = intake_local_raw(
            "2026-05",
            staging_root=self.tmp / "staging5",
        )
        self.assertFalse(intake.errors)
        out = self.tmp / "merged.xlsx"
        build_consolidated_workbook(intake, out)
        self.assertLess(
            out.stat().st_size,
            GOLDEN_SALES.stat().st_size * 2,
            "merge should copy bytes, not openpyxl-bloat the workbook",
        )
        raw = pd.read_excel(
            out,
            sheet_name="销售任务及完成率",
            header=None,
        )
        mask = raw.iloc[:, 2].astype(str).str.contains("唐鹏", na=False)
        self.assertTrue(mask.any(), "唐鹏 row should exist")
        row = raw[mask].iloc[0]
        self.assertEqual(float(row.iloc[24]), 5.0)
        self.assertEqual(float(row.iloc[25]), 3.0)


if __name__ == "__main__":
    unittest.main()
