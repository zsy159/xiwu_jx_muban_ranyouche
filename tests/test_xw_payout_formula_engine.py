from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.payout_skeleton import read_payout_skeleton
from salary_pipeline.paths import CONFIG_DIR, resolve_project_path
from salary_pipeline.pipelines.xw_payout_formula_engine import (
    XW_CONFIG,
    XwPayoutFormulaEngine,
)


class XwPayoutFormulaEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.month_cfg = yaml.safe_load(
            (CONFIG_DIR / "month.yaml").read_text(encoding="utf-8")
        )
        cls.workbook = resolve_project_path(cls.month_cfg["workbooks"]["sales"])
        cls.topology = resolve_project_path(cls.month_cfg["topology"]["sales"])

    def test_hub_sumif_sample_row(self) -> None:
        skeleton = read_payout_skeleton(self.workbook, "XW提成-发")
        loader = WorkbookLoader(self.workbook)
        engine = XwPayoutFormulaEngine(self.topology, loader, XW_CONFIG)
        name = "熊杰文"
        row = skeleton[skeleton["姓名"] == name].iloc[0]
        result = engine.apply(skeleton[skeleton["姓名"] == name])
        self.assertIsNotNone(result["考核量"].iloc[0])
        self.assertEqual(int(row["_excel_row"]), 3)

    def test_row_sum_u_equals_h_to_t(self) -> None:
        loader = WorkbookLoader(self.workbook)
        engine = XwPayoutFormulaEngine(self.topology, loader, XW_CONFIG)
        engine.values = {f"{c}10": 1.0 for c in "HIJKLMNOPQRST"}
        total = engine._eval_sum("H10:T10")
        self.assertAlmostEqual(total, 13.0, places=6)

    def test_payroll_sumif_basic(self) -> None:
        loader = WorkbookLoader(self.workbook)
        engine = XwPayoutFormulaEngine(self.topology, loader, XW_CONFIG)
        engine._row_names = {3: "熊杰文"}
        value = engine._eval_payout(
            "=SUMIF(西物基本!C:C,D3,西物基本!P:P)", 3, "熊杰文"
        )
        self.assertIsNotNone(value)


if __name__ == "__main__":
    unittest.main()
