"""Tests for Phase B performance sheet module + pipeline wiring (Slice 5)."""

from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, load_month_config
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.hub_formula_engine import HubFormulaEngine
from salary_pipeline.pipelines.performance_sheet_builder import (
    IMPLEMENTED_COLUMNS,
    PerformanceSheetBuilder,
)
from salary_pipeline.pipelines.sales import SalesPipeline

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"
TOLERANCE = 1e-2

ADVISOR_PERF_COLUMNS = (
    "整车绩效",
    "权限结余绩效",
    "加装绩效",
    "保险绩效",
    "金融绩效",
    "爱车宝绩效",
    "上户绩效",
    "盈利产品绩效",
    "延保提成",
    "特殊车型+指定车型",
    "座位险提成",
    "二手车提成",
    "玻碎险提成",
)


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class PerformanceSheetModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(cls.config["workbooks"]["sales"]))
        cls.topology = resolve_project_path(cls.config["topology"]["sales"])
        ctx = {"month_config": cls.config}
        cls.perf_result = PerformanceSheetModule().run(ctx)
        cls.computed_frame = ctx["computed_perf_frame"]
        skeleton = SummarySkeletonModule().run({"month_config": cls.config}).metrics
        cls.advisors = skeleton[skeleton["职务"] == "销售顾问"]

    def test_module_populates_context(self) -> None:
        self.assertFalse(self.computed_frame.empty)
        self.assertEqual(self.perf_result.metadata["source"], "computed")
        for col in IMPLEMENTED_COLUMNS:
            self.assertIn(col, self.computed_frame.columns, msg=col)

    def test_use_computed_false_skips_builder(self) -> None:
        ctx = {
            "month_config": {
                **self.config,
                "performance_sheet": {"use_computed": False},
            }
        }
        result = PerformanceSheetModule().run(ctx)
        self.assertNotIn("computed_perf_frame", ctx)
        self.assertEqual(result.metadata.get("status"), "skipped")

    def test_advisor_w_ai_zero_diff_with_computed_overlay(self) -> None:
        """51 销售顾问 W–AI：computed overlay vs 金标准绩效整理表 拓扑回放一致。"""
        golden_engine = HubFormulaEngine(self.topology, self.loader)
        computed_engine = HubFormulaEngine(
            self.topology,
            self.loader,
            computed_perf_frame=self.computed_frame,
        )
        golden_out = golden_engine.apply(self.advisors.copy())
        computed_out = computed_engine.apply(self.advisors.copy())

        mismatches = 0
        mismatch_detail: list[str] = []
        for idx, row in self.advisors.iterrows():
            name = row["姓名"]
            g_row = golden_out[golden_out["姓名"] == name].iloc[0]
            c_row = computed_out[computed_out["姓名"] == name].iloc[0]
            for col in ADVISOR_PERF_COLUMNS:
                g_val = float(g_row[col]) if pd.notna(g_row[col]) else 0.0
                c_val = float(c_row[col]) if pd.notna(c_row[col]) else 0.0
                if abs(g_val - c_val) > TOLERANCE:
                    mismatches += 1
                    mismatch_detail.append(f"{name}/{col}: {c_val} vs {g_val}")

        self.assertEqual(
            mismatches,
            0,
            f"W–AI mismatches={mismatches}: {mismatch_detail[:10]}",
        )

    def test_sales_pipeline_wires_computed_perf(self) -> None:
        """SalesPipeline.run 注入 computed_perf_frame 后顾问 W–AI 仍零差异。"""
        pipeline = SalesPipeline(CONFIG_DIR)
        result = pipeline.run({"month_config": load_month_config(CONFIG_DIR)})
        summary = result["summary"]
        advisors = summary[summary["职务"] == "销售顾问"]

        golden_engine = HubFormulaEngine(self.topology, self.loader)
        golden_out = golden_engine.apply(
            SummarySkeletonModule()
            .run({"month_config": self.config})
            .metrics.pipe(lambda m: m[m["职务"] == "销售顾问"])
        )

        mismatches = 0
        for _, row in advisors.iterrows():
            name = row["姓名"]
            g_row = golden_out[golden_out["姓名"] == name].iloc[0]
            c_row = advisors[advisors["姓名"] == name].iloc[0]
            for col in ADVISOR_PERF_COLUMNS:
                g_val = float(g_row[col]) if pd.notna(g_row[col]) else 0.0
                c_val = float(c_row[col]) if pd.notna(c_row[col]) else 0.0
                if abs(g_val - c_val) > TOLERANCE:
                    mismatches += 1

        self.assertEqual(mismatches, 0, f"pipeline W–AI mismatches={mismatches}")


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class PerformanceSheetBuilderProductionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))
        cls.builder = PerformanceSheetBuilder(loader)

    def test_build_alias_matches_slice_6(self) -> None:
        b6 = self.builder.build_slice_6()
        b_prod = self.builder.build()
        pd.testing.assert_frame_equal(b6, b_prod)


if __name__ == "__main__":
    unittest.main()
