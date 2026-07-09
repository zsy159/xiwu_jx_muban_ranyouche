from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.pipelines.commission_summary import load_month_config
from salary_pipeline.pipelines.hub_formula_engine import HubFormulaEngine
from salary_pipeline.paths import CONFIG_DIR, resolve_project_path


class TestHubFormulaEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_month_config(CONFIG_DIR)
        cls.loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))
        cls.topology = resolve_project_path(config["topology"]["sales"])
        cls.engine = HubFormulaEngine(cls.topology, cls.loader)

    def test_tang_peng_row(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "店别": "崇州直营店",
                    "职务": "销售顾问",
                    "姓名": "唐鹏",
                    "_excel_row": 4,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "考核量"]), 5.0)
        self.assertAlmostEqual(float(out.loc[0, "实际销量"]), 3.0)
        self.assertAlmostEqual(float(out.loc[0, "销量完成率"]), 0.6)

    def test_deng_ge_supervisor_shanghu_double_sumif_chain(self) -> None:
        """销售主管 邓戈：上户绩效 = SUMIF(AN)+SUMIF(AS)，AN=258 AS=0。"""
        formula = (
            "=SUMIF(绩效整理表!P:P,D60,绩效整理表!AN:AN)"
            "+SUMIF(绩效整理表!P:P,D60,绩效整理表!AS:AS)"
        )
        val = self.engine._eval(formula, 60, "邓戈")
        self.assertIsNotNone(val)
        self.assertAlmostEqual(float(val), 258.0, places=2)

        summary = pd.DataFrame(
            [
                {
                    "店别": "机场展厅",
                    "职务": "销售主管",
                    "姓名": "邓戈",
                    "_excel_row": 60,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "上户绩效"]), 258.0, places=2)

    def test_xiong_jiewen_supervisor_shanghu_double_sumif_chain(self) -> None:
        """销售主管 熊杰文：上户绩效 = SUMIF(AN)+SUMIF(AS)，AN=428 AS=140。"""
        formula = (
            "=SUMIF(绩效整理表!P:P,D107,绩效整理表!AN:AN)"
            "+SUMIF(绩效整理表!P:P,D107,绩效整理表!AS:AS)"
        )
        val = self.engine._eval(formula, 107, "熊杰文")
        self.assertIsNotNone(val)
        self.assertAlmostEqual(float(val), 568.0, places=2)

        summary = pd.DataFrame(
            [
                {
                    "店别": "武侯DCC",
                    "职务": "销售主管",
                    "姓名": "熊杰文",
                    "_excel_row": 107,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "上户绩效"]), 568.0, places=2)

    def test_he_yu_shanghu_double_sumif_chain(self) -> None:
        """上户绩效 = SUMIF(AN)+SUMIF(AS)；链式解析须计入第一段。"""
        formula = (
            "=SUMIF(绩效整理表!P:P,D92,绩效整理表!AN:AN)"
            "+SUMIF(绩效整理表!P:P,D92,绩效整理表!AS:AS)"
        )
        val = self.engine._eval(formula, 92, "何宇")
        self.assertIsNotNone(val)
        self.assertAlmostEqual(float(val), 959.0, places=2)

        summary = pd.DataFrame(
            [
                {
                    "店别": None,
                    "职务": "销售顾问",
                    "姓名": "何宇",
                    "_excel_row": 92,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "上户绩效"]), 959.0, places=2)

    def test_han_baicheng_insurance_sumifs_plus_constant(self) -> None:
        """保险绩效 = SUMIFS(AJ)+600（韩柏成特例）。"""
        formula = "=SUMIFS(绩效整理表!AJ:AJ,绩效整理表!P:P,D134)+600"
        val = self.engine._eval(formula, 134, "韩柏成")
        self.assertIsNotNone(val)
        self.assertAlmostEqual(float(val), 800.0, places=2)

        summary = pd.DataFrame(
            [
                {
                    "店别": None,
                    "职务": "销售顾问",
                    "姓名": "韩柏成",
                    "_excel_row": 134,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "保险绩效"]), 800.0, places=2)

    def test_zhong_xiaoli_uses_sum_block(self) -> None:
        from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
        from salary_pipeline.pipelines.commission_summary import load_month_config

        config = load_month_config(CONFIG_DIR)
        skeleton = SummarySkeletonModule().run({"month_config": config}).metrics
        out = self.engine.apply(skeleton)
        row = out[out["姓名"] == "钟小丽"].iloc[0]
        self.assertAlmostEqual(float(row["考核量"]), 114.0)
        self.assertAlmostEqual(float(row["实际销量"]), 73.0)

    def test_mou_chunliu_ref_sumif_row(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "店别": "彭州直营店",
                    "职务": "出纳+内勤",
                    "姓名": "牟春柳",
                    "_excel_row": 32,
                }
            ]
        )
        out = self.engine.apply(summary)
        for col in ("考核量", "实际销量", "保险渗透率", "整车毛利"):
            self.assertIn(col, out.columns, msg=f"missing {col}")
            self.assertAlmostEqual(float(out.loc[0, col]), 0.0, msg=col)
        summary = pd.DataFrame(
            [
                {
                    "店别": "崇州直营店",
                    "职务": "销售顾问",
                    "姓名": "唐鹏",
                    "_excel_row": 4,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertIn("整车绩效", out.columns)
        self.assertAlmostEqual(float(out.loc[0, "整车绩效"]), 900.0)

    def test_xiaotingzhong_new_media_sumif(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "店别": "新媒体",
                    "职务": "运维主管",
                    "姓名": "肖廷忠",
                    "_excel_row": 124,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "整车绩效"]), 9684.0522875817, places=4)

    def test_zhou_xiaohong_recruit_sumif(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "店别": "行政人事部",
                    "职务": "行政主管",
                    "姓名": "周小红",
                    "_excel_row": 197,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "保险绩效"]), 204.0)

    def test_sub_sum_minus_chain_ac1(self) -> None:
        self.engine.values["AC59"] = 100.0
        val = self.engine._eval(
            "=SUM(AC59,AC71,AC89,AC106,AC120,AC137,AC144)-绩效整理表!AN1-绩效整理表!AS1",
            1,
            None,
        )
        self.assertIsNotNone(val)
        self.engine.values["AA59"] = 1540.0
        val = self.engine._eval(
            "=SUM(AA59,AA71,AA89,AA106,AA120,AA137)-绩效整理表!AK1",
            1,
            None,
        )
        self.assertIsNotNone(val)
        self.assertAlmostEqual(float(val), 0.0, places=4)

    def test_m218_metrics_subtract(self) -> None:
        self.engine.values["M217"] = -1086812.92155226
        val = self.engine._eval("=M217-指标汇总!E53", 218, "薛祥建")
        self.assertIsNotNone(val)
        self.assertAlmostEqual(float(val), -54649.881606472, places=2)

    def test_chen_ziyi_invite_ae_sumif(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "店别": "武侯DCC",
                    "职务": "邀约专员",
                    "姓名": "陈子逸",
                    "_excel_row": 211,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "整车绩效"]), 3638.0)

    def test_used_car_sheet_y185(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "店别": "武侯展厅",
                    "职务": "二手车专员",
                    "姓名": "测试",
                    "_excel_row": 185,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "加装绩效"]), 2250.0)

    def test_wang_qiaoqiao_vehicle_completion_ak(self) -> None:
        """内勤 王巧巧：整车完成考核 = G31*20（店块小计销量 × 20）。"""
        from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule

        config = load_month_config(CONFIG_DIR)
        skeleton = SummarySkeletonModule().run({"month_config": config}).metrics
        out = self.engine.apply(skeleton)
        row = out[out["姓名"] == "王巧巧"].iloc[0]
        self.assertGreater(float(row["整车完成考核"]), 0.0)

    def test_deng_ge_product_manager_ak(self) -> None:
        """销售主管 邓戈：整车完成考核 = 产品经理提成核算!W9。"""
        summary = pd.DataFrame(
            [
                {
                    "店别": "机场展厅",
                    "职务": "销售主管",
                    "姓名": "邓戈",
                    "_excel_row": 60,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "整车完成考核"]), 2725.0, places=2)

    def test_xue_xiangjian_yizhen_ak(self) -> None:
        """销售总监 薛祥建：整车完成考核 = SUMIF(翼真考核!C:C,D132,翼真考核!AC:AC)。"""
        summary = pd.DataFrame(
            [
                {
                    "店别": "西物-翼真",
                    "职务": "销售总监",
                    "姓名": "薛祥建",
                    "_excel_row": 132,
                }
            ]
        )
        out = self.engine.apply(summary)
        self.assertAlmostEqual(float(out.loc[0, "整车完成考核"]), 6500.0, places=2)

    def test_sales_assistant_w_without_bootstrap(self) -> None:
        """销售助理/内勤 W=SUMIFS(AG)×BA/H；bootstrap=false 时须惰性求值 BA/H。"""
        config = load_month_config(CONFIG_DIR)
        loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))
        topo = resolve_project_path(config["topology"]["sales"])
        engine = HubFormulaEngine(topo, loader, bootstrap_from_golden=False)
        engine._row_names = {16: "王海", 46: "蒋云", 74: "王熙鸿"}

        cases = [
            (16, "王海", "=SUMIFS(绩效整理表!AG:AG,绩效整理表!P:P,D16)*BA16", 1595.0),
            (46, "蒋云", "=SUMIFS(绩效整理表!AG:AG,绩效整理表!P:P,D46)*BA46", 100.0),
            (74, "王熙鸿", "=SUMIFS(绩效整理表!AG:AG,绩效整理表!P:P,D74)*H74", 200.0),
        ]
        for row, name, formula, expected in cases:
            with self.subTest(name=name):
                val = engine._eval(formula, row, name)
                self.assertIsNotNone(val)
                self.assertAlmostEqual(float(val), expected, places=2)

    def test_store_advisor_w_uses_task_sheet_combined_completion(self) -> None:
        """门店块销售顾问：W = SUMIFS(AG) × 销售任务及完成率!AG（合并完成率）。"""
        from salary_pipeline.main import _resolve_month_config
        from salary_pipeline.pipelines.run_cache import load_hub_snapshot

        try:
            config = _resolve_month_config("2026-05")
        except SystemExit:
            self.skipTest("2026-05 not registered; run onboard-month first")
        cache_dir = resolve_project_path(config["outputs"]["cache_dir"])
        if not cache_dir.exists():
            self.skipTest("2026-05 hub cache missing; run compute-all first")
        _, perf = load_hub_snapshot(cache_dir)
        loader = WorkbookLoader(resolve_project_path(config["workbooks"]["sales"]))
        topo = resolve_project_path(config["topology"]["sales"])
        engine = HubFormulaEngine(
            topo,
            loader,
            computed_perf_frame=perf,
            use_golden_perf_sheet=False,
            bootstrap_from_golden=False,
        )
        cases = [
            (5, "赵思梵", 2566.66666666667),
            (50, "丁小玲", 2280.0),
        ]
        for row, name, expected in cases:
            with self.subTest(name=name):
                summary = pd.DataFrame(
                    [
                        {
                            "店别": "崇州直营店",
                            "职务": "销售顾问",
                            "姓名": name,
                            "_excel_row": row,
                        }
                    ]
                )
                out = engine.apply(summary)
                self.assertAlmostEqual(
                    float(out.loc[0, "整车绩效"]), expected, places=2
                )

    def test_lookup_combined_completion_rate_from_uploads(self) -> None:
        from salary_pipeline.data_ingestion.data_loader import (
            lookup_combined_completion_rate,
        )
        from salary_pipeline.main import _resolve_month_config

        try:
            config = _resolve_month_config("2026-05")
        except SystemExit:
            self.skipTest("2026-05 not registered; run onboard-month first")
        golden = resolve_project_path(config["workbooks"]["sales"])
        if not golden.is_file():
            self.skipTest("2026-05 workbook missing")
        loader = WorkbookLoader(golden)
        rate = lookup_combined_completion_rate(loader, "赵思梵")
        self.assertIsNotNone(rate)
        self.assertAlmostEqual(float(rate), 1.16666666666667, places=4)


if __name__ == "__main__":
    unittest.main()
