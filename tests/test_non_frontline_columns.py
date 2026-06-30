"""Tests for 非一线 semantic columns (management + support tiers)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from salary_pipeline.calculators.non_frontline.classification import (
    all_semantic_columns,
    highlight_column_for_row,
    is_management_non_frontline_row,
    is_non_frontline_row,
    is_support_non_frontline_row,
    non_frontline_tier,
)
from salary_pipeline.pipelines.commission_summary import CommissionSummaryBuilder
from salary_pipeline.pipelines.non_frontline_columns import (
    apply_non_frontline_columns,
    bootstrap_non_frontline_physical_columns,
)


class TestNonFrontlineClassification(unittest.TestCase):
    def test_management_shops(self) -> None:
        self.assertEqual(non_frontline_tier("销售管理部", "网销经理"), "management")
        self.assertTrue(is_management_non_frontline_row("事业部", "事业部总经理"))
        self.assertTrue(is_management_non_frontline_row("总经办", "储备干部"))

    def test_support_shops(self) -> None:
        self.assertEqual(non_frontline_tier("财务部", "会计"), "support")
        self.assertTrue(is_support_non_frontline_row("市场部", None))
        self.assertTrue(is_support_non_frontline_row("物流", "物流专员"))
        self.assertTrue(is_support_non_frontline_row("其它", "后勤"))

    def test_store_sales_director_not_non_frontline(self) -> None:
        self.assertFalse(is_non_frontline_row("西物-翼真", "销售总监"))
        self.assertIsNone(non_frontline_tier("西物-翼真", "销售总监"))

    def test_advisor_not_non_frontline(self) -> None:
        self.assertFalse(is_non_frontline_row("崇州直营店", "销售顾问"))

    def test_all_semantic_columns_includes_support_fields(self) -> None:
        cols = all_semantic_columns()
        self.assertIn("台次", cols)
        self.assertIn("提成系数", cols)
        self.assertIn("业绩绩效1", cols)
        self.assertIn("岗位绩效", cols)


class TestNonFrontlineColumns(unittest.TestCase):
    def test_copies_hub_values_for_management_rows_only(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "店别": "崇州直营店",
                    "职务": "销售顾问",
                    "姓名": "张三",
                    "整车绩效": 1000.0,
                    "加装绩效": 200.0,
                },
                {
                    "店别": "事业部",
                    "职务": "事业部总经理",
                    "姓名": "刘伟生",
                    "整车绩效": 6500.0,
                    "加装绩效": pd.NA,
                },
                {
                    "店别": "总经办",
                    "职务": "储备干部",
                    "姓名": "赖跃坤",
                    "整车绩效": 6000.0,
                    "加装绩效": 150.0,
                },
            ]
        )
        out = apply_non_frontline_columns(summary)
        advisor = out.loc[out["姓名"] == "张三"].iloc[0]
        self.assertTrue(pd.isna(advisor["岗位绩效"]))
        self.assertTrue(pd.isna(advisor["业绩绩效"]))
        self.assertTrue(pd.isna(advisor["台次"]))
        self.assertEqual(float(advisor["整车绩效"]), 1000.0)

        liu = out.loc[out["姓名"] == "刘伟生"].iloc[0]
        self.assertEqual(float(liu["岗位绩效"]), 6500.0)
        self.assertTrue(pd.isna(liu["整车绩效"]))
        self.assertTrue(pd.isna(liu["业绩绩效"]))
        self.assertTrue(pd.isna(liu["业绩绩效1"]))

        lai = out.loc[out["姓名"] == "赖跃坤"].iloc[0]
        self.assertEqual(float(lai["岗位绩效"]), 6000.0)
        self.assertEqual(float(lai["业绩绩效"]), 150.0)
        self.assertTrue(pd.isna(lai["整车绩效"]))
        self.assertTrue(pd.isna(lai["加装绩效"]))

    def test_copies_support_department_metrics(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "店别": "财务部",
                    "职务": "会计",
                    "姓名": "罗涵",
                    "综合毛利": 742.0,
                    "主营单台毛利": 2.0,
                    "整车绩效": 2700.0,
                    "加装绩效": 1484.0,
                },
                {
                    "店别": "市场部",
                    "职务": "武侯前台接待",
                    "姓名": "邓娟",
                    "整车+加装（毛利）": 740.0,
                    "主营单台毛利": 1.8,
                    "整车绩效": 1800.0,
                    "加装绩效": 1332.0,
                },
            ]
        )
        out = apply_non_frontline_columns(summary)
        luo = out.loc[out["姓名"] == "罗涵"].iloc[0]
        self.assertEqual(float(luo["台次"]), 742.0)
        self.assertEqual(float(luo["提成系数"]), 2.0)
        self.assertEqual(float(luo["岗位绩效"]), 2700.0)
        self.assertEqual(float(luo["业绩绩效1"]), 1484.0)
        self.assertTrue(pd.isna(luo["业绩绩效"]))
        self.assertTrue(pd.isna(luo["综合毛利"]))
        self.assertTrue(pd.isna(luo["主营单台毛利"]))
        self.assertTrue(pd.isna(luo["整车绩效"]))
        self.assertTrue(pd.isna(luo["加装绩效"]))

        deng = out.loc[out["姓名"] == "邓娟"].iloc[0]
        self.assertEqual(float(deng["入库"]), 740.0)
        self.assertEqual(float(deng["提成系数"]), 1.8)
        self.assertEqual(float(deng["业绩绩效1"]), 1332.0)
        self.assertTrue(pd.isna(deng["整车+加装（毛利）"]))
        self.assertTrue(pd.isna(deng["主营单台毛利"]))
        self.assertTrue(pd.isna(deng["整车绩效"]))
        self.assertTrue(pd.isna(deng["加装绩效"]))


    def test_frontline_physical_columns_unchanged(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "店别": "崇州直营店",
                    "职务": "销售顾问",
                    "姓名": "张三",
                    "整车绩效": 1000.0,
                    "加装绩效": 200.0,
                    "综合毛利": 50.0,
                },
            ]
        )
        out = apply_non_frontline_columns(summary)
        row = out.iloc[0]
        self.assertEqual(float(row["整车绩效"]), 1000.0)
        self.assertEqual(float(row["加装绩效"]), 200.0)
        self.assertEqual(float(row["综合毛利"]), 50.0)
        self.assertTrue(pd.isna(row["岗位绩效"]))
        self.assertTrue(pd.isna(row["台次"]))


class TestNonFrontlineBootstrap(unittest.TestCase):
    def test_bootstrap_fills_support_physical_columns_from_golden(self) -> None:
        golden = pd.DataFrame(
            [
                {
                    "店别": "财务部",
                    "职务": "会计",
                    "姓名": "罗涵",
                    "综合毛利": 742.0,
                    "主营单台毛利": 2.0,
                    "整车绩效": 2700.0,
                    "加装绩效": 1484.0,
                },
            ]
        )
        summary = pd.DataFrame(
            [
                {
                    "店别": "财务部",
                    "职务": "会计",
                    "姓名": "罗涵",
                    "综合毛利": pd.NA,
                    "主营单台毛利": pd.NA,
                    "整车绩效": pd.NA,
                    "加装绩效": pd.NA,
                },
            ]
        )
        builder = CommissionSummaryBuilder(
            template_columns=list(golden.columns),
        )
        with tempfile.TemporaryDirectory() as tmp:
            golden_path = Path(tmp) / "golden.xlsx"
            builder.export_excel(golden, golden_path)
            bootstrapped = bootstrap_non_frontline_physical_columns(summary, golden_path)
            out = apply_non_frontline_columns(bootstrapped)
        row = out.iloc[0]
        self.assertEqual(float(row["台次"]), 742.0)
        self.assertEqual(float(row["提成系数"]), 2.0)
        self.assertEqual(float(row["岗位绩效"]), 2700.0)
        self.assertEqual(float(row["业绩绩效1"]), 1484.0)


class TestNonFrontlineHighlightMapping(unittest.TestCase):
    def test_management_physical_maps_to_semantic_for_highlight(self) -> None:
        self.assertEqual(
            highlight_column_for_row("事业部", "事业部总经理", "整车绩效"),
            "岗位绩效",
        )
        self.assertEqual(
            highlight_column_for_row("崇州直营店", "销售顾问", "整车绩效"),
            "整车绩效",
        )


if __name__ == "__main__":
    unittest.main()
