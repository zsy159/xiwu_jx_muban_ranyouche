"""Tests for post-export commission summary highlighting."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from salary_pipeline.pipelines.commission_summary import (
    SUMMARY_TEMPLATE_COLUMNS,
    CommissionSummaryBuilder,
)
from salary_pipeline.pipelines.commission_summary_formatting import (
    apply_commission_summary_highlighting,
    resolve_highlight_golden_path,
)
from salary_pipeline.pipelines.non_frontline_columns import apply_non_frontline_columns


class CommissionSummaryFormattingTests(unittest.TestCase):
    def test_resolve_highlight_golden_prefers_reference(self) -> None:
        cfg = {
            "parity": {
                "reference_golden_workbook": "data/raw/2026-05/golden.xlsx",
                "golden_workbook": "upload/sales.xlsx",
            }
        }
        with patch(
            "salary_pipeline.pipelines.commission_summary_formatting.resolve_project_path",
            side_effect=lambda p: Path(str(p)),
        ), patch.object(Path, "exists", return_value=True):
            path = resolve_highlight_golden_path(cfg)
        self.assertEqual(path, Path("data/raw/2026-05/golden.xlsx"))

    def test_export_then_highlight_invokes_formatting(self) -> None:
        from salary_pipeline.pipelines.commission_summary import load_month_config
        from salary_pipeline.paths import CONFIG_DIR

        month_config = load_month_config(CONFIG_DIR)
        summary = pd.DataFrame(
            {
                "序号": [1],
                "店别": ["崇州直营店"],
                "职务": ["销售顾问"],
                "姓名": ["测试顾问"],
                "人数": [1],
                "考核量": [1],
            }
        )
        builder = CommissionSummaryBuilder()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(summary, path)
            with patch(
                "salary_pipeline.pipelines.commission_summary_formatting.add_commission_summary_color_legend",
            ) as legend, patch(
                "salary_pipeline.pipelines.commission_summary_formatting.highlight_commission_summary_mismatches",
                return_value=3,
            ), patch(
                "salary_pipeline.pipelines.commission_summary_formatting.highlight_commission_summary_deferred_cells",
                return_value=5,
            ), patch(
                "salary_pipeline.pipelines.commission_summary_formatting.add_commission_summary_annotations",
                return_value=2,
            ), patch(
                "salary_pipeline.pipelines.commission_summary_formatting.build_reconcile_deferred_cells",
                return_value={},
            ), patch(
                "salary_pipeline.pipelines.commission_summary_formatting.collect_topology_static_fill_cells",
                return_value={},
            ), patch(
                "salary_pipeline.pipelines.commission_summary_formatting.annotations_for_workbook",
                return_value=[],
            ), patch(
                "salary_pipeline.pipelines.commission_summary_formatting.parity_values_for_annotations",
                return_value={},
            ), patch(
                "salary_pipeline.pipelines.commission_summary_formatting.CommissionSummaryParity",
            ) as parity_cls:
                parity_cls.return_value.collect_mismatches_from_files.return_value = []
                stats = apply_commission_summary_highlighting(month_config, path)
            legend.assert_called_once()
            self.assertEqual(stats.mismatches, 3)
            self.assertEqual(stats.deferred, 5)
            self.assertEqual(stats.annotated, 2)

    def test_non_frontline_columns_present_after_export(self) -> None:
        summary = pd.DataFrame(
            {
                "序号": [1],
                "店别": ["财务部"],
                "职务": ["会计"],
                "姓名": ["罗涵"],
                "人数": [1],
                "综合毛利": [742.0],
                "主营单台毛利": [2.0],
                "整车绩效": [2700.0],
                "加装绩效": [1484.0],
            }
        )
        summary = apply_non_frontline_columns(summary)
        builder = CommissionSummaryBuilder()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(summary, path)
            exported = pd.read_excel(path, header=1, nrows=1)
        self.assertEqual(list(exported.columns), SUMMARY_TEMPLATE_COLUMNS)
        self.assertEqual(float(exported.loc[0, "台次"]), 742.0)
        self.assertEqual(float(exported.loc[0, "岗位绩效"]), 2700.0)


if __name__ == "__main__":
    unittest.main()
