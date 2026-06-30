"""Tests for 招聘岗位族绩效模块与计算器。"""

from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.calculators.recruit import (
    compute_for_role,
    compute_person_commission,
    extract_role_inputs,
    extract_team_block,
    is_hub_linked,
    list_roles,
    lookup_golden_cells,
    lookup_golden_hub,
    lookup_role_performance,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.recruit_performance import (
    HUB_COLUMN,
    RecruitPerformanceModule,
)
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config
from salary_pipeline.pipelines.performance_overlay import overlay_module_metrics

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"

EXPECTED = {
    "周小红": 204.0,
    "刘晓琴": 108.0,
    "何婷婷": 156.0,
    "李玲": 132.0,
}

HUB_ROWS = {
    "周小红": 197,
    "刘晓琴": 198,
    "何婷婷": 199,
}

TEAM = {
    "onboard_count": 6.0,
    "commission_per_hire": 100.0,
    "total_commission": 600.0,
    "ratios": {
        "周小红": 0.34,
        "何婷婷": 0.26,
        "李玲": 0.22,
        "刘晓琴": 0.18,
    },
}


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class RecruitCalculatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))

    def test_team_block_extracted(self) -> None:
        block = extract_team_block(self.loader)
        self.assertEqual(set(block.keys()), set(EXPECTED.keys()))
        anchor = block["周小红"]
        self.assertAlmostEqual(anchor.onboard_count, TEAM["onboard_count"])
        self.assertAlmostEqual(anchor.commission_per_hire, TEAM["commission_per_hire"])
        self.assertAlmostEqual(anchor.total_commission, TEAM["total_commission"])

    def test_formula_matches_golden(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                team = extract_role_inputs(self.loader, name)
                self.assertAlmostEqual(
                    team.allocation_ratio, TEAM["ratios"][name], places=4
                )
                calc = compute_person_commission(team)
                self.assertAlmostEqual(calc, expected, places=2)
                perf = lookup_role_performance(self.loader, name)
                self.assertAlmostEqual(perf, expected, places=2)

    def test_compute_from_extracted_inputs(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                team = extract_role_inputs(self.loader, name)
                result = compute_for_role(name, team)
                self.assertAlmostEqual(result.insurance_performance, expected, places=2)
                self.assertAlmostEqual(
                    result.team.onboard_count * result.team.commission_per_hire,
                    TEAM["total_commission"],
                    places=2,
                )

    def test_lookup_golden_hub_rows(self) -> None:
        for name, expected in EXPECTED.items():
            if name not in HUB_ROWS:
                continue
            with self.subTest(name=name, row=HUB_ROWS[name]):
                golden = lookup_golden_hub(self.loader, name)
                assert golden is not None
                self.assertAlmostEqual(golden, expected, places=2)

    def test_liling_hub_linked_false(self) -> None:
        role = next(r for r in list_roles() if r["name"] == "李玲")
        self.assertFalse(is_hub_linked(role))
        golden = lookup_golden_hub(self.loader, "李玲")
        self.assertIsNone(golden)
        cells = lookup_golden_cells(self.loader, "李玲")
        self.assertAlmostEqual(cells["提成金额"], EXPECTED["李玲"], places=2)


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class RecruitModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.config = config
        cls.skeleton = SummarySkeletonModule().run({"month_config": config}).metrics

    def test_module_covers_three_hub_rows(self) -> None:
        result = RecruitPerformanceModule().run(
            {
                "month_config": self.config,
                "summary_skeleton": self.skeleton,
            }
        )
        self.assertEqual(len(result.metrics), 3)
        names = set(result.metrics["姓名"])
        self.assertEqual(names, {"周小红", "刘晓琴", "何婷婷"})

    def test_overlay_matches_golden(self) -> None:
        perf = RecruitPerformanceModule().run(
            {
                "month_config": self.config,
                "summary_skeleton": self.skeleton,
            }
        )
        summary = overlay_module_metrics(self.skeleton.copy(), perf)
        for name, expected in EXPECTED.items():
            if name == "李玲":
                continue
            with self.subTest(name=name):
                row = summary[summary["姓名"] == name].iloc[0]
                self.assertAlmostEqual(float(row[HUB_COLUMN]), expected, places=2)
                self.assertEqual(str(row["店别"]), "行政人事部")


if __name__ == "__main__":
    unittest.main()
