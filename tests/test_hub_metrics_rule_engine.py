"""Tests for declarative HubMetricsRuleEngine（提成汇总 F–P，取代 topology 行号回放）。"""

from __future__ import annotations

import copy
import unittest

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import PROJECT_ROOT
from salary_pipeline.pipelines.hub_metrics_rule_engine import (
    HubMetricsRuleEngine,
    load_hub_metrics_rules,
)

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"


def _golden_backed_config() -> dict:
    cfg = copy.deepcopy(load_month_config_for("2026-05"))
    cfg["workbooks"]["sales"] = str(GOLDEN)
    cfg["parity"]["golden_workbook"] = str(GOLDEN)
    return cfg


class HubMetricsRuleEngineSyntheticTest(unittest.TestCase):
    """合成数据：验证各 op（sumif / ratio_with_cap_group / ratio / filtered_ratio / lookup_first）。"""

    def setUp(self) -> None:
        self.engine = HubMetricsRuleEngine()
        self.task_frame = pd.DataFrame(
            [
                {"姓名": "张三", "考核量": 10.0, "实际销量": 12.0, "集客达成率": 0.8},
                {"姓名": "李四", "考核量": 5.0, "实际销量": 2.0, "集客达成率": 0.5},
            ]
        )
        self.perf_frame = pd.DataFrame(
            [
                {"P": "张三", "K": 1, "S": 100.0, "BG": 1000.0, "BI": 200.0, "AB": 50.0, "AC": 10.0},
                {"P": "张三", "K": 1, "S": 50.0, "BG": 500.0, "BI": 100.0, "AB": 0.0, "AC": 0.0},
                {"P": "李四", "K": 1, "S": 0.0, "BG": 300.0, "BI": 0.0, "AB": 30.0, "AC": 5.0},
            ]
        )

    def _apply(self, summary: pd.DataFrame) -> pd.DataFrame:
        class _StubLoader:
            def has_sheet(_self, name: str) -> bool:
                return name == "销售任务及完成率"

            def read_sales_task_sheet(_self) -> pd.DataFrame:
                return self.task_frame

        return self.engine.apply(
            summary, computed_perf_frame=self.perf_frame, loader=_StubLoader()
        )

    def test_sumif_task_sheet_columns(self) -> None:
        summary = pd.DataFrame(
            [{"店别": "崇州直营店", "职务": "销售顾问", "姓名": "张三"}]
        )
        out = self._apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "考核量"]), 10.0)
        self.assertAlmostEqual(float(out.loc[0, "实际销量"]), 12.0)
        self.assertAlmostEqual(float(out.loc[0, "集客达成率"]), 0.8)

    def test_ratio_with_cap_group_default(self) -> None:
        """张三 12/10=120% 恰好触及默认 120% 上限，不属于覆盖分组。"""
        summary = pd.DataFrame(
            [{"店别": "崇州直营店", "职务": "销售顾问", "姓名": "张三"}]
        )
        out = self._apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "销量完成率"]), 1.2, places=4)

    def test_ratio_with_cap_group_override_caps_lower(self) -> None:
        """李四在覆盖分组店别（新媒体销售部）：2/5=40%，低于任何上限，原样。"""
        summary = pd.DataFrame(
            [{"店别": "新媒体销售部", "职务": "运维专员", "姓名": "李四"}]
        )
        out = self._apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "销量完成率"]), 0.4, places=4)

    def test_ratio_with_cap_group_override_actually_caps(self) -> None:
        """虚构一个比例超过 110% 覆盖上限但低于默认 120% 上限的分组行，验证分组生效。"""
        task_frame = pd.DataFrame(
            [{"姓名": "王五", "考核量": 10.0, "实际销量": 11.5, "集客达成率": 1.0}]
        )

        class _StubLoader:
            def has_sheet(_self, name: str) -> bool:
                return True

            def read_sales_task_sheet(_self) -> pd.DataFrame:
                return task_frame

        summary = pd.DataFrame(
            [{"店别": "西物-翼真", "职务": "销售总监", "姓名": "王五"}]
        )
        out = self.engine.apply(
            summary, computed_perf_frame=self.perf_frame, loader=_StubLoader()
        )
        # 11.5/10 = 1.15，若误用默认 120% 上限则应为 1.15；分组生效则应封顶 1.1
        self.assertAlmostEqual(float(out.loc[0, "销量完成率"]), 1.1, places=4)

    def test_sumif_perf_sheet_sums_multiple_orders(self) -> None:
        summary = pd.DataFrame(
            [{"店别": "崇州直营店", "职务": "销售顾问", "姓名": "张三"}]
        )
        out = self._apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "加装额"]), 150.0)
        self.assertAlmostEqual(float(out.loc[0, "整车毛利"]), 1500.0)
        self.assertAlmostEqual(float(out.loc[0, "加装毛利"]), 300.0)
        self.assertAlmostEqual(float(out.loc[0, "保险毛利"]), 50.0)
        self.assertAlmostEqual(float(out.loc[0, "按揭毛利"]), 10.0)

    def test_ratio_derived_column(self) -> None:
        """加装销量完成率 = 加装额 / (实际销量 × 1500)。"""
        summary = pd.DataFrame(
            [{"店别": "崇州直营店", "职务": "销售顾问", "姓名": "张三"}]
        )
        out = self._apply(summary)
        expected = 150.0 / (12.0 * 1500.0)
        self.assertAlmostEqual(float(out.loc[0, "加装销量完成率"]), expected, places=6)

    def test_filtered_ratio_insurance_penetration(self) -> None:
        """保险渗透率 = SUMIFS(K, AB>0, P=姓名) / SUMIF(P=姓名, K)：张三两单一单有保险。"""
        summary = pd.DataFrame(
            [{"店别": "崇州直营店", "职务": "销售顾问", "姓名": "张三"}]
        )
        out = self._apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "保险渗透率"]), 0.5, places=6)

    def test_unmatched_name_returns_zero_not_error(self) -> None:
        summary = pd.DataFrame(
            [{"店别": "武侯DCC", "职务": "出纳+内勤", "姓名": "未知人员"}]
        )
        out = self._apply(summary)
        for col in ("考核量", "实际销量", "销量完成率", "加装额", "整车毛利"):
            self.assertAlmostEqual(float(out.loc[0, col]), 0.0, msg=col)


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class HubMetricsRuleEngineGoldenParityTest(unittest.TestCase):
    """对照 2026-05 金标准 提成汇总 只读校验（不回填金标准数值）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _golden_backed_config()
        ctx = {"month_config": cls.config}
        cls.skeleton = SummarySkeletonModule().run(ctx).metrics
        PerformanceSheetModule().run(ctx)
        cls.perf_frame = ctx["computed_perf_frame"]
        cls.loader = WorkbookLoader(str(GOLDEN))
        cls.engine = HubMetricsRuleEngine()
        cls.out = cls.engine.apply(
            cls.skeleton, computed_perf_frame=cls.perf_frame, loader=cls.loader
        )

    def _row(self, name: str) -> pd.Series:
        matches = self.out[self.out["姓名"] == name]
        return matches.iloc[0]

    def test_tang_peng_full_f_to_p_matches_golden(self) -> None:
        """唐鹏（崇州直营店，默认 120% 分组）：F–P 全列与金标准一致。"""
        row = self._row("唐鹏")
        expected = {
            "考核量": 5,
            "实际销量": 3,
            "销量完成率": 0.6,
            "集客达成率": 1,
            "加装额": 900.03,
            "加装销量完成率": 0.200006666666667,
            "保险渗透率": 1,
            "整车毛利": 1765.25,
            "加装毛利": 600.03,
            "保险毛利": 1267.376,
            "按揭毛利": 0,
        }
        for col, golden_val in expected.items():
            with self.subTest(col=col):
                self.assertAlmostEqual(float(row[col]), float(golden_val), places=2)

    def test_zhao_sifan_full_f_to_p_matches_golden(self) -> None:
        """赵思梵（崇州直营店）：F–P 全列与金标准一致（含负毛利）。"""
        row = self._row("赵思梵")
        expected = {
            "考核量": 9,
            "实际销量": 9,
            "销量完成率": 1,
            "集客达成率": 1,
            "加装额": 2238.09,
            "加装销量完成率": 0.165784444444444,
            "保险渗透率": 1,
            "整车毛利": -14437.4668275862,
            "加装毛利": 1350.09,
            "保险毛利": 5126.673,
            "按揭毛利": 1000,
        }
        for col, golden_val in expected.items():
            with self.subTest(col=col):
                self.assertAlmostEqual(float(row[col]), float(golden_val), places=1)

    def test_yu_caiwan_direct_store_management_cap_group_matches_golden(self) -> None:
        """余才万（直营店管理）：35/40=114.3%，覆盖分组 110% 生效，与金标准一致。

        若误用默认 120% 上限，本测试会失败（114.3% < 120% 不会被封顶）。
        """
        row = self._row("余才万")
        self.assertAlmostEqual(float(row["考核量"]), 35.0, places=2)
        self.assertAlmostEqual(float(row["实际销量"]), 40.0, places=2)
        self.assertAlmostEqual(float(row["销量完成率"]), 1.1, places=4)

    def test_mou_chunliu_non_task_role_all_zero(self) -> None:
        """牟春柳（彭州直营店 出纳+内勤，无任务表数据）：F–P 全为 0，非缺陷。"""
        row = self._row("牟春柳")
        for col in ("考核量", "实际销量", "销量完成率", "加装额", "整车毛利"):
            self.assertAlmostEqual(float(row[col]), 0.0, msg=col)


class RulesConfigStructureTest(unittest.TestCase):
    def test_config_has_eleven_fp_columns(self) -> None:
        cfg = load_hub_metrics_rules()
        columns = {spec["hub_column"] for spec in cfg["columns"]}
        expected = {
            "考核量",
            "实际销量",
            "销量完成率",
            "集客达成率",
            "加装额",
            "加装销量完成率",
            "保险渗透率",
            "整车毛利",
            "加装毛利",
            "保险毛利",
            "按揭毛利",
        }
        self.assertEqual(columns, expected)


if __name__ == "__main__":
    unittest.main()
