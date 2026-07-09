"""Tests for 绩效整理表 path resolution (财务确认版 vs 系统生成)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from salary_pipeline.app.finance_adjust_helpers import (
    build_perf_editor_column_config,
    load_performance_sheet_for_edit,
)
from salary_pipeline.pipelines.performance_sheet_export import export_computed_performance_sheet
from salary_pipeline.pipelines.performance_sheet_formatting import (
    add_performance_sheet_color_legend,
)
from salary_pipeline.pipelines.performance_sheet_paths import (
    CONFIRMED_PERF_FILENAME,
    SYSTEM_PERF_FILENAME,
    load_performance_sheet_frame,
    load_resolved_performance_frame,
    resolve_confirmed_performance_sheet_path,
    resolve_performance_sheet_path,
    resolve_system_performance_sheet_path,
)


def _month_config(base: Path) -> dict:
    return {
        "month": "2099-01",
        "outputs": {
            "commission_summary_file": str(base / "提成汇总.xlsx"),
            "performance_sheet_file": str(base / SYSTEM_PERF_FILENAME),
        },
    }


class PerformanceSheetPathsTest(unittest.TestCase):
    def test_resolve_returns_system_when_only_system_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = _month_config(base)
            system = resolve_system_performance_sheet_path(cfg)
            export_computed_performance_sheet(
                pd.DataFrame({"P": ["张三"], "AG": [100.0]}),
                system,
                title="test",
            )
            resolved = resolve_performance_sheet_path(cfg)
            self.assertEqual(resolved, system)
            self.assertTrue(resolved.exists())

    def test_resolve_prefers_confirmed_when_both_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = _month_config(base)
            system = resolve_system_performance_sheet_path(cfg)
            confirmed = resolve_confirmed_performance_sheet_path(cfg)
            export_computed_performance_sheet(
                pd.DataFrame({"P": ["系统"], "AG": [1.0]}),
                system,
                title="system",
            )
            export_computed_performance_sheet(
                pd.DataFrame({"P": ["财务"], "AG": [99.0]}),
                confirmed,
                title="confirmed",
            )
            resolved = resolve_performance_sheet_path(cfg)
            self.assertEqual(resolved, confirmed)
            frame = load_performance_sheet_frame(resolved)
            self.assertEqual(frame.loc[0, "P"], "财务")

    def test_load_resolved_performance_frame_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = _month_config(base)
            fallback = pd.DataFrame({"P": ["缓存"], "AG": [5.0]})
            self.assertIs(load_resolved_performance_frame(cfg, fallback), fallback)

    def test_load_resolved_reads_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = _month_config(base)
            confirmed = resolve_confirmed_performance_sheet_path(cfg)
            export_computed_performance_sheet(
                pd.DataFrame({"P": ["财务"], "AG": [42.0]}),
                confirmed,
                title="confirmed",
            )
            frame = load_resolved_performance_frame(cfg)
            assert frame is not None
            self.assertEqual(frame.loc[0, "AG"], 42.0)

    def test_load_frame_after_reconcile_legend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = _month_config(base)
            system = resolve_system_performance_sheet_path(cfg)
            export_computed_performance_sheet(
                pd.DataFrame({"P": ["张三"], "O": ["VIN1"], "AG": [100.0]}),
                system,
                title="test",
            )
            self.assertTrue(add_performance_sheet_color_legend(system))
            frame = load_performance_sheet_frame(system)
            self.assertEqual(frame.loc[0, "P"], "张三")
            self.assertEqual(frame.loc[0, "AG"], 100.0)

    def test_finance_edit_loads_export_header_row_not_source_row(self) -> None:
        """Finance page must not use header=1 (row2 source annotations → all None)."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = _month_config(base)
            system = resolve_system_performance_sheet_path(cfg)
            export_computed_performance_sheet(
                pd.DataFrame(
                    {
                        "G": ["ORD1"],
                        "O": ["VIN123"],
                        "P": ["张三"],
                        "K": [1],
                        "AG": [888.0],
                    }
                ),
                system,
                title="test",
            )
            df, path, label = load_performance_sheet_for_edit(cfg)
            self.assertEqual(label, "system")
            self.assertIsNotNone(df)
            assert df is not None
            self.assertIn("销售顾问", df.columns)
            self.assertEqual(df.loc[0, "销售顾问"], "张三")
            self.assertEqual(df.loc[0, "单台绩效"], 888.0)


class FinanceAdjustColumnConfigTest(unittest.TestCase):
    def test_build_perf_editor_column_config_types_and_width(self) -> None:
        df = pd.DataFrame({"P": ["张三", "李四"], "AG": [100.0, 200.0]})
        config = build_perf_editor_column_config(df)
        self.assertEqual(config["P"]["type_config"]["type"], "text")
        self.assertEqual(config["AG"]["type_config"]["type"], "number")
        self.assertEqual(config["P"]["width"], 132)
        self.assertEqual(config["AG"]["width"], 132)


if __name__ == "__main__":
    unittest.main()
