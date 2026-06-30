from __future__ import annotations

import unittest
from pathlib import Path

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
    DIRECT_STORE_COLUMN_MAP,
    DIRECT_STORE_CONFIG,
    XwPayoutFormulaEngine,
)


STORE_MANAGER_NAMES = ("朱剑波", "孙伟", "钟涛", "黎明朗", "吴思超")


class DirectStorePayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.month_cfg = yaml.safe_load(
            (CONFIG_DIR / "month.yaml").read_text(encoding="utf-8")
        )
        cls.workbook = resolve_project_path(cls.month_cfg["workbooks"]["sales"])
        cls.topology = resolve_project_path(cls.month_cfg["topology"]["sales"])
        cls.sheet = "直营店提成-发"

    def test_galaxy_ag_for_zhu_jianbo(self) -> None:
        skeleton = read_payout_skeleton(self.workbook, self.sheet)
        loader = WorkbookLoader(self.workbook)
        engine = XwPayoutFormulaEngine(
            self.topology, loader, DIRECT_STORE_CONFIG
        )
        result = engine.apply(skeleton[skeleton["姓名"] == "朱剑波"])
        golden = read_payout_metric_frame(
            self.workbook,
            self.sheet,
            DIRECT_STORE_COLUMN_MAP,
            data_start_row=3,
        )
        expected = golden.loc[golden["姓名"] == "朱剑波", "代发放绩效(银河A+B)"].iloc[0]
        actual = result["代发放绩效(银河A+B)"].iloc[0]
        self.assertAlmostEqual(float(actual), float(expected), places=4)

    def test_store_managers_core_columns(self) -> None:
        pipeline = ChannelPayoutPipeline("direct_store", CONFIG_DIR)
        result = pipeline.run()["summary"]
        golden = read_payout_metric_frame(
            self.workbook,
            self.sheet,
            DIRECT_STORE_COLUMN_MAP,
            data_start_row=3,
        )
        columns = self.month_cfg["direct_store_parity"]["columns"]
        tol = float(self.month_cfg["direct_store_parity"]["numeric_tolerance"])
        for name in STORE_MANAGER_NAMES:
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

    def test_basic_pay_sumif(self) -> None:
        loader = WorkbookLoader(self.workbook)
        engine = XwPayoutFormulaEngine(
            self.topology, loader, DIRECT_STORE_CONFIG
        )
        engine._row_names = {10: "朱剑波"}
        value = engine._eval_payout(
            "=SUMIF(直营店基本!C:C,'直营店提成-发'!D10,直营店基本!P:P)",
            10,
            "朱剑波",
        )
        self.assertAlmostEqual(float(value), 2851.0, places=4)


if __name__ == "__main__":
    unittest.main()
