from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.payout_skeleton import read_payout_skeleton
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.xw_payout import ChannelPayoutPipeline
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


    @unittest.skipUnless(
        (PROJECT_ROOT / "output/2026-05/提成汇总.xlsx").exists(),
        "computed hub missing",
    )
    def test_payout_sumif_uses_computed_hub_for_tangcao(self) -> None:
        from salary_pipeline.data_ingestion.hub_frame_loader import build_hub_sumif_frame
        from salary_pipeline.data_ingestion.data_loader import normalize_name

        computed = resolve_project_path(
            self.month_cfg["outputs"]["commission_summary_file"]
        )
        hub_frame = build_hub_sumif_frame(self.workbook, computed_workbook=computed)
        row = hub_frame[hub_frame["D"].map(normalize_name) == "唐操"].iloc[0]
        self.assertAlmostEqual(float(row["W"]), 861.5385, places=2)
        self.assertAlmostEqual(float(row["X"]), -952.1525, places=2)

    def test_resolve_hub_context_from_month_config(self) -> None:
        pipeline = ChannelPayoutPipeline("xw", CONFIG_DIR)
        hub_rel = pipeline.month_config["outputs"].get("commission_summary_file")
        if not hub_rel:
            self.skipTest("commission_summary_file not configured")
        computed = resolve_project_path(hub_rel)
        if not computed.exists():
            self.skipTest("computed hub missing")

        path, use = pipeline._resolve_hub_context({})
        self.assertTrue(use)
        self.assertEqual(path, computed)

        path2, use2 = pipeline._resolve_hub_context({"use_computed_hub": False})
        self.assertFalse(use2)
        self.assertIsNone(path2)


if __name__ == "__main__":
    unittest.main()
