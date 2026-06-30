"""销售顾问 Hub 五列（W/Y/Z/AE/AF）聚焦对账与手工暂缓登记。"""

from __future__ import annotations

import unittest

from salary_pipeline.calculators.sales_advisor.registry import (
    is_wa_parity_deferred,
    wa_parity_deferred_cells,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.ops.basic import sumif_by_key
from salary_pipeline.paths import CONFIG_DIR, resolve_project_path
from salary_pipeline.pipelines.commission_summary import load_month_config
from salary_pipeline.pipelines.performance_sheet_builder import PerformanceSheetBuilder

WA_FOCUS_COLUMNS = (
    "整车绩效",
    "保险绩效",
    "加装绩效",
    "特殊车型+指定车型",
    "延保提成",
)


class SalesAdvisorWaFocusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cfg = load_month_config(CONFIG_DIR)
        cls.cfg = cfg
        wb = resolve_project_path(cfg["workbooks"]["sales"])
        cls.loader = WorkbookLoader(wb)
        cls.builder = PerformanceSheetBuilder(cls.loader, billing_month="2026-05")

    def test_deferred_registry_covers_manual_cases(self) -> None:
        deferred = wa_parity_deferred_cells()
        self.assertIn("韩柏成", deferred)
        self.assertIn("整车绩效", deferred["韩柏成"])
        self.assertTrue(is_wa_parity_deferred("唐操", "整车绩效"))
        self.assertFalse(is_wa_parity_deferred("刘波", "整车绩效"))

    def test_xiongjunjie_ai_tail_adjustment(self) -> None:
        built = self.builder.build()
        total = float(sumif_by_key(built, "P", "AI", "熊俊杰"))
        self.assertAlmostEqual(total, 445.2024, places=2)

    def test_aq_sum_for_liubo(self) -> None:
        built = self.builder.build()
        total = float(sumif_by_key(built, "P", "AQ", "刘波"))
        self.assertAlmostEqual(total, 300.0, places=2)


if __name__ == "__main__":
    unittest.main()
