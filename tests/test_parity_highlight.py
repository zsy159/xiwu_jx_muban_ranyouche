"""Parity mismatch Excel highlighting tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from salary_pipeline.pipelines.commission_summary import CommissionSummaryBuilder
from salary_pipeline.data_ingestion.data_loader import normalize_header
from salary_pipeline.calculators.sales_advisor.registry import wa_parity_deferred_cells
from salary_pipeline.calculators.sales_advisor.topology_specs import (
    collect_topology_manual_formula_cells,
    collect_topology_static_fill_cells,
    is_manual_formula_adjustment,
)
from salary_pipeline.utils.excel_format import (
    FORMULA_ANOMALY_FILL_RGB,
    GOLDEN_STATIC_FILL_RGB,
    MANUAL_DEFERRED_FILL_RGB,
    MANUAL_DEFERRED_FILL_COMMENT,
    PARITY_MISMATCH_FILL_COMMENT,
    PARITY_MISMATCH_FILL_RGB,
    STATIC_FILL_COMMENT,
    add_commission_summary_color_legend,
    highlight_commission_summary_deferred_cells,
    highlight_commission_summary_mismatches,
)
from salary_pipeline.validation.parity import CellMismatch, CommissionSummaryParity


class ManualFormulaDetectionTests(unittest.TestCase):
    def test_is_manual_formula_adjustment(self) -> None:
        self.assertTrue(is_manual_formula_adjustment("=-140"))
        self.assertTrue(is_manual_formula_adjustment("=100"))
        self.assertTrue(is_manual_formula_adjustment("=SUMIFS(AJ:AJ,D:D,D3)-100"))
        self.assertTrue(is_manual_formula_adjustment("=AH80-100"))
        self.assertTrue(is_manual_formula_adjustment("=SUMIFS(AJ:AJ,D:D,D3)+600"))
        self.assertTrue(is_manual_formula_adjustment("=189*20"))
        self.assertTrue(is_manual_formula_adjustment("=100*0.8"))
        self.assertTrue(is_manual_formula_adjustment("=500+300"))
        self.assertFalse(is_manual_formula_adjustment("=SUMIFS(AJ:AJ,D:D,D3)"))
        self.assertFalse(is_manual_formula_adjustment("100"))
        self.assertFalse(is_manual_formula_adjustment("=W80*0.8"))

    def test_collect_manual_formula_cells_from_golden_workbook(self) -> None:
        columns = [
            "店别",
            "职务",
            "姓名",
            "权限结余绩效",
            "保险绩效",
            "整车绩效",
        ]
        df = pd.DataFrame(
            [
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "沈燕1",
                    "权限结余绩效": -140,
                    "保险绩效": 200,
                    "整车绩效": 3500,
                },
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "韩柏成",
                    "权限结余绩效": 100,
                    "保险绩效": 800,
                    "整车绩效": 1500,
                },
            ]
        )
        builder = CommissionSummaryBuilder(template_columns=columns)
        with tempfile.TemporaryDirectory() as tmp:
            golden_path = Path(tmp) / "golden.xlsx"
            topo_path = Path(tmp) / "topo.json"
            builder.export_excel(df, golden_path)

            wb = load_workbook(golden_path)
            ws = wb["提成汇总"]
            ws["X3"] = "=-140"
            ws["Z3"] = "=SUMIFS(AJ:AJ,D:D,D3)+600"
            ws["X4"] = "=189*20"
            ws["W4"] = "=SUMIFS(绩效整理表!AG:AG,绩效整理表!P:P,D4)"
            wb.save(golden_path)
            wb.close()

            topo_path.write_text(
                '{"cells": {'
                '"提成汇总!W4": {"formula": "=SUMIFS(绩效整理表!AG:AG,绩效整理表!P:P,D4)"}'
                "}}",
                encoding="utf-8",
            )
            manual_cells = collect_topology_manual_formula_cells(
                topology_path=topo_path,
                golden_workbook_path=golden_path,
            )
            self.assertIn(("沈燕1", "销售顾问"), manual_cells)
            self.assertIn("权限结余绩效", manual_cells[("沈燕1", "销售顾问")])
            self.assertIn("保险绩效", manual_cells[("沈燕1", "销售顾问")])
            self.assertIn("权限结余绩效", manual_cells[("韩柏成", "销售顾问")])
            self.assertNotIn("整车绩效", manual_cells.get(("韩柏成", "销售顾问"), frozenset()))

    def test_highlight_manual_formula_cells_blue_with_comment(self) -> None:
        columns = ["店别", "职务", "姓名", "权限结余绩效"]
        df = pd.DataFrame(
            [
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "沈燕1",
                    "权限结余绩效": -140,
                },
            ]
        )
        builder = CommissionSummaryBuilder(template_columns=columns)
        deferred = {"沈燕1": frozenset({"权限结余绩效"})}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(df, path)

            highlighted = highlight_commission_summary_deferred_cells(
                path,
                "提成汇总",
                deferred,
            )
            self.assertEqual(highlighted, 1)

            wb = load_workbook(path)
            ws = wb["提成汇总"]
            col = columns.index("权限结余绩效") + 1
            cell = ws.cell(row=3, column=col)
            self.assertEqual(cell.fill.start_color.rgb, MANUAL_DEFERRED_FILL_RGB)
            self.assertEqual(cell.comment.text, MANUAL_DEFERRED_FILL_COMMENT)


class ParityHighlightTests(unittest.TestCase):
    def test_collect_and_highlight_mismatch_cells(self) -> None:
        join_keys = ["店别", "职务", "姓名"]
        golden = pd.DataFrame(
            [
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "张三",
                    "整车毛利": 100.0,
                    "整车绩效": 50.0,
                },
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "李四",
                    "整车毛利": 200.0,
                    "整车绩效": 80.0,
                },
            ]
        )
        computed = golden.copy()
        computed.loc[0, "整车毛利"] = 101.0
        computed.loc[1, "整车绩效"] = 90.0

        checker = CommissionSummaryParity(
            join_keys=join_keys,
            columns=["整车毛利", "整车绩效"],
        )
        mismatches = checker.collect_cell_mismatches(computed, golden)
        self.assertEqual(len(mismatches), 2)
        mismatch_cols = {m.column for m in mismatches}
        self.assertEqual(mismatch_cols, {"整车毛利", "整车绩效"})

        builder = CommissionSummaryBuilder(template_columns=list(computed.columns))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(computed, path)

            highlighted = highlight_commission_summary_mismatches(
                path,
                "提成汇总",
                mismatches,
                join_keys,
                ["整车毛利", "整车绩效"],
            )
            self.assertEqual(highlighted, 2)

            wb = load_workbook(path)
            ws = wb["提成汇总"]
            self.assertEqual(
                ws["D3"].fill.start_color.rgb,
                PARITY_MISMATCH_FILL_RGB,
            )
            self.assertIsNotNone(ws["D3"].comment)
            assert ws["D3"].comment is not None
            self.assertIn(PARITY_MISMATCH_FILL_COMMENT, ws["D3"].comment.text)
            self.assertIn("金标准=100", ws["D3"].comment.text)
            self.assertIn("系统=101", ws["D3"].comment.text)
            self.assertEqual(
                ws["E4"].fill.start_color.rgb,
                PARITY_MISMATCH_FILL_RGB,
            )
            self.assertIsNotNone(ws["E4"].comment)
            self.assertNotEqual(
                ws["D4"].fill.start_color.rgb,
                PARITY_MISMATCH_FILL_RGB,
            )

    def test_wa_parity_deferred_cells_not_collected(self) -> None:
        join_keys = ["店别", "职务", "姓名"]
        golden = pd.DataFrame(
            [
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "唐操",
                    "整车绩效": 100.0,
                },
            ]
        )
        computed = golden.copy()
        computed.loc[0, "整车绩效"] = 999.0

        checker = CommissionSummaryParity(
            join_keys=join_keys,
            columns=["整车绩效"],
        )
        mismatches = checker.collect_cell_mismatches(computed, golden)
        self.assertEqual(mismatches, [])

    def test_highlight_deferred_cells_by_name_and_role(self) -> None:
        """手工录入格按 姓名+职务 高亮，不依赖 店别。"""
        deferred = wa_parity_deferred_cells()
        self.assertIn("唐操", deferred)
        self.assertIn("整车绩效", deferred["唐操"])

        df = pd.DataFrame(
            [
                {
                    "店别": float("nan"),
                    "职务": "销售顾问",
                    "姓名": "唐操",
                    "整车绩效": 100.0,
                    "保险绩效": 50.0,
                },
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "刘波",
                    "整车绩效": 200.0,
                    "保险绩效": 80.0,
                },
            ]
        )
        builder = CommissionSummaryBuilder(template_columns=list(df.columns))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(df, path)

            highlighted = highlight_commission_summary_deferred_cells(
                path,
                "提成汇总",
                deferred,
            )
            self.assertGreaterEqual(highlighted, 1)

            wb = load_workbook(path)
            ws = wb["提成汇总"]
            # 唐操 整车绩效 — deferred (nan 店别 still matches)
            perf_col = list(df.columns).index("整车绩效") + 1
            tang_cell = ws.cell(row=3, column=perf_col)
            self.assertEqual(
                tang_cell.fill.start_color.rgb,
                MANUAL_DEFERRED_FILL_RGB,
            )
            # 刘波 — not deferred
            liu_cell = ws.cell(row=4, column=perf_col)
            self.assertNotEqual(
                liu_cell.fill.start_color.rgb,
                MANUAL_DEFERRED_FILL_RGB,
            )

    def test_deferred_fill_wins_over_mismatch(self) -> None:
        """Deferred applied after mismatch; manual color takes precedence."""
        join_keys = ["店别", "职务", "姓名"]
        golden = pd.DataFrame(
            [
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "唐操",
                    "整车绩效": 100.0,
                },
            ]
        )
        computed = golden.copy()
        computed.loc[0, "整车绩效"] = 999.0

        builder = CommissionSummaryBuilder(template_columns=list(computed.columns))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(computed, path)

            checker = CommissionSummaryParity(
                join_keys=join_keys,
                columns=["整车绩效"],
            )
            mismatches = checker.collect_cell_mismatches(computed, golden)
            self.assertEqual(mismatches, [])

            # Simulate a mismatch highlight on the same cell, then deferred overwrites.
            highlight_commission_summary_mismatches(
                path,
                "提成汇总",
                [
                    CellMismatch(
                        join_values=(("店别", "西物"), ("职务", "销售顾问"), ("姓名", "唐操")),
                        column="整车绩效",
                    )
                ],
                join_keys,
                ["整车绩效"],
            )
            highlight_commission_summary_deferred_cells(
                path,
                "提成汇总",
                wa_parity_deferred_cells(),
            )

            wb = load_workbook(path)
            ws = wb["提成汇总"]
            perf_col = list(computed.columns).index("整车绩效") + 1
            cell = ws.cell(row=3, column=perf_col)
            self.assertEqual(cell.fill.start_color.rgb, MANUAL_DEFERRED_FILL_RGB)
            self.assertNotEqual(cell.fill.start_color.rgb, PARITY_MISMATCH_FILL_RGB)

    def test_collect_static_fill_cells_from_golden_workbook(self) -> None:
        """Topology omits formula-less cells; golden workbook is the source of truth."""
        columns = [
            "序号",
            "店别",
            "职务",
            "姓名",
            "人数",
            "考核量",
            "实际销量",
            "销量完成率",
            "整车绩效",
            "加装绩效",
        ]
        df = pd.DataFrame(
            [
                {
                    "序号": 1,
                    "店别": "机场DCC",
                    "职务": "销售助理",
                    "姓名": "王熙鸿",
                    "人数": 1,
                    "考核量": 11,
                    "实际销量": 1,
                    "销量完成率": 1,
                    "整车绩效": 200,
                    "加装绩效": 50,
                },
                {
                    "序号": 2,
                    "店别": "西物-翼真",
                    "职务": "销售顾问",
                    "姓名": "韩柏成",
                    "人数": 1,
                    "考核量": 10,
                    "实际销量": 8,
                    "销量完成率": 0.8,
                    "整车绩效": 1500,
                    "加装绩效": 1000,
                },
            ]
        )
        builder = CommissionSummaryBuilder(template_columns=columns)
        with tempfile.TemporaryDirectory() as tmp:
            golden_path = Path(tmp) / "golden.xlsx"
            topo_path = Path(tmp) / "topo.json"
            builder.export_excel(df, golden_path)

            wb = load_workbook(golden_path)
            ws = wb["提成汇总"]
            ws["H3"] = 1
            ws["Y4"] = 1000
            wb.save(golden_path)
            wb.close()

            topo_path.write_text(
                '{"cells": {'
                '"提成汇总!W3": {"formula": "=SUMIFS(绩效整理表!AG:AG,绩效整理表!P:P,D3)"},'
                '"提成汇总!W4": {"formula": "=SUMIFS(绩效整理表!AG:AG,绩效整理表!P:P,D4)"}'
                "}}",
                encoding="utf-8",
            )
            static_cells = collect_topology_static_fill_cells(
                topology_path=topo_path,
                golden_workbook_path=golden_path,
            )
            self.assertIn(("王熙鸿", "销售助理"), static_cells)
            self.assertIn("销量完成率", static_cells[("王熙鸿", "销售助理")])
            self.assertIn(("韩柏成", "销售顾问"), static_cells)
            self.assertIn("加装绩效", static_cells[("韩柏成", "销售顾问")])
            self.assertNotIn("整车绩效", static_cells[("韩柏成", "销售顾问")])

    def test_highlight_static_cells_gray_fill_and_comment(self) -> None:
        columns = [
            "店别",
            "职务",
            "姓名",
            "销量完成率",
            "整车绩效",
        ]
        df = pd.DataFrame(
            [
                {
                    "店别": "机场DCC",
                    "职务": "销售助理",
                    "姓名": "王熙鸿",
                    "销量完成率": 1,
                    "整车绩效": 200,
                },
            ]
        )
        builder = CommissionSummaryBuilder(template_columns=columns)
        static_cells = {("王熙鸿", "销售助理"): frozenset({"销量完成率"})}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(df, path)

            highlighted = highlight_commission_summary_deferred_cells(
                path,
                "提成汇总",
                {},
                static_cells=static_cells,
            )
            self.assertEqual(highlighted, 1)

            wb = load_workbook(path)
            ws = wb["提成汇总"]
            h_col = columns.index("销量完成率") + 1
            cell = ws.cell(row=3, column=h_col)
            self.assertEqual(cell.fill.start_color.rgb, GOLDEN_STATIC_FILL_RGB)
            self.assertIsNotNone(cell.comment)
            self.assertEqual(cell.comment.text, STATIC_FILL_COMMENT)

    def test_highlight_deferred_cells_blue_fill_and_comment(self) -> None:
        columns = ["店别", "职务", "姓名", "整车绩效"]
        df = pd.DataFrame(
            [
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "唐操",
                    "整车绩效": 100.0,
                },
            ]
        )
        builder = CommissionSummaryBuilder(template_columns=columns)
        deferred = {"唐操": frozenset({"整车绩效"})}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(df, path)

            highlighted = highlight_commission_summary_deferred_cells(
                path,
                "提成汇总",
                deferred,
            )
            self.assertEqual(highlighted, 1)

            wb = load_workbook(path)
            ws = wb["提成汇总"]
            perf_col = columns.index("整车绩效") + 1
            cell = ws.cell(row=3, column=perf_col)
            self.assertEqual(cell.fill.start_color.rgb, MANUAL_DEFERRED_FILL_RGB)
            self.assertIsNotNone(cell.comment)
            self.assertEqual(cell.comment.text, MANUAL_DEFERRED_FILL_COMMENT)

    def test_static_fill_wins_over_mismatch(self) -> None:
        join_keys = ["店别", "职务", "姓名"]
        columns = ["店别", "职务", "姓名", "加装绩效"]
        golden = pd.DataFrame(
            [
                {
                    "店别": "西物-翼真",
                    "职务": "销售顾问",
                    "姓名": "韩柏成",
                    "加装绩效": 1000.0,
                },
            ]
        )
        computed = golden.copy()
        computed.loc[0, "加装绩效"] = 0.0

        builder = CommissionSummaryBuilder(template_columns=columns)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(computed, path)

            highlight_commission_summary_mismatches(
                path,
                "提成汇总",
                [
                    CellMismatch(
                        join_values=(
                            ("店别", "西物-翼真"),
                            ("职务", "销售顾问"),
                            ("姓名", "韩柏成"),
                        ),
                        column="加装绩效",
                    )
                ],
                join_keys,
                ["加装绩效"],
            )
            highlight_commission_summary_deferred_cells(
                path,
                "提成汇总",
                {},
                static_cells={("韩柏成", "销售顾问"): frozenset({"加装绩效"})},
            )

            wb = load_workbook(path)
            ws = wb["提成汇总"]
            y_col = columns.index("加装绩效") + 1
            cell = ws.cell(row=3, column=y_col)
            self.assertEqual(cell.fill.start_color.rgb, GOLDEN_STATIC_FILL_RGB)

    def test_deferred_wins_over_static_for_same_cell(self) -> None:
        """wa_parity_deferred takes blue fill when cell is also a golden static fill."""
        columns = ["店别", "职务", "姓名", "加装绩效"]
        df = pd.DataFrame(
            [
                {
                    "店别": "西物-翼真",
                    "职务": "销售顾问",
                    "姓名": "韩柏成",
                    "加装绩效": 1000.0,
                },
            ]
        )
        builder = CommissionSummaryBuilder(template_columns=columns)
        deferred = {"韩柏成": frozenset({"加装绩效"})}
        static_cells = {("韩柏成", "销售顾问"): frozenset({"加装绩效"})}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(df, path)

            highlighted = highlight_commission_summary_deferred_cells(
                path,
                "提成汇总",
                deferred,
                static_cells=static_cells,
            )
            self.assertEqual(highlighted, 1)

            wb = load_workbook(path)
            ws = wb["提成汇总"]
            y_col = columns.index("加装绩效") + 1
            cell = ws.cell(row=3, column=y_col)
            self.assertEqual(cell.fill.start_color.rgb, MANUAL_DEFERRED_FILL_RGB)

    def test_cell_mismatch_join_dict(self) -> None:
        mismatch = CellMismatch(
            join_values=(("店别", "西物"), ("职务", "销售顾问"), ("姓名", "张三")),
            column="整车毛利",
        )
        self.assertEqual(
            mismatch.join_dict(),
            {"店别": "西物", "职务": "销售顾问", "姓名": "张三"},
        )

    def test_erwang_blank_ah_skip_for_hub_permission_column(self) -> None:
        """Golden D 二网 → AH blank; computed AH explains Hub 权限结余绩效 diff."""
        from salary_pipeline.validation.golden_perf_skips import (
            hub_parity_skip_erwang_blank_ah,
        )

        join_keys = ["店别", "职务", "姓名"]
        golden = pd.DataFrame(
            [
                {
                    "店别": "武侯DCC",
                    "职务": "销售顾问",
                    "姓名": "蒲喜",
                    "权限结余绩效": -747.3054,
                },
            ]
        )
        computed = golden.copy()
        computed.loc[0, "权限结余绩效"] = -964.0254

        adjustments = {"蒲喜": -216.72}
        checker = CommissionSummaryParity(
            join_keys=join_keys,
            columns=["权限结余绩效"],
            golden_workbook=Path("/tmp/unused-golden.xlsx"),
            computed_perf_path=Path("/tmp/unused-perf.xlsx"),
        )
        checker._erwang_ah_adjustments = adjustments

        mismatches = checker.collect_cell_mismatches(computed, golden)
        self.assertEqual(mismatches, [])
        self.assertTrue(
            hub_parity_skip_erwang_blank_ah(
                "蒲喜",
                "权限结余绩效",
                -747.3054,
                -964.0254,
                adjustments,
            )
        )

    def test_erwang_skip_does_not_apply_without_adjustment(self) -> None:
        join_keys = ["店别", "职务", "姓名"]
        golden = pd.DataFrame(
            [
                {
                    "店别": "武侯DCC",
                    "职务": "销售顾问",
                    "姓名": "刘波",
                    "权限结余绩效": 100.0,
                },
            ]
        )
        computed = golden.copy()
        computed.loc[0, "权限结余绩效"] = 200.0

        checker = CommissionSummaryParity(
            join_keys=join_keys,
            columns=["权限结余绩效"],
        )
        checker._erwang_ah_adjustments = {"蒲喜": -216.72}

        mismatches = checker.collect_cell_mismatches(computed, golden)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0].column, "权限结余绩效")


class ColorLegendTests(unittest.TestCase):
    def test_add_commission_summary_color_legend_inserts_row(self) -> None:
        columns = ["店别", "职务", "姓名", "整车绩效"]
        df = pd.DataFrame(
            [{"店别": "西物", "职务": "销售顾问", "姓名": "张三", "整车绩效": 100.0}]
        )
        builder = CommissionSummaryBuilder(template_columns=columns)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(df, path)

            add_commission_summary_color_legend(path, "提成汇总", insert_at_row=2)

            wb = load_workbook(path)
            ws = wb["提成汇总"]
            self.assertEqual(ws.cell(row=2, column=1).fill.start_color.rgb, GOLDEN_STATIC_FILL_RGB)
            self.assertIn("金标准直接填数", ws.cell(row=2, column=2).value)
            self.assertEqual(
                ws.cell(row=2, column=3).fill.start_color.rgb, MANUAL_DEFERRED_FILL_RGB
            )
            self.assertIn("公式含手工", ws.cell(row=2, column=4).value)
            self.assertEqual(
                ws.cell(row=2, column=5).fill.start_color.rgb, PARITY_MISMATCH_FILL_RGB
            )
            self.assertIn("数值不一致", ws.cell(row=2, column=6).value)
            self.assertEqual(
                ws.cell(row=2, column=7).fill.start_color.rgb, FORMULA_ANOMALY_FILL_RGB
            )
            self.assertIn("公式形态异常", ws.cell(row=2, column=8).value)
            self.assertEqual(normalize_header(ws.cell(row=3, column=1).value), "店别")


if __name__ == "__main__":
    unittest.main()
