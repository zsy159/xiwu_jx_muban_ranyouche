from __future__ import annotations

import unittest
from pathlib import Path

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.aftersales_skeleton import read_aftersales_skeleton
from salary_pipeline.paths import CONFIG_DIR, resolve_project_path
from salary_pipeline.pipelines.aftersales_formula_engine import (
    INDEX_TERM,
    WUHOU_CONFIG,
    AftersalesFormulaEngine,
)


class AftersalesFormulaEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        month_cfg_path = CONFIG_DIR / "month.yaml"
        import yaml

        cls.month_cfg = yaml.safe_load(month_cfg_path.read_text(encoding="utf-8"))
        cls.workbook = resolve_project_path(cls.month_cfg["workbooks"]["aftersales"])
        cls.topology = resolve_project_path(cls.month_cfg["topology"]["aftersales"])

    def test_index_term_regex_matches_basic_lookup(self) -> None:
        body = "INDEX('05基本'!P:P,MATCH(C134,'05基本'!C:C,0))"
        match = INDEX_TERM.search(body)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("qsheet"), "05基本")
        self.assertEqual(match.group("vcol"), "P")
        self.assertEqual(match.group("kref"), "C134")

    def test_eval_index_lookup_for_sample_row(self) -> None:
        skeleton = read_aftersales_skeleton(self.workbook, WUHOU_CONFIG.anchor_sheet)
        row = skeleton[skeleton["姓名"] == "孙小平"].iloc[0]
        loader = WorkbookLoader(self.workbook)
        engine = AftersalesFormulaEngine(self.topology, loader, WUHOU_CONFIG)
        result = engine.apply(skeleton[skeleton["姓名"] == "孙小平"])
        self.assertAlmostEqual(float(result["基本工资"].iloc[0]), 1612.0, places=2)
        self.assertAlmostEqual(float(result["单位社保"].iloc[0]), 1268.59, places=2)
        self.assertEqual(int(row["_excel_row"]), 134)

    def test_sum_horizontal_range(self) -> None:
        loader = WorkbookLoader(self.workbook)
        engine = AftersalesFormulaEngine(self.topology, loader, WUHOU_CONFIG)
        engine.values = {"K30": 7182.7, "L30": 220.0}
        self.assertAlmostEqual(engine._eval_sum("K30:L30"), 7402.7, places=2)

    def test_tax_lookup_uses_ab_ac_table(self) -> None:
        loader = WorkbookLoader(self.workbook)
        engine = AftersalesFormulaEngine(self.topology, loader, WUHOU_CONFIG)
        engine._row_names = {5: "曹磊"}
        engine._bootstrap_static_columns()
        formula = "=INDEX(AC:AC,MATCH(C5,AB:AB,0))"
        value = engine._eval_aftersales(formula, 5, "曹磊")
        self.assertAlmostEqual(float(value), 797.76, places=2)


if __name__ == "__main__":
    unittest.main()
