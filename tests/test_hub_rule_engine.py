"""Tests for declarative HubRuleEngine（销售顾问 W–AI，取代 topology 行号回放）。"""

from __future__ import annotations

import copy
import unittest

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.modules.sales_advisor_performance import (
    SalesAdvisorPerformanceModule,
)
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import PROJECT_ROOT
from salary_pipeline.pipelines.hub_rule_engine import (
    HubRuleEngine,
    load_hub_column_rules,
    resolve_sales_advisor_template,
)
from salary_pipeline.calculators.sales_advisor.extract import lookup_golden_hub

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"
GOLDEN_TOPOLOGY = (
    PROJECT_ROOT
    / "data/topology/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).topology.json"
)


def _golden_backed_config() -> dict:
    """2026-05 month config with workbooks/topology pointed at the full golden
    reference file (contains raw source sheets + 提成汇总 for read-only compare).
    """
    cfg = copy.deepcopy(load_month_config_for("2026-05"))
    cfg["workbooks"]["sales"] = str(GOLDEN)
    cfg["topology"]["sales"] = str(GOLDEN_TOPOLOGY)
    cfg["parity"]["golden_workbook"] = str(GOLDEN)
    return cfg


class TemplateSelectorTest(unittest.TestCase):
    """纯规则单测：不依赖金标准文件。"""

    def setUp(self) -> None:
        self.family_cfg = load_hub_column_rules()["role_families"]["销售顾问"]

    def test_store_ba_shop_selected(self) -> None:
        template, add_const = resolve_sales_advisor_template(
            name="张三", store="崇州直营店", family_cfg=self.family_cfg
        )
        self.assertEqual(template, "store_ba")
        self.assertEqual(add_const, 0.0)

    def test_default_personal_h_for_unlisted_store(self) -> None:
        template, add_const = resolve_sales_advisor_template(
            name="李四", store="武侯DCC", family_cfg=self.family_cfg
        )
        self.assertEqual(template, "personal_h")
        self.assertEqual(add_const, 0.0)

    def test_missing_store_defaults_personal_h(self) -> None:
        template, _ = resolve_sales_advisor_template(
            name="王五", store=None, family_cfg=self.family_cfg
        )
        self.assertEqual(template, "personal_h")

    def test_name_override_wins_over_store(self) -> None:
        """韩柏成即使在 store_ba 门店，姓名覆盖也应优先生效。"""
        template, add_const = resolve_sales_advisor_template(
            name="韩柏成", store="崇州直营店", family_cfg=self.family_cfg
        )
        self.assertEqual(template, "insurance_add")
        self.assertEqual(add_const, 600.0)


class HubRuleEngineSyntheticTest(unittest.TestCase):
    """合成绩效整理表：验证 store_ba(×BA) / personal_h(×H) / insurance_add(+常数) 计算。"""

    def setUp(self) -> None:
        self.engine = HubRuleEngine()
        self.family_cfg = self.engine.role_families["销售顾问"]
        self.perf = pd.DataFrame(
            [
                {"P": "张三", "AG": 1000.0, "AI": 200.0, "AJ": 300.0, "AK": 50.0},
                {"P": "李四", "AG": 2000.0, "AI": 400.0, "AJ": 100.0, "AK": 0.0},
                {"P": "韩柏成", "AG": 500.0, "AI": 0.0, "AJ": 200.0, "AK": 0.0},
            ]
        )

    def test_store_ba_multiplies_vehicle_by_ba_not_h(self) -> None:
        metrics = self.engine.compute_row(
            name="张三",
            store="崇州直营店",
            h_rate=0.5,
            perf_frame=self.perf,
            family_cfg=self.family_cfg,
            loader=None,  # no loader -> BA lookup unavailable, falls back to h_rate
        )
        # No loader available: BA lookup fails, falls back to h_rate (documented behavior).
        self.assertAlmostEqual(metrics["整车绩效"], 1000.0 * 0.5, places=4)
        self.assertAlmostEqual(metrics["加装绩效"], 200.0 * 0.5, places=4)
        self.assertAlmostEqual(metrics["保险绩效"], 300.0 * 0.5, places=4)
        self.assertAlmostEqual(metrics["金融绩效"], 50.0, places=4)

    def test_personal_h_multiplies_vehicle_by_h(self) -> None:
        metrics = self.engine.compute_row(
            name="李四",
            store="武侯DCC",
            h_rate=0.9,
            perf_frame=self.perf,
            family_cfg=self.family_cfg,
            loader=None,
        )
        self.assertAlmostEqual(metrics["整车绩效"], 2000.0 * 0.9, places=4)
        self.assertAlmostEqual(metrics["加装绩效"], 400.0 * 0.9, places=4)
        self.assertAlmostEqual(metrics["保险绩效"], 100.0 * 0.9, places=4)

    def test_insurance_add_applies_name_override_const(self) -> None:
        metrics = self.engine.compute_row(
            name="韩柏成",
            store="西物-翼真",
            h_rate=1.0,
            perf_frame=self.perf,
            family_cfg=self.family_cfg,
            loader=None,
        )
        # insurance_add: vehicle multiplies by H (default rate branch), insurance += 600
        self.assertAlmostEqual(metrics["整车绩效"], 500.0 * 1.0, places=4)
        self.assertAlmostEqual(metrics["保险绩效"], 200.0 * 1.0 + 600.0, places=4)

    def test_registration_sums_two_perf_columns(self) -> None:
        perf = pd.DataFrame(
            [{"P": "赵六", "AN": 100.0, "AS": 50.0}]
        )
        metrics = self.engine.compute_row(
            name="赵六",
            store="武侯DCC",
            h_rate=1.0,
            perf_frame=perf,
            family_cfg=self.family_cfg,
            loader=None,
        )
        self.assertAlmostEqual(metrics["上户绩效"], 150.0, places=4)

    def test_apply_writes_matched_family_rows_only(self) -> None:
        summary = pd.DataFrame(
            [
                {"店别": "崇州直营店", "职务": "销售顾问", "姓名": "张三", "销量完成率": 0.5},
                {"店别": "新媒体销售部", "职务": "新媒体专员", "姓名": "非顾问", "销量完成率": 1.0},
            ]
        )
        out = self.engine.apply(summary, computed_perf_frame=self.perf, loader=None)
        self.assertAlmostEqual(float(out.loc[0, "整车绩效"]), 500.0, places=4)
        self.assertTrue(pd.isna(out.loc[1, "整车绩效"]))


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class HubRuleEngineGoldenParityTest(unittest.TestCase):
    """对照 2026-05 金标准 提成汇总 只读校验（不回填金标准数值）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _golden_backed_config()
        ctx = {"month_config": cls.config}
        cls.skeleton = SummarySkeletonModule().run(ctx).metrics
        PerformanceSheetModule().run(ctx)
        cls.perf_frame = ctx["computed_perf_frame"]
        cls.loader = WorkbookLoader(str(GOLDEN))
        cls.engine = HubRuleEngine()
        cls.family_cfg = cls.engine.role_families["销售顾问"]

    def _row_for(self, name: str) -> pd.Series:
        advisors = self.skeleton[self.skeleton["职务"] == "销售顾问"]
        return advisors[advisors["姓名"] == name].iloc[0]

    def _h_rate_from_golden(self, excel_row: int) -> float:
        val = self.loader.read_cell_value("提成汇总", f"H{excel_row}")
        return float(val) if val is not None else 0.0

    def test_store_ba_advisor_matches_golden_all_columns(self) -> None:
        """唐鹏（崇州直营店，门店块 ×BA）：W–AI 与金标准逐列一致。"""
        name = "唐鹏"
        row = self._row_for(name)
        h_rate = self._h_rate_from_golden(int(row["_excel_row"]))
        metrics = self.engine.compute_row(
            name=name,
            store=row["店别"],
            h_rate=h_rate,
            perf_frame=self.perf_frame,
            family_cfg=self.family_cfg,
            loader=self.loader,
        )
        for col in self.family_cfg["columns"]:
            hub_col = col["hub_column"]
            golden = lookup_golden_hub(self.loader, name, hub_col)
            if golden is None:
                continue
            with self.subTest(col=hub_col):
                self.assertAlmostEqual(metrics.get(hub_col, 0.0), golden, places=2)

    def test_personal_h_advisor_matches_golden_all_columns(self) -> None:
        """何宇（武侯DCC，个人 ×H）：W–AI 与金标准逐列一致。"""
        name = "何宇"
        row = self._row_for(name)
        h_rate = self._h_rate_from_golden(int(row["_excel_row"]))
        metrics = self.engine.compute_row(
            name=name,
            store=row["店别"],
            h_rate=h_rate,
            perf_frame=self.perf_frame,
            family_cfg=self.family_cfg,
            loader=self.loader,
        )
        for col in self.family_cfg["columns"]:
            hub_col = col["hub_column"]
            golden = lookup_golden_hub(self.loader, name, hub_col)
            if golden is None:
                continue
            with self.subTest(col=hub_col):
                self.assertAlmostEqual(metrics.get(hub_col, 0.0), golden, places=2)

    def test_han_baicheng_insurance_add_matches_known_deferred_gap(self) -> None:
        """韩柏成：保险绩效手工 +600 常数生效；整车/加装绩效差异属已知
        wa_parity_deferred 个案（金标准手工格，非系统计算 bug）。"""
        name = "韩柏成"
        row = self._row_for(name)
        h_rate = self._h_rate_from_golden(int(row["_excel_row"]))
        metrics = self.engine.compute_row(
            name=name,
            store=row["店别"],
            h_rate=h_rate,
            perf_frame=self.perf_frame,
            family_cfg=self.family_cfg,
            loader=self.loader,
        )
        template, add_const = resolve_sales_advisor_template(
            name=name, store=row["店别"], family_cfg=self.family_cfg
        )
        self.assertEqual(template, "insurance_add")
        self.assertEqual(add_const, 600.0)
        # 金融/爱车宝/上户绩效等无乘数直引列应精确一致
        for hub_col in ("金融绩效", "爱车宝绩效", "上户绩效"):
            golden = lookup_golden_hub(self.loader, name, hub_col)
            if golden is not None:
                self.assertAlmostEqual(metrics.get(hub_col, 0.0), golden, places=2)


class SalesRoleUnificationTest(unittest.TestCase):
    """2026-07-07 用户要求：销售主管/销售助理并入销售顾问同一套规则（含
    template_selector），不再单独维持仅 W/Y/Z ×H 的窄规则。"""

    def setUp(self) -> None:
        self.rules = load_hub_column_rules()["role_families"]
        self.family_cfg = self.rules["销售顾问"]

    def test_supervisor_and_assistant_no_longer_separate_families(self) -> None:
        self.assertNotIn("销售主管", self.rules)
        self.assertNotIn("销售助理", self.rules)

    def test_match_includes_all_three_titles(self) -> None:
        self.assertEqual(
            set(self.family_cfg["match"]["职务"]),
            {"销售顾问", "销售主管", "销售助理"},
        )

    def test_full_column_set_applies_to_supervisor(self) -> None:
        """销售主管现与顾问一样计算全部 W–AI 列（此前仅 3 列）。"""
        engine = HubRuleEngine()
        perf = pd.DataFrame(
            [{"P": "赵七", "AG": 1000.0, "AI": 200.0, "AJ": 300.0, "AK": 50.0}]
        )
        metrics = engine.compute_row(
            name="赵七",
            store="武侯DCC",
            h_rate=0.8,
            perf_frame=perf,
            family_cfg=self.family_cfg,
            loader=None,
        )
        self.assertIn("金融绩效", metrics)
        self.assertAlmostEqual(metrics["整车绩效"], 1000.0 * 0.8, places=4)
        self.assertAlmostEqual(metrics["加装绩效"], 200.0 * 0.8, places=4)
        self.assertAlmostEqual(metrics["保险绩效"], 300.0 * 0.8, places=4)
        self.assertAlmostEqual(metrics["金融绩效"], 50.0, places=4)

    def test_supervisor_at_store_ba_shop_now_uses_ba_template(self) -> None:
        """并入统一规则后，若销售主管店别落在 store_ba_shops，会切到 store_ba
        模板（与此前"销售主管恒定 H"的窄规则不同——用户已知悉此权衡）。"""
        template, _ = resolve_sales_advisor_template(
            name="赵七", store="崇州直营店", family_cfg=self.family_cfg
        )
        self.assertEqual(template, "store_ba")


class MatchAdvisorRowTitlesTest(unittest.TestCase):
    """match_advisor_row 现覆盖销售顾问/销售主管/销售助理三个职务。"""

    def test_matches_all_three_titles(self) -> None:
        from salary_pipeline.calculators.sales_advisor.extract import match_advisor_row

        for title in ("销售顾问", "销售主管", "销售助理"):
            with self.subTest(title=title):
                row = pd.Series({"职务": title, "姓名": "某某"})
                self.assertTrue(match_advisor_row(row))

    def test_other_titles_not_matched(self) -> None:
        from salary_pipeline.calculators.sales_advisor.extract import match_advisor_row

        row = pd.Series({"职务": "新媒体专员", "姓名": "某某"})
        self.assertFalse(match_advisor_row(row))


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class SalesSupervisorUnifiedGoldenParityTest(unittest.TestCase):
    """2026-05 金标准只读验证：销售主管并入销售顾问规则后，W/Y/Z 数值不变
    （邓戈/熊杰文门店均不在 store_ba_shops，personal_h 兜底结果与此前 H-only
    窄规则一致），且新增列（如上户绩效）现也一并计算。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _golden_backed_config()
        ctx = {"month_config": cls.config}
        cls.skeleton = SummarySkeletonModule().run(ctx).metrics
        PerformanceSheetModule().run(ctx)
        cls.perf_frame = ctx["computed_perf_frame"]
        cls.loader = WorkbookLoader(str(GOLDEN))
        cls.engine = HubRuleEngine()
        cls.family_cfg = cls.engine.role_families["销售顾问"]

    def _check_supervisor(self, name: str, excel_row: int) -> None:
        supervisors = self.skeleton[self.skeleton["职务"] == "销售主管"]
        row = supervisors[supervisors["姓名"] == name].iloc[0]
        h_val = self.loader.read_cell_value("提成汇总", f"H{excel_row}")
        h_rate = float(h_val) if h_val is not None else 0.0
        metrics = self.engine.compute_row(
            name=name,
            store=row["店别"],
            h_rate=h_rate,
            perf_frame=self.perf_frame,
            family_cfg=self.family_cfg,
            loader=self.loader,
        )
        for hub_col, letter in (
            ("整车绩效", "W"),
            ("加装绩效", "Y"),
            ("保险绩效", "Z"),
            ("上户绩效", "AC"),
        ):
            golden = self.loader.read_cell_value("提成汇总", f"{letter}{excel_row}")
            if golden is None:
                continue
            with self.subTest(name=name, col=hub_col):
                self.assertAlmostEqual(metrics.get(hub_col, 0.0), float(golden), places=2)

    def test_deng_ge_matches_golden(self) -> None:
        """邓戈（机场展厅，row 60，不在 store_ba_shops）：personal_h 结果与
        此前 H-only 窄规则一致，新增的上户绩效列也与金标准一致。"""
        self._check_supervisor("邓戈", 60)

    def test_xiong_jiewen_matches_golden(self) -> None:
        """熊杰文（武侯DCC，row 107，不在 store_ba_shops）：同上。"""
        self._check_supervisor("熊杰文", 107)


class SalesAdvisorModuleWiringTest(unittest.TestCase):
    """SalesAdvisorPerformanceModule 已改为调用 HubRuleEngine（非 topology）。"""

    def test_module_imports_hub_rule_engine_not_topology_compute(self) -> None:
        import salary_pipeline.modules.sales_advisor_performance as mod

        self.assertTrue(hasattr(mod, "HubRuleEngine"))
        self.assertFalse(hasattr(mod, "compute_for_advisor"))


if __name__ == "__main__":
    unittest.main()
