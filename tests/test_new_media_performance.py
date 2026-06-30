"""Tests for 新媒体岗位族绩效模块（试点）。"""

from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.data_ingestion.new_media_sheet import (
    load_new_media_performance_frame,
    lookup_vehicle_performance,
)
from salary_pipeline.modules.new_media_performance import NewMediaPerformanceModule
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config
from salary_pipeline.pipelines.performance_overlay import overlay_module_metrics

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class NewMediaPerformanceModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.config = config
        cls.loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))
        cls.source = load_new_media_performance_frame(cls.loader)
        cls.skeleton = SummarySkeletonModule().run({"month_config": config}).metrics

    def test_lookup_xiaotingzhong(self) -> None:
        val = lookup_vehicle_performance(self.source, "肖廷忠")
        self.assertAlmostEqual(val, 9684.0522875817, places=4)

    def test_module_covers_seven_sales_rows(self) -> None:
        result = NewMediaPerformanceModule().run(
            {
                "month_config": self.config,
                "summary_skeleton": self.skeleton,
                "project_root": PROJECT_ROOT,
            }
        )
        self.assertEqual(len(result.metrics), 7)
        names = set(result.metrics["姓名"].map(normalize_name))
        self.assertIn("肖廷忠", names)
        self.assertNotIn("蒋利", names)

    def test_overlay_matches_golden_w_column(self) -> None:
        result = NewMediaPerformanceModule().run(
            {
                "month_config": self.config,
                "summary_skeleton": self.skeleton,
                "project_root": PROJECT_ROOT,
            }
        )
        base = self.skeleton.drop(columns=["_excel_row"], errors="ignore").copy()
        base["整车绩效"] = pd.NA
        merged = overlay_module_metrics(base, result)
        for _, row in result.metrics.iterrows():
            golden_w = self.loader.read_cell_value(
                "提成汇总",
                f"W{int(self.skeleton.loc[self.skeleton['姓名']==row['姓名'], '_excel_row'].iloc[0])}",
            )
            got = merged.loc[merged["姓名"] == row["姓名"], "整车绩效"].iloc[0]
            self.assertAlmostEqual(float(got), float(golden_w), places=4)


if __name__ == "__main__":
    unittest.main()
