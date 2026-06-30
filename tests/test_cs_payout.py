from __future__ import annotations

import unittest

import pandas as pd
import yaml

from salary_pipeline.data_ingestion.data_loader import (
    WorkbookLoader,
    read_payout_metric_frame,
)
from salary_pipeline.modules.payout_skeleton import read_payout_skeleton
from salary_pipeline.paths import CONFIG_DIR, resolve_project_path
from salary_pipeline.pipelines.xw_payout import ChannelPayoutPipeline
from salary_pipeline.pipelines.xw_payout_formula_engine import (
    CS_COLUMN_MAP,
    CS_CONFIG,
    XwPayoutFormulaEngine,
)


GOLDEN_ROW_NAMES = ("康忠伦", "何玉", "张嘉唯", "李彦林", "谷雨")


class CsPayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.month_cfg = yaml.safe_load(
            (CONFIG_DIR / "month.yaml").read_text(encoding="utf-8")
        )
        cls.workbook = resolve_project_path(cls.month_cfg["workbooks"]["sales"])
        cls.topology = resolve_project_path(cls.month_cfg["topology"]["sales"])
        cls.sheet = "CS提成-发"

    def test_cs_hub_sumif_sample(self) -> None:
        skeleton = read_payout_skeleton(self.workbook, self.sheet)
        loader = WorkbookLoader(self.workbook)
        engine = XwPayoutFormulaEngine(self.topology, loader, CS_CONFIG)
        row = skeleton.iloc[0]
        result = engine.apply(skeleton.iloc[[0]])
        self.assertIn("考核量", result.columns)
        self.assertIsNotNone(result["考核量"].iloc[0])
        self.assertEqual(int(row["_excel_row"]), 3)

    def test_tax_lookup_ba_bb(self) -> None:
        """CS uses INDEX(BB, MATCH(D, BA)) — not XW's AZ/BA tax table."""
        loader = WorkbookLoader(self.workbook)
        engine = XwPayoutFormulaEngine(self.topology, loader, CS_CONFIG)
        engine._row_names = {45: "康忠伦"}
        engine._bootstrap_static_columns()
        value = engine._eval_payout(
            "=INDEX(BB:BB,MATCH(D45,BA:BA,0))",
            45,
            "康忠伦",
        )
        self.assertAlmostEqual(float(value), 12.17, places=4)

    def test_basic_pay_sumif(self) -> None:
        loader = WorkbookLoader(self.workbook)
        engine = XwPayoutFormulaEngine(self.topology, loader, CS_CONFIG)
        engine._row_names = {36: "李芳"}
        value = engine._eval_payout(
            "=SUMIF(超市基本!C:C,D36,超市基本!P:P)",
            36,
            "李芳",
        )
        self.assertAlmostEqual(float(value), 2200.0, places=4)

    def test_golden_rows_core_columns(self) -> None:
        pipeline = ChannelPayoutPipeline("cs", CONFIG_DIR)
        result = pipeline.run()["summary"]
        golden = read_payout_metric_frame(
            self.workbook,
            self.sheet,
            CS_COLUMN_MAP,
            data_start_row=3,
        )
        columns = self.month_cfg["cs_parity"]["columns"]
        tol = float(self.month_cfg["cs_parity"]["numeric_tolerance"])
        for name in GOLDEN_ROW_NAMES:
            computed_row = result.loc[result["姓名"] == name].iloc[0]
            golden_row = golden.loc[golden["姓名"] == name].iloc[0]
            for col in columns:
                cv = computed_row[col]
                gv = golden_row[col]
                if pd.isna(gv) and pd.isna(cv):
                    continue
                self.assertAlmostEqual(
                    float(cv),
                    float(gv),
                    delta=tol,
                    msg=f"{name}.{col}",
                )


if __name__ == "__main__":
    unittest.main()
