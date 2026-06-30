"""Tests for 邀约专员岗位族绩效模块与计算器。"""

from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.calculators.invite_specialist import (
    compute_for_role,
    extract_role_inputs,
    lookup_golden_af,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.invite_specialist_sheet import (
    load_invite_specialist_frame,
    lookup_vehicle_performance,
)
from salary_pipeline.modules.invite_specialist_performance import (
    InviteSpecialistPerformanceModule,
)
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config
from salary_pipeline.pipelines.performance_overlay import overlay_module_metrics

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"

EXPECTED = {
    "金玉梅": 3820.0,
    "周思雨": 5160.0,
    "陈文霜": 4780.0,
    "杜小红": 5240.0,
    "周梅": 6530.0,
    "李春梅": 6540.0,
    "魏艳": 4709.0,
    "谷雨": 5055.0,
    "杨婷": 4130.0,
}

DCC_HUB_COLUMN = "整车绩效"
CHONGZHOU_HUB_COLUMN = "整车完成考核"


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class InviteSpecialistCalculatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))

    def test_extract_and_compute_all_eight(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                inputs = extract_role_inputs(self.loader, name)
                result = compute_for_role(name, inputs)
                self.assertAlmostEqual(
                    result.hub_vehicle_performance, expected, places=2
                )


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class InviteSpecialistModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.config = config
        cls.loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))
        cls.source = load_invite_specialist_frame(cls.loader)
        cls.skeleton = SummarySkeletonModule().run({"month_config": config}).metrics

    def test_lookup_zhou_siyu(self) -> None:
        val = lookup_vehicle_performance(self.source, "周思雨")
        self.assertAlmostEqual(val, 5160.0, places=2)

    def test_module_covers_nine_rows(self) -> None:
        result = InviteSpecialistPerformanceModule().run(
            {
                "month_config": self.config,
                "summary_skeleton": self.skeleton,
                "project_root": PROJECT_ROOT,
            }
        )
        self.assertEqual(len(result.metrics), 9)

    def test_overlay_matches_golden_hub_columns(self) -> None:
        result = InviteSpecialistPerformanceModule().run(
            {
                "month_config": self.config,
                "summary_skeleton": self.skeleton,
                "project_root": PROJECT_ROOT,
            }
        )
        base = self.skeleton.drop(columns=["_excel_row"], errors="ignore").copy()
        base[DCC_HUB_COLUMN] = pd.NA
        base[CHONGZHOU_HUB_COLUMN] = pd.NA
        merged = overlay_module_metrics(base, result)
        hub_letter_by_name = {
            "杨婷": ("AK", CHONGZHOU_HUB_COLUMN),
        }
        for _, row in result.metrics.iterrows():
            name = row["姓名"]
            letter, col = hub_letter_by_name.get(name, ("W", DCC_HUB_COLUMN))
            excel_row = int(
                self.skeleton.loc[self.skeleton["姓名"] == name, "_excel_row"].iloc[0]
            )
            golden = self.loader.read_cell_value("提成汇总", f"{letter}{excel_row}")
            got = merged.loc[merged["姓名"] == name, col].iloc[0]
            self.assertAlmostEqual(float(got), float(golden), places=2)


if __name__ == "__main__":
    unittest.main()
