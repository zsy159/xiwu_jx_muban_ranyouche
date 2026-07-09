"""Tests for declarative HubAdjustmentRuleEngine（提成汇总 AM–AP 调整列）。"""

from __future__ import annotations

import copy
import unittest

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import PROJECT_ROOT
from salary_pipeline.pipelines.hub_adjustment_rule_engine import (
    HubAdjustmentRuleEngine,
    load_hub_adjustment_rules,
    resolve_activity_column_name,
)

GOLDEN = PROJECT_ROOT / "data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx"


def _golden_backed_config() -> dict:
    cfg = copy.deepcopy(load_month_config_for("2026-05"))
    cfg["workbooks"]["sales"] = str(GOLDEN)
    cfg["parity"]["golden_workbook"] = str(GOLDEN)
    cfg.setdefault("hub", {})["activity_column_name"] = "04月活动"
    return cfg


class HubAdjustmentRuleEngineSyntheticTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = HubAdjustmentRuleEngine(
            month_config={"hub": {"activity_column_name": "04月活动"}}
        )
        self.composite = pd.DataFrame(
            [
                {"B": "张三", "J": 100.0, "L": 200.0},
                {"B": "张三", "J": 50.0, "L": 30.0},
                {"B": "李四", "J": 0.0, "L": 400.0},
            ]
        )
        self.overdue = pd.DataFrame(
            [
                {"Q": "张三", "X": 80.0},
                {"Q": "李四", "X": 10.0},
            ]
        )
        self.perf = pd.DataFrame(
            [
                {"P": "张三", "AU": 15.0},
                {"P": "张三", "AU": 5.0},
                {"P": "李四", "AU": 0.0},
            ]
        )

    def _apply(self, summary: pd.DataFrame) -> pd.DataFrame:
        class _StubLoader:
            def has_sheet(_self, name: str) -> bool:
                return name in ("综合表", "重功超期+活动")

        engine = HubAdjustmentRuleEngine(
            month_config={"hub": {"activity_column_name": "04月活动"}}
        )
        engine._load_composite_frame = lambda _loader: self.composite  # type: ignore[method-assign]
        engine._load_overdue_frame = lambda _loader: self.overdue  # type: ignore[method-assign]
        return engine.apply(
            summary,
            computed_perf_frame=self.perf,
            loader=_StubLoader(),  # type: ignore[arg-type]
        )

    def test_sumif_composite_and_overdue_columns(self) -> None:
        summary = pd.DataFrame(
            [{"店别": "崇州直营店", "职务": "销售顾问", "姓名": "张三"}]
        )
        out = self._apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "综合项"]), 230.0)
        self.assertAlmostEqual(float(out.loc[0, "04月活动"]), 80.0)
        self.assertAlmostEqual(float(out.loc[0, "（已发放奖励）"]), 150.0)
        self.assertAlmostEqual(float(out.loc[0, "超期"]), 20.0)

    def test_missing_sheet_returns_zero(self) -> None:
        summary = pd.DataFrame(
            [{"店别": "崇州直营店", "职务": "销售顾问", "姓名": "王五"}]
        )
        engine = HubAdjustmentRuleEngine(
            month_config={"hub": {"activity_column_name": "05月活动"}}
        )
        out = engine.apply(summary, computed_perf_frame=pd.DataFrame(), loader=None)
        self.assertAlmostEqual(float(out.loc[0, "综合项"]), 0.0)
        self.assertIn("05月活动", out.columns)
        self.assertAlmostEqual(float(out.loc[0, "05月活动"]), 0.0)

    def test_activity_column_from_month_config(self) -> None:
        cfg = {"hub": {"activity_column_name": "06月活动"}}
        self.assertEqual(resolve_activity_column_name(cfg), "06月活动")
        self.assertEqual(resolve_activity_column_name({}), "04月活动")


@unittest.skipUnless(GOLDEN.exists(), "golden workbook missing")
class HubAdjustmentRuleEngineGoldenParityTest(unittest.TestCase):
    """2026-05 金标准只读：程羊等行调整列与金标准比对。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _golden_backed_config()
        ctx: dict = {"month_config": cls.config}
        cls.summary = SummarySkeletonModule().run(ctx).metrics
        PerformanceSheetModule().run(ctx)
        cls.perf = ctx["computed_perf_frame"]
        cls.loader = WorkbookLoader(str(GOLDEN))
        cls.engine = HubAdjustmentRuleEngine(month_config=cls.config)
        cls.out = cls.engine.apply(
            cls.summary,
            computed_perf_frame=cls.perf,
            loader=cls.loader,
        )
        cls.golden = pd.read_excel(GOLDEN, sheet_name="提成汇总", header=1)
        cls.golden.columns = [str(c).strip() for c in cls.golden.columns]

    def test_chengyang_adjustment_columns(self) -> None:
        name = "程羊"
        cols = ["综合项", "04月活动", "超期", "（已发放奖励）"]
        sys_row = self.out.loc[self.out["姓名"] == name].iloc[0]
        gold_row = self.golden.loc[self.golden["姓名"] == name].iloc[0]
        for col in cols:
            with self.subTest(column=col):
                sys_val = float(pd.to_numeric(sys_row[col], errors="coerce") or 0.0)
                gold_val = float(pd.to_numeric(gold_row[col], errors="coerce") or 0.0)
                self.assertAlmostEqual(
                    sys_val,
                    gold_val,
                    places=2,
                    msg=f"{name} {col}: system={sys_val} golden={gold_val}",
                )

    def test_rules_yaml_loads_four_columns(self) -> None:
        rules = load_hub_adjustment_rules()
        self.assertEqual(len(rules.get("columns", [])), 4)


if __name__ == "__main__":
    unittest.main()
