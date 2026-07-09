"""Tests for post-export commission summary highlighting."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from salary_pipeline.paths import PROJECT_ROOT
from salary_pipeline.pipelines.commission_summary import (
    SUMMARY_TEMPLATE_COLUMNS,
    CommissionSummaryBuilder,
)
from salary_pipeline.pipelines.commission_summary_formatting import (
    apply_commission_summary_highlighting,
    parity_highlight_mode,
    resolve_highlight_golden_path,
)
from salary_pipeline.pipelines.non_frontline_columns import apply_non_frontline_columns


class CommissionSummaryFormattingTests(unittest.TestCase):
    def test_parity_highlight_mode_defaults_to_mismatch_only(self) -> None:
        self.assertEqual(parity_highlight_mode({}), "mismatch_only")
        self.assertEqual(
            parity_highlight_mode({"highlight_mode": "full"}),
            "full",
        )
        self.assertEqual(
            parity_highlight_mode({"skip_root_cause": True}),
            "mismatch_only",
        )
        self.assertEqual(
            parity_highlight_mode({"lightweight_highlight": True}),
            "mismatch_only",
        )

    def test_resolve_highlight_golden_prefers_reference(self) -> None:
        cfg = {
            "parity": {
                "reference_golden_workbook": "data/raw/2026-05/golden.xlsx",
                "golden_workbook": "upload/sales.xlsx",
            }
        }
        ref = Path("data/raw/2026-05/golden.xlsx")
        with patch(
            "salary_pipeline.data_ingestion.data_loader.resolve_parity_golden_workbook",
            return_value=ref,
        ):
            path = resolve_highlight_golden_path(cfg)
        self.assertEqual(path, ref)

    def test_export_then_highlight_invokes_formatting(self) -> None:
        from salary_pipeline.pipelines.commission_summary import load_month_config
        from salary_pipeline.paths import CONFIG_DIR

        month_config = load_month_config(CONFIG_DIR)
        month_config = {
            **month_config,
            "parity": {**month_config["parity"], "highlight_mode": "full"},
        }
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
                stats = apply_commission_summary_highlighting(
                    month_config, path, golden_path=path
                )
            legend.assert_called_once()
            self.assertEqual(stats.mismatches, 3)
            self.assertEqual(stats.deferred, 5)
            self.assertEqual(stats.annotated, 2)

    def test_resolve_highlight_golden_skips_upload_merge_without_hub_sheet(self) -> None:
        cfg = {
            "parity": {"golden_workbook": "data/raw/2026-04/销售账套-合并-2026-04.xlsx"},
            "workbooks": {"sales": "data/raw/2026-04/销售账套-合并-2026-04.xlsx"},
            "outputs": {"commission_summary_sheet": "提成汇总"},
        }
        canonical = Path("data/raw/2026-05/燃油车-2026年05月西物超市销售提成(终)(1).xlsx")
        with patch(
            "salary_pipeline.data_ingestion.data_loader.resolve_project_path",
            side_effect=lambda p: Path(str(p)),
        ), patch(
            "salary_pipeline.data_ingestion.data_loader.workbook_has_sheet",
            side_effect=lambda path, sheet: path == canonical,
        ), patch(
            "salary_pipeline.data_ingestion.data_loader.resolve_canonical_skeleton_workbook",
            return_value=canonical,
        ):
            path = resolve_highlight_golden_path(cfg)
        self.assertEqual(path, canonical)

    def test_trial_highlight_with_merged_upload_does_not_read_hub_from_upload(self) -> None:
        merged = PROJECT_ROOT / "data/raw/2026-05/销售账套-合并-2026-05.xlsx"
        if not merged.exists():
            self.skipTest("merged workbook not available")

        from salary_pipeline.ingestion_upload.month_config import write_month_config

        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config"
            config_path = write_month_config(
                "2026-05",
                sales_workbook=str(merged.relative_to(PROJECT_ROOT)),
                sales_topology="data/topology/2026-05/销售账套-合并-2026-05.topology.json",
                staging=True,
                config_dir=config_dir,
            )
            import yaml

            month_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertTrue(month_config["parity"].get("reference_golden_workbook"))

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
            computed = Path(tmp) / "提成汇总.xlsx"
            builder.export_excel(summary, computed)

            with patch(
                "salary_pipeline.pipelines.commission_summary_formatting.add_commission_summary_color_legend",
            ), patch(
                "salary_pipeline.pipelines.commission_summary_formatting.highlight_commission_summary_mismatches",
                return_value=0,
            ), patch(
                "salary_pipeline.pipelines.commission_summary_formatting.CommissionSummaryParity",
            ) as parity_cls:
                parity_cls.return_value.collect_mismatches_from_files.return_value = []
                stats = apply_commission_summary_highlighting(month_config, computed)
            self.assertEqual(stats.mismatches, 0)
            golden_arg = parity_cls.return_value.collect_mismatches_from_files.call_args[0][1]
            self.assertNotEqual(golden_arg.resolve(), merged.resolve())

    def test_lightweight_highlight_skips_static_gray(self) -> None:
        columns = ["店别", "职务", "姓名", "整车毛利"]
        df = pd.DataFrame(
            [{"店别": "西物", "职务": "销售顾问", "姓名": "张三", "整车毛利": 101.0}]
        )
        builder = CommissionSummaryBuilder(template_columns=columns)
        month_config = {
            "outputs": {"commission_summary_sheet": "提成汇总"},
            "parity": {
                "auto_highlight": True,
                "highlight_mode": "mismatch_only",
                "header_row": 2,
                "data_start_row": 3,
                "join_keys": ["店别", "职务", "姓名"],
                "columns": ["整车毛利"],
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            computed = Path(tmp) / "computed.xlsx"
            golden = Path(tmp) / "golden.xlsx"
            builder.export_excel(df, computed)
            builder.export_excel(df, golden)

            with patch(
                "salary_pipeline.pipelines.commission_summary_formatting.enrich_cell_mismatches",
                side_effect=AssertionError("enrich_cell_mismatches should not run"),
            ) as enrich, patch(
                "salary_pipeline.pipelines.commission_summary_formatting.highlight_commission_summary_deferred_cells",
                return_value=2,
            ) as deferred, patch(
                "salary_pipeline.pipelines.commission_summary_formatting.highlight_manual_hub_columns",
                return_value=0,
            ) as manual, patch(
                "salary_pipeline.pipelines.commission_summary_formatting.add_commission_summary_annotations",
                side_effect=AssertionError("annotations should not run"),
            ) as annotations, patch(
                "salary_pipeline.pipelines.commission_summary_formatting.add_commission_summary_color_legend",
            ), patch(
                "salary_pipeline.pipelines.commission_summary_formatting.CommissionSummaryParity",
            ) as parity_cls, patch(
                "salary_pipeline.pipelines.commission_summary_formatting.highlight_commission_summary_mismatches",
                return_value=1,
            ):
                parity_cls.return_value.collect_mismatches_from_files.return_value = []
                stats = apply_commission_summary_highlighting(
                    month_config,
                    computed,
                    golden_path=golden,
                )

            enrich.assert_not_called()
            deferred.assert_not_called()
            manual.assert_not_called()
            annotations.assert_not_called()
            self.assertEqual(stats.mismatches, 1)
            self.assertEqual(stats.deferred, 0)
            self.assertEqual(stats.annotated, 0)

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
            exported = pd.read_excel(path, header=2, nrows=1)
        self.assertEqual(list(exported.columns), SUMMARY_TEMPLATE_COLUMNS)
        self.assertEqual(float(exported.loc[0, "台次"]), 742.0)
        self.assertEqual(float(exported.loc[0, "岗位绩效"]), 2700.0)


if __name__ == "__main__":
    unittest.main()
