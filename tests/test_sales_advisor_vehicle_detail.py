"""Tests for 销售顾问整车绩效原始数据层（订单级 AG 拆解）。"""

from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.calculators.sales_advisor.vehicle_performance_detail import (
    VehicleOrderPrimitive,
    load_vehicle_performance_detail,
    recompute_orders,
)
from salary_pipeline.calculators.sales_advisor import build_eval_perf_frame
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"
TOLERANCE = 1e-2


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class VehiclePerformanceDetailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(cls.config["workbooks"]["sales"]))
        cls.topology = resolve_project_path(cls.config["topology"]["sales"])
        ctx = {"month_config": cls.config}
        PerformanceSheetModule().run(ctx)
        cls.perf_frame = ctx["computed_perf_frame"]
        cls.eval_perf = build_eval_perf_frame(
            cls.loader, cls.perf_frame, cls.topology
        )
        skeleton = SummarySkeletonModule().run({"month_config": cls.config}).metrics
        cls.advisors = skeleton[skeleton["职务"] == "销售顾问"].copy()

    def _computed_ag_sum(self, advisor_name: str) -> float:
        mask = (
            self.perf_frame["P"].astype(str).map(normalize_name)
            == normalize_name(advisor_name)
        )
        return float(
            pd.to_numeric(self.perf_frame.loc[mask, "AG"], errors="coerce")
            .fillna(0)
            .sum()
        )

    def test_load_detail_ag_sum_matches_perf_sheet(self) -> None:
        for name in ("何宇", "唐鹏", "韩柏成"):
            with self.subTest(name=name):
                detail = load_vehicle_performance_detail(
                    self.loader,
                    name,
                    computed_perf=self.perf_frame,
                )
                expected = self._computed_ag_sum(name)
                self.assertGreater(len(detail.orders), 0, msg=f"{name} 应有订单")
                self.assertAlmostEqual(
                    detail.ag_sum, expected, places=2, msg=f"{name} AG 合计"
                )

    def test_per_order_ag_equals_rate_times_units(self) -> None:
        detail = load_vehicle_performance_detail(
            self.loader, "何宇", eval_perf=self.eval_perf
        )
        for order in detail.orders:
            with self.subTest(vin=order.vin):
                self.assertAlmostEqual(
                    order.ag_amount,
                    order.commission_rate * order.units,
                    places=2,
                )

    def test_edit_units_recomputes_sum(self) -> None:
        detail = load_vehicle_performance_detail(
            self.loader, "何宇", eval_perf=self.eval_perf
        )
        self.assertGreater(len(detail.orders), 0)
        edited = [
            VehicleOrderPrimitive(
                **{**order.__dict__, "units": order.units * 2}
            )
            for order in detail.orders
        ]
        recomputed = recompute_orders(edited, self.loader)
        new_sum = sum(o.ag_amount for o in recomputed)
        self.assertAlmostEqual(new_sum, detail.ag_sum * 2, places=2)

    def test_display_frame_has_chinese_columns(self) -> None:
        detail = load_vehicle_performance_detail(self.loader, "何宇")
        frame = detail.to_display_frame()
        self.assertIn("车架号", frame.columns)
        self.assertIn("单车整车绩效", frame.columns)
        self.assertNotIn("AG", frame.columns)

    def test_golden_column_when_computed_perf_provided(self) -> None:
        detail = load_vehicle_performance_detail(
            self.loader, "何宇", computed_perf=self.perf_frame
        )
        frame = detail.to_display_frame()
        self.assertIn("金标准整车绩效", frame.columns)
        self.assertTrue(detail.orders[0].golden_ag is not None)


if __name__ == "__main__":
    unittest.main()
