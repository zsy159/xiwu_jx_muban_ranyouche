"""Tests for 客户专员底层计算器（对齐金标准子表 / hub 列）。"""

from __future__ import annotations

import unittest

from salary_pipeline.calculators.customer_specialist import (
    compute_for_role,
    extract_role_inputs,
    lookup_golden_cells,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"

HUB_EXPECTED = {
    "张保珍": {"整车绩效": 2000.0, "加装绩效": 4045.0},
    "邓芳": {"权限结余绩效": 1170.0, "加装绩效": 4607.0},
    "周舟": {"加装绩效": 4204.0},
}

SUBSHEET_EXPECTED = {
    "李璐秀": 1140.0,
    "郭静": 1540.0,
    "古瑞婷": 370.0,
}


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class CustomerSpecialistCalculatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))

    def test_hub_linked_roles(self) -> None:
        for name, expected in HUB_EXPECTED.items():
            with self.subTest(name=name):
                inputs = extract_role_inputs(self.loader, name)
                result = compute_for_role(name, inputs)
                for col, val in expected.items():
                    self.assertAlmostEqual(result.hub_metrics[col], val, places=2)
                golden = lookup_golden_cells(self.loader, name)
                for col, val in expected.items():
                    self.assertAlmostEqual(golden[col], val, places=2)

    def test_baoke_only_roles(self) -> None:
        for name, expected in SUBSHEET_EXPECTED.items():
            with self.subTest(name=name):
                inputs = extract_role_inputs(self.loader, name)
                result = compute_for_role(name, inputs)
                self.assertAlmostEqual(result.performance_salary, expected, places=2)


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class CustomerSpecialistModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from salary_pipeline.modules.customer_specialist_performance import (
            CustomerSpecialistPerformanceModule,
        )
        from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule

        config = load_month_config(CONFIG_DIR)
        cls.config = config
        cls.skeleton = SummarySkeletonModule().run({"month_config": config}).metrics
        cls.module_cls = CustomerSpecialistPerformanceModule

    def test_module_covers_three_hub_rows(self) -> None:
        result = self.module_cls().run(
            {
                "month_config": self.config,
                "summary_skeleton": self.skeleton,
                "project_root": PROJECT_ROOT,
            }
        )
        self.assertEqual(len(result.metrics), 3)
        names = set(result.metrics["姓名"].tolist())
        self.assertEqual(names, {"张保珍", "邓芳", "周舟"})


COMPUTED_HUB = PROJECT_ROOT / "output/2026-05/提成汇总.xlsx"
PERF_COLS = ("整车绩效", "权限结余绩效", "加装绩效")


@unittest.skipUnless(GOLDEN.exists() and COMPUTED_HUB.exists(), "fixtures missing")
class CustomerSpecialistHubWaiTest(unittest.TestCase):
    """提成汇总 W–AI：客户专员 3 行与金标准一致。"""

    def test_hub_rows_match_golden(self) -> None:
        import pandas as pd

        names = list(HUB_EXPECTED.keys())
        for label, path in [("golden", GOLDEN), ("computed", COMPUTED_HUB)]:
            df = pd.read_excel(path, sheet_name="提成汇总", header=1)
            sub = df[df["姓名"].isin(names)].set_index("姓名")
            self.assertEqual(len(sub), 3, f"{label}: expected 3 hub rows")
            for name, expected in HUB_EXPECTED.items():
                for col, val in expected.items():
                    actual = sub.at[name, col]
                    self.assertAlmostEqual(
                        float(actual), val, places=2, msg=f"{label} {name} {col}"
                    )

    def test_baoke_only_not_in_hub(self) -> None:
        import pandas as pd

        df = pd.read_excel(GOLDEN, sheet_name="提成汇总", header=1)
        in_hub = set(df["姓名"].tolist()) & set(SUBSHEET_EXPECTED.keys())
        self.assertEqual(in_hub, set(), "保客专员不应出现在提成汇总")


if __name__ == "__main__":
    unittest.main()
