"""Parity formula-anomaly Excel annotation tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from openpyxl import load_workbook

from salary_pipeline.calculators.sales_advisor.parity_annotations import (
    HubCellAnnotation,
    annotations_for_workbook,
    collect_hub_cell_annotations,
    load_annotation_registry,
)
from salary_pipeline.pipelines.commission_summary import CommissionSummaryBuilder
from salary_pipeline.utils.excel_format import (
    FORMULA_ANOMALY_FILL_RGB,
    add_commission_summary_annotations,
)


class ParityAnnotationTests(unittest.TestCase):
    def test_load_registry_includes_zhaosifan(self) -> None:
        registry = load_annotation_registry()
        keys = {ann.key() for ann in registry}
        self.assertIn(("赵思梵", "权限结余绩效"), keys)
        zsf = next(a for a in registry if a.name == "赵思梵")
        self.assertIn("LB37822ZXSB207636", zsf.reason)
        self.assertIn("AA×0.4", zsf.reason)

    def test_comment_attached_to_correct_cell(self) -> None:
        ann = HubCellAnnotation(
            name="赵思梵",
            column="权限结余绩效",
            reason="绩效整理表 VIN LB37822ZXSB207636：金标准 AH=AA×0.4，系统 AA×20%",
            golden_value=1484.20,
            computed_value=1474.20,
        )
        df = pd.DataFrame(
            [
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "赵思梵",
                    "权限结余绩效": 1474.20,
                },
                {
                    "店别": "西物",
                    "职务": "销售顾问",
                    "姓名": "刘波",
                    "权限结余绩效": 100.0,
                },
            ]
        )
        builder = CommissionSummaryBuilder(template_columns=list(df.columns))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(df, path)

            applied = add_commission_summary_annotations(path, "提成汇总", [ann])
            self.assertEqual(applied, 1)

            wb = load_workbook(path)
            ws = wb["提成汇总"]
            col = list(df.columns).index("权限结余绩效") + 1
            cell = ws.cell(row=3, column=col)
            self.assertEqual(cell.fill.start_color.rgb, FORMULA_ANOMALY_FILL_RGB)
            self.assertIsNotNone(cell.comment)
            assert cell.comment is not None
            self.assertIn("LB37822ZXSB207636", cell.comment.text)
            self.assertIn("1484.2", cell.comment.text)
            self.assertIn("1474.2", cell.comment.text)

            other = ws.cell(row=4, column=col)
            self.assertNotEqual(
                getattr(other.fill.start_color, "rgb", None),
                FORMULA_ANOMALY_FILL_RGB,
            )

    def test_manual_formula_deferred_excluded_from_annotations(self) -> None:
        deferred = {"韩柏成": frozenset({"保险绩效"})}
        with patch(
            "salary_pipeline.calculators.sales_advisor.parity_annotations.load_annotation_registry",
            return_value=[
                HubCellAnnotation(
                    name="韩柏成",
                    column="保险绩效",
                    reason="SUMIFS+600",
                )
            ],
        ):
            with patch(
                "salary_pipeline.calculators.sales_advisor.parity_annotations.detect_topology_formula_anomalies",
                return_value=[],
            ):
                anns = annotations_for_workbook(deferred_cells=deferred)
        keys = {a.key() for a in anns}
        self.assertNotIn(("韩柏成", "保险绩效"), keys)

    def test_deferred_cells_excluded_from_annotations(self) -> None:
        with patch(
            "salary_pipeline.calculators.sales_advisor.parity_annotations.load_annotation_registry",
            return_value=[
                HubCellAnnotation(
                    name="唐操",
                    column="整车绩效",
                    reason="channel mismatch",
                )
            ],
        ):
            with patch(
                "salary_pipeline.calculators.sales_advisor.parity_annotations.detect_topology_formula_anomalies",
                return_value=[],
            ):
                anns = annotations_for_workbook()
        keys = {a.key() for a in anns}
        self.assertNotIn(("唐操", "整车绩效"), keys)

    def test_collect_merges_registry_over_topology(self) -> None:
        registry_ann = HubCellAnnotation(
            name="测试",
            column="权限结余绩效",
            reason="登记原因",
            source="registry",
        )
        topo_ann = HubCellAnnotation(
            name="测试",
            column="权限结余绩效",
            reason="topology 原因",
            source="topology",
        )
        merged = collect_hub_cell_annotations(
            include_topology=False,
        )
        self.assertTrue(any(a.name == "赵思梵" for a in merged))

        manual = collect_hub_cell_annotations(include_topology=False)
        with patch(
            "salary_pipeline.calculators.sales_advisor.parity_annotations.load_annotation_registry",
            return_value=[registry_ann],
        ):
            with patch(
                "salary_pipeline.calculators.sales_advisor.parity_annotations.detect_topology_formula_anomalies",
                return_value=[topo_ann],
            ):
                result = collect_hub_cell_annotations()
        by_key = {a.key(): a for a in result}
        self.assertEqual(by_key[("测试", "权限结余绩效")].reason, "登记原因")
        self.assertEqual(by_key[("测试", "权限结余绩效")].source, "registry")


if __name__ == "__main__":
    unittest.main()
