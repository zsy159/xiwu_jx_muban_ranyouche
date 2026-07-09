"""Tests for 内勤 / 网络顾问 / 新媒体翼真 / 按揭内勤岗位族 overlay。"""

from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.modules.network_advisor_performance import (
    NetworkAdvisorPerformanceModule,
)
from salary_pipeline.modules.store_clerk_performance import StoreClerkPerformanceModule
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.modules.yizhen_new_media_performance import (
    YizhenNewMediaPerformanceModule,
)
from salary_pipeline.modules.mortgage_clerk_performance import (
    MortgageClerkPerformanceModule,
)
from salary_pipeline.data_ingestion.data_loader import build_workbook_loader
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.pipelines.hub_metrics_rule_engine import HubMetricsRuleEngine
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT
from salary_pipeline.pipelines.commission_summary import load_month_config
from salary_pipeline.pipelines.performance_overlay import overlay_module_metrics

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class RoleFamilyOverlayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.config = config
        ctx: dict = {"month_config": config, "project_root": PROJECT_ROOT}
        cls.skeleton = SummarySkeletonModule().run(ctx).metrics
        PerformanceSheetModule().run(ctx)
        loader = build_workbook_loader(ctx)
        cls.summary = HubMetricsRuleEngine().apply(
            cls.skeleton.copy(),
            computed_perf_frame=ctx.get("computed_perf_frame"),
            loader=loader,
        )
        ctx["summary_skeleton"] = cls.summary
        cls.ctx = ctx

    def test_store_clerk_wang_qiaoqiao_ak(self) -> None:
        result = StoreClerkPerformanceModule().run(self.ctx)
        row = result.metrics[result.metrics["姓名"] == "王巧巧"].iloc[0]
        self.assertAlmostEqual(float(row["整车完成考核"]), 280.0, places=2)

    def test_network_advisor_yu_caiwan_w(self) -> None:
        result = NetworkAdvisorPerformanceModule().run(self.ctx)
        row = result.metrics[result.metrics["姓名"] == "余才万"].iloc[0]
        self.assertAlmostEqual(float(row["整车绩效"]), 5280.0, places=2)

    def test_network_advisor_yu_caiwan3_channel_w(self) -> None:
        result = NetworkAdvisorPerformanceModule().run(self.ctx)
        row = result.metrics[result.metrics["姓名"] == "余才万3"].iloc[0]
        self.assertEqual(str(row["职务"]), "渠道")
        self.assertAlmostEqual(float(row["整车绩效"]), 120.0, places=2)

    def test_network_advisor_wang_hai_w(self) -> None:
        result = NetworkAdvisorPerformanceModule().run(self.ctx)
        row = result.metrics[result.metrics["姓名"] == "王海"].iloc[0]
        self.assertAlmostEqual(float(row["整车绩效"]), 1595.0, places=2)

    def test_yizhen_jiang_li_ak(self) -> None:
        result = YizhenNewMediaPerformanceModule().run(self.ctx)
        row = result.metrics[result.metrics["姓名"] == "蒋利"].iloc[0]
        self.assertAlmostEqual(float(row["整车完成考核"]), 6660.0, places=2)

    def test_mortgage_clerk_addon(self) -> None:
        result = MortgageClerkPerformanceModule().run(self.ctx)
        for name in ("熊宇", "李彦林"):
            row = result.metrics[result.metrics["姓名"] == name].iloc[0]
            self.assertAlmostEqual(float(row["加装绩效"]), 3985.8325, places=2)

    def test_overlay_populates_physical_columns(self) -> None:
        base = self.summary.drop(columns=["_excel_row"], errors="ignore").copy()
        for mod in (
            StoreClerkPerformanceModule(),
            NetworkAdvisorPerformanceModule(),
            YizhenNewMediaPerformanceModule(),
        ):
            result = mod.run(self.ctx)
            base = overlay_module_metrics(base, result)
        self.assertAlmostEqual(
            float(base.loc[base["姓名"] == "余才万", "整车绩效"].iloc[0]),
            5280.0,
            places=2,
        )
        self.assertAlmostEqual(
            float(base.loc[base["姓名"] == "蒋利", "整车完成考核"].iloc[0]),
            6660.0,
            places=2,
        )


if __name__ == "__main__":
    unittest.main()
