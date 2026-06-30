"""Tests for 销售顾问字段拉通（Phase D 汇总层）。"""

from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.calculators.sales_advisor.aligned_input import (
    ALL_HUB_COLUMNS,
    AdvisorAlignedInput,
    coerce_aligned_input,
    compute_aligned,
    detect_template,
    extract_aligned_inputs,
    registration_performance_total,
)
from salary_pipeline.calculators.sales_advisor import (
    build_eval_perf_frame,
    hub_linked_names,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"
TOLERANCE = 1e-2


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class SalesAdvisorAlignedTest(unittest.TestCase):
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
        cls.eval_perf = build_eval_perf_frame(
            cls.loader, cls.perf_frame, cls.topology
        )

    def test_detect_template_personal_h(self) -> None:
        row = self.advisors[self.advisors["姓名"] == "何宇"].iloc[0]
        self.assertEqual(detect_template(int(row["_excel_row"])), "personal_h")

    def test_detect_template_store_ba(self) -> None:
        row = self.advisors[self.advisors["姓名"] == "唐鹏"].iloc[0]
        self.assertEqual(detect_template(int(row["_excel_row"])), "store_ba")

    def test_detect_template_insurance_add(self) -> None:
        row = self.advisors[self.advisors["姓名"] == "韩柏成"].iloc[0]
        self.assertEqual(detect_template(int(row["_excel_row"])), "insurance_add")

    def test_aligned_matches_golden_for_sample(self) -> None:
        for name in ("何宇", "唐鹏", "韩柏成"):
            with self.subTest(name=name):
                row = self.advisors[self.advisors["姓名"] == name].iloc[0]
                aligned = extract_aligned_inputs(self.loader, self.eval_perf, row)
                result = compute_aligned(name, aligned, self.loader)
                from salary_pipeline.calculators.sales_advisor import lookup_golden_hub_all

                golden = lookup_golden_hub_all(self.loader, name, ALL_HUB_COLUMNS)
                for col, gval in golden.items():
                    calc = result.hub_metrics.get(col, 0.0)
                    self.assertAlmostEqual(calc, gval, places=2, msg=f"{name} {col}")

    def test_manual_input_recomputes_vehicle(self) -> None:
        row = self.advisors[self.advisors["姓名"] == "何宇"].iloc[0]
        aligned = extract_aligned_inputs(self.loader, self.eval_perf, row)
        aligned.sales_completion_rate = 0.75
        aligned.perf_ag_sum = 10000.0
        result = compute_aligned("何宇", aligned, self.loader)
        self.assertAlmostEqual(result.hub_metrics["整车绩效"], 7500.0, places=2)

    def test_prefill_sums_match_golden_perf_sheet(self) -> None:
        """预填应等于 Excel 绩效整理表按姓名 SUM，而非 Hub W–AC 列。"""
        from salary_pipeline.pipelines.hub_formula_engine import HubFormulaEngine

        from salary_pipeline.data_ingestion.data_loader import normalize_name

        engine = HubFormulaEngine(
            self.topology, self.loader, computed_perf_frame=self.perf_frame
        )
        golden_perf = engine._sheet_frame("绩效整理表")
        for name in ("何宇", "唐鹏", "韩柏成"):
            with self.subTest(name=name):
                row = self.advisors[self.advisors["姓名"] == name].iloc[0]
                aligned = extract_aligned_inputs(self.loader, self.eval_perf, row)
                mask = (
                    golden_perf["P"].astype(str).map(normalize_name)
                    == normalize_name(name)
                )
                for col, attr in (
                    ("AG", "perf_ag_sum"),
                    ("AH", "perf_ah_sum"),
                    ("AI", "perf_ai_sum"),
                    ("AJ", "perf_aj_sum"),
                    ("AK", "perf_ak_sum"),
                    ("AL", "perf_al_sum"),
                    ("AM", "perf_am_sum"),
                    ("AN", "perf_an_sum"),
                    ("AO", "perf_ao_sum"),
                    ("AP", "perf_ap_sum"),
                    ("AQ", "perf_aq_sum"),
                    ("AR", "perf_ar_sum"),
                    ("AS", "perf_as_sum"),
                    ("AT", "perf_at_sum"),
                ):
                    expected = float(
                        pd.to_numeric(golden_perf.loc[mask, col], errors="coerce")
                        .fillna(0)
                        .sum()
                    )
                    actual = getattr(aligned, attr)
                    self.assertAlmostEqual(actual, expected, places=2, msg=f"{name} {col}")

    def test_personal_h_does_not_read_ba_completion_rate(self) -> None:
        row = self.advisors[self.advisors["姓名"] == "何宇"].iloc[0]
        aligned = extract_aligned_inputs(self.loader, self.eval_perf, row)
        self.assertEqual(detect_template(int(row["_excel_row"])), "personal_h")
        self.assertAlmostEqual(aligned.store_completion_rate, 1.0, places=4)

    def test_coerce_upgrades_legacy_session_instance(self) -> None:
        """旧 session 缓存缺 perf_ah_sum 等新字段时不应 AttributeError。"""
        legacy = object.__new__(AdvisorAlignedInput)
        legacy.sales_completion_rate = 0.8
        legacy.perf_ag_sum = 100.0
        legacy.perf_ai_sum = 200.0
        legacy.perf_aj_sum = 300.0
        legacy.perf_ak_sum = 400.0
        legacy.perf_am_sum = 500.0
        legacy.perf_an_sum = 600.0
        legacy.perf_as_sum = 700.0
        coerced = coerce_aligned_input(legacy)
        self.assertEqual(coerced.sales_completion_rate, 0.8)
        self.assertEqual(coerced.perf_ag_sum, 100.0)
        self.assertEqual(coerced.perf_ah_sum, 0.0)
        self.assertEqual(coerced.perf_al_sum, 0.0)
        self.assertEqual(coerced.perf_at_sum, 0.0)

    def test_registration_total_equals_hub_column(self) -> None:
        for name in ("何宇", "唐鹏", "韩柏成"):
            with self.subTest(name=name):
                row = self.advisors[self.advisors["姓名"] == name].iloc[0]
                aligned = extract_aligned_inputs(self.loader, self.eval_perf, row)
                result = compute_aligned(name, aligned, self.loader)
                total = registration_performance_total(aligned)
                self.assertAlmostEqual(
                    total,
                    result.hub_metrics["上户绩效"],
                    places=2,
                    msg=f"{name} AN+AS",
                )


if __name__ == "__main__":
    unittest.main()
