"""Tests for 销售顾问岗位族绩效模块（Phase C）。"""

from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.calculators.sales_advisor import (
    compute_for_advisor,
    hub_linked_names,
    is_hub_linked,
    list_roles,
    lookup_golden_hub,
    match_advisor_row,
    parse_hub_formula,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.modules.sales_advisor_performance import SalesAdvisorPerformanceModule
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config
from salary_pipeline.pipelines.hub_formula_engine import HubFormulaEngine
from salary_pipeline.pipelines.performance_overlay import (
    clear_bootstrap_for_overlay,
    overlay_module_metrics,
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

GATE_COLUMNS = (
    "整车绩效",
    "加装绩效",
    "保险绩效",
    "金融绩效",
    "爱车宝绩效",
    "上户绩效",
)


class SalesAdvisorFormulaParseTest(unittest.TestCase):
    def test_parse_sumifs_with_multiplier(self) -> None:
        spec = parse_hub_formula(
            "=SUMIFS(绩效整理表!AG:AG,绩效整理表!P:P,D92)*H92",
            hub_letter="W",
        )
        assert spec is not None
        self.assertEqual(spec.perf_columns, ("AG",))
        self.assertEqual(spec.multiply_ref, "H92")

    def test_parse_sumifs_add_const(self) -> None:
        spec = parse_hub_formula(
            "=SUMIFS(绩效整理表!AJ:AJ,绩效整理表!P:P,D134)+600",
            hub_letter="Z",
        )
        assert spec is not None
        self.assertEqual(spec.add_const, 600.0)

    def test_parse_sumif_chain(self) -> None:
        spec = parse_hub_formula(
            "=SUMIF(绩效整理表!P:P,D92,绩效整理表!AN:AN)"
            "+SUMIF(绩效整理表!P:P,D92,绩效整理表!AS:AS)",
            hub_letter="AC",
        )
        assert spec is not None
        self.assertEqual(spec.kind, "sumif_chain")
        self.assertEqual(spec.perf_columns, ("AN", "AS"))


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class SalesAdvisorCalculatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(cls.config["workbooks"]["sales"]))
        cls.topology = resolve_project_path(cls.config["topology"]["sales"])
        ctx = {"month_config": cls.config}
        PerformanceSheetModule().run(ctx)
        cls.perf_frame = ctx["computed_perf_frame"]
        skeleton = SummarySkeletonModule().run({"month_config": cls.config}).metrics
        cls.advisors = skeleton[skeleton["职务"] == "销售顾问"].copy()

    def test_hub_linked_registry(self) -> None:
        linked = hub_linked_names()
        self.assertGreaterEqual(len(linked), 49)
        subsheet = next(r for r in list_roles() if r["name"] == "徐荣尧")
        self.assertFalse(is_hub_linked(subsheet))

    def test_calculator_matches_topology_engine(self) -> None:
        engine = HubFormulaEngine(
            self.topology,
            self.loader,
            computed_perf_frame=self.perf_frame,
        )
        golden_out = engine.apply(self.advisors.copy())
        mismatches = 0
        for _, row in self.advisors.iterrows():
            name = row["姓名"]
            calc = compute_for_advisor(
                row, self.perf_frame, self.loader, topology_path=self.topology
            )
            g_row = golden_out[golden_out["姓名"] == name].iloc[0]
            for col in ADVISOR_PERF_COLUMNS:
                g_val = float(g_row[col]) if pd.notna(g_row[col]) else 0.0
                c_val = float(calc.hub_metrics.get(col, 0.0))
                if abs(g_val - c_val) > TOLERANCE:
                    mismatches += 1
        self.assertEqual(mismatches, 0, f"calculator vs engine mismatches={mismatches}")

    def test_he_yu_insurance_and_shanghu(self) -> None:
        row = self.advisors[self.advisors["姓名"] == "何宇"].iloc[0]
        calc = compute_for_advisor(
            row, self.perf_frame, self.loader, topology_path=self.topology
        )
        golden_z = lookup_golden_hub(self.loader, "何宇", "保险绩效")
        golden_ac = lookup_golden_hub(self.loader, "何宇", "上户绩效")
        assert golden_z is not None and golden_ac is not None
        self.assertAlmostEqual(calc.hub_metrics["保险绩效"], golden_z, places=2)
        self.assertAlmostEqual(calc.hub_metrics["上户绩效"], golden_ac, places=2)

    def test_han_baicheng_insurance_add_600(self) -> None:
        row = self.advisors[self.advisors["姓名"] == "韩柏成"].iloc[0]
        calc = compute_for_advisor(
            row, self.perf_frame, self.loader, topology_path=self.topology
        )
        golden = lookup_golden_hub(self.loader, "韩柏成", "保险绩效")
        assert golden is not None
        self.assertAlmostEqual(calc.hub_metrics["保险绩效"], golden, places=2)
        self.assertAlmostEqual(calc.hub_metrics["保险绩效"], 800.0, places=2)


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class SalesAdvisorModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_month_config(CONFIG_DIR)
        ctx = {"month_config": cls.config}
        cls.skeleton = SummarySkeletonModule().run(ctx).metrics
        PerformanceSheetModule().run(ctx)
        cls.ctx = ctx

    def test_module_covers_hub_linked_advisors(self) -> None:
        result = SalesAdvisorPerformanceModule().run(
            {**self.ctx, "summary_skeleton": self.skeleton}
        )
        self.assertGreaterEqual(len(result.metrics), 49)
        self.assertTrue(all(match_advisor_row(r) for _, r in result.metrics.iterrows()))

    def test_overlay_gate_columns_match_golden(self) -> None:
        perf = SalesAdvisorPerformanceModule().run(
            {**self.ctx, "summary_skeleton": self.skeleton}
        )
        advisors = self.skeleton[self.skeleton["职务"] == "销售顾问"]
        base = clear_bootstrap_for_overlay(advisors.copy(), perf)
        summary = overlay_module_metrics(base, perf)
        loader = WorkbookLoader(resolve_project_path(self.config["workbooks"]["sales"]))
        for name in hub_linked_names()[:5]:
            with self.subTest(name=name):
                row = summary[summary["姓名"] == name].iloc[0]
                for col in GATE_COLUMNS:
                    golden = lookup_golden_hub(loader, name, col)
                    if golden is None:
                        continue
                    self.assertAlmostEqual(float(row[col]), golden, places=2)


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class SalesAdvisorPipelineTest(unittest.TestCase):
    def test_pipeline_w_ai_zero_diff_after_overlay(self) -> None:
        config = load_month_config(CONFIG_DIR)
        loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))
        topology = resolve_project_path(config["topology"]["sales"])
        pipeline = SalesPipeline(CONFIG_DIR)
        result = pipeline.run({"month_config": config})
        summary = result["summary"]
        advisors = summary[summary["职务"] == "销售顾问"]

        engine = HubFormulaEngine(
            topology,
            loader,
            computed_perf_frame=PerformanceSheetModule()
            .run({"month_config": config})
            .frame,
        )
        golden_out = engine.apply(
            SummarySkeletonModule()
            .run({"month_config": config})
            .metrics.pipe(lambda m: m[m["职务"] == "销售顾问"])
        )

        mismatches = 0
        for _, row in advisors.iterrows():
            name = row["姓名"]
            g_row = golden_out[golden_out["姓名"] == name].iloc[0]
            for col in ADVISOR_PERF_COLUMNS:
                g_val = float(g_row[col]) if pd.notna(g_row[col]) else 0.0
                c_val = float(row[col]) if pd.notna(row[col]) else 0.0
                if abs(g_val - c_val) > TOLERANCE:
                    mismatches += 1
        self.assertEqual(mismatches, 0, f"pipeline overlay mismatches={mismatches}")


if __name__ == "__main__":
    unittest.main()
