"""Tests for 直营店经理岗位族绩效模块与计算器。"""

from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.calculators.direct_store_manager import (
    compute_for_role,
    extract_role_inputs,
    lookup_golden_r,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.direct_store_manager_performance import (
    DirectStoreManagerPerformanceModule,
    HUB_COLUMN,
)
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config
from salary_pipeline.pipelines.performance_overlay import overlay_module_metrics

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"

EXPECTED = {
    "朱剑波": 5891.48803846154,
    "孙伟": 3657.525,
    "吴思超": 4780.0485,
    "黎明朗": 6371.6875,
    "钟涛": 4431.61665217391,
}


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class DirectStoreManagerCalculatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))

    def test_extract_and_compute_all_five(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                inputs = extract_role_inputs(self.loader, name)
                result = compute_for_role(name, inputs)
                self.assertAlmostEqual(
                    result.hub_vehicle_performance, expected, places=2
                )

    def test_lookup_golden_matches_r_column(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                golden = lookup_golden_r(self.loader, name)
                assert golden is not None
                self.assertAlmostEqual(golden, expected, places=2)


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class DirectStoreManagerModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.config = config
        cls.skeleton = SummarySkeletonModule().run({"month_config": config}).metrics

    def test_module_covers_five_rows(self) -> None:
        result = DirectStoreManagerPerformanceModule().run(
            {
                "month_config": self.config,
                "summary_skeleton": self.skeleton,
            }
        )
        self.assertEqual(len(result.metrics), 5)
        names = set(result.metrics["姓名"])
        self.assertEqual(names, set(EXPECTED.keys()))

    def test_overlay_matches_golden(self) -> None:
        perf = DirectStoreManagerPerformanceModule().run(
            {
                "month_config": self.config,
                "summary_skeleton": self.skeleton,
            }
        )
        summary = overlay_module_metrics(self.skeleton.copy(), perf)
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                row = summary[summary["姓名"] == name].iloc[0]
                self.assertAlmostEqual(float(row[HUB_COLUMN]), expected, places=2)


if __name__ == "__main__":
    unittest.main()
