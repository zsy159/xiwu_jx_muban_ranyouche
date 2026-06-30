from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from salary_pipeline.modules.base import SUMMARY_KEY_COLUMNS, ModuleResult
from salary_pipeline.pipelines.run_cache import (
    cache_is_valid,
    compute_input_fingerprint,
    load_hub_snapshot,
    normalize_overlay_key,
    read_manifest,
    resolve_cache_dir,
    save_hub_snapshot,
    write_manifest,
)
from salary_pipeline.pipelines.sales import (
    PERFORMANCE_OVERLAY_REGISTRY,
    SalesPipeline,
)


def _minimal_month_config(tmp: Path) -> dict:
    sales = tmp / "sales.xlsx"
    topo = tmp / "sales.topology.json"
    sales.write_bytes(b"sales-v1")
    topo.write_bytes(b"topo-v1")
    return {
        "workbooks": {"sales": str(sales)},
        "topology": {"sales": str(topo)},
        "outputs": {
            "commission_summary_file": str(tmp / "out" / "提成汇总.xlsx"),
            "cache_dir": str(tmp / "cache"),
        },
        "performance_sheet": {"use_computed": True},
        "hub": {"bootstrap_from_golden": False},
    }


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_changes_when_topology_changes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = _minimal_month_config(tmp)
            fp1 = compute_input_fingerprint(cfg)

            topo_path = Path(cfg["topology"]["sales"])
            topo_path.write_bytes(b"topo-v2")
            fp2 = compute_input_fingerprint(cfg)

            self.assertNotEqual(
                fp1["topology.sales"],
                fp2["topology.sales"],
            )

    def test_fingerprint_sensitive_to_performance_sheet_columns(self) -> None:
        from salary_pipeline.paths import CONFIG_DIR

        cfg_path = CONFIG_DIR / "performance_sheet_columns.yaml"
        original = cfg_path.read_bytes()
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                cfg = _minimal_month_config(tmp)
                fp1 = compute_input_fingerprint(cfg)
                cfg_path.write_bytes(original + b"\n# touch")
                fp2 = compute_input_fingerprint(cfg)
                self.assertNotEqual(
                    fp1["config.performance_sheet_columns"],
                    fp2["config.performance_sheet_columns"],
                )
        finally:
            cfg_path.write_bytes(original)


class SnapshotRoundtripTests(unittest.TestCase):
    def test_save_and_load_hub_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache_dir = Path(td)
            summary = pd.DataFrame(
                {
                    "店别": ["A店"],
                    "职务": ["销售顾问"],
                    "姓名": ["张三"],
                    "整车绩效": [100.0],
                }
            )
            perf = pd.DataFrame({"订单号": ["VIN1"], "顾问": ["张三"], "整车绩效": [50.0]})

            artifacts = save_hub_snapshot(cache_dir, summary, perf)
            loaded_summary, loaded_perf = load_hub_snapshot(cache_dir)

            pd.testing.assert_frame_equal(
                summary.reset_index(drop=True),
                loaded_summary.reset_index(drop=True),
            )
            pd.testing.assert_frame_equal(
                perf.reset_index(drop=True),
                loaded_perf.reset_index(drop=True),
            )
            self.assertIn("hub_pre_overlay", artifacts)
            self.assertIn("computed_perf_frame", artifacts)


class CacheValidityTests(unittest.TestCase):
    def test_cache_is_valid_when_fingerprint_matches(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = _minimal_month_config(tmp)
            cache_dir = resolve_cache_dir(cfg)
            summary = pd.DataFrame({"店别": ["A"], "职务": ["X"], "姓名": ["Y"]})
            artifacts = save_hub_snapshot(cache_dir, summary, pd.DataFrame())
            fp = compute_input_fingerprint(cfg)
            write_manifest(cache_dir, fp, stage="hub", artifacts=artifacts)

            manifest = read_manifest(cache_dir)
            valid, reason = cache_is_valid(manifest, fp, cache_dir=cache_dir)
            self.assertTrue(valid, reason)

    def test_cache_invalid_when_config_hash_changes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = _minimal_month_config(tmp)
            cache_dir = resolve_cache_dir(cfg)
            summary = pd.DataFrame({"店别": ["A"], "职务": ["X"], "姓名": ["Y"]})
            artifacts = save_hub_snapshot(cache_dir, summary, pd.DataFrame())
            fp = compute_input_fingerprint(cfg)
            write_manifest(cache_dir, fp, stage="hub", artifacts=artifacts)
            manifest = read_manifest(cache_dir)

            Path(cfg["topology"]["sales"]).write_bytes(b"changed")
            new_fp = compute_input_fingerprint(cfg)
            valid, reason = cache_is_valid(manifest, new_fp, cache_dir=cache_dir)
            self.assertFalse(valid)
            self.assertIn("topology.sales", reason)

    def test_cache_invalid_without_manifest(self) -> None:
        fp = {"workbooks.sales": "x"}
        valid, reason = cache_is_valid(None, fp)
        self.assertFalse(valid)
        self.assertIn("manifest", reason)


class OverlayKeyTests(unittest.TestCase):
    def test_normalize_aliases(self) -> None:
        self.assertEqual(normalize_overlay_key("sales_advisor"), "sales-advisor")
        self.assertEqual(normalize_overlay_key("new_media"), "new-media")


class SalesPipelineOnlyFilterTests(unittest.TestCase):
    def test_only_filter_runs_single_overlay(self) -> None:
        keys = [k for k, _ in PERFORMANCE_OVERLAY_REGISTRY]
        self.assertIn("sales-advisor", keys)

        summary = pd.DataFrame(
            [
                {
                    "店别": "A店",
                    "职务": "销售顾问",
                    "姓名": "张三",
                    "整车绩效": 0.0,
                    "加装绩效": 0.0,
                }
            ]
        )
        perf = pd.DataFrame()

        advisor_metrics = pd.DataFrame(
            {
                "店别": ["A店"],
                "职务": ["销售顾问"],
                "姓名": ["张三"],
                "整车绩效": [999.0],
            }
        )
        advisor_result = ModuleResult(
            module_name="sales_advisor_performance",
            roles=["销售顾问"],
            metrics=advisor_metrics,
        )

        other_result = ModuleResult(
            module_name="new_media_performance",
            roles=["新媒体"],
            metrics=pd.DataFrame(columns=SUMMARY_KEY_COLUMNS),
        )

        pipeline = SalesPipeline.__new__(SalesPipeline)
        pipeline.month_config = {
            "outputs": {
                "commission_summary_file": "/tmp/out.xlsx",
                "commission_summary_sheet": "提成汇总",
                "report_dir": "/tmp/reports",
            }
        }
        pipeline.summary_builder = MagicMock()
        pipeline.summary_builder.export_excel = MagicMock()

        def fake_runner(ctx: dict) -> ModuleResult:
            if ctx.get("_overlay_key") == "sales-advisor":
                return advisor_result
            return other_result

        registry = [
            ("new-media", lambda ctx: fake_runner({**ctx, "_overlay_key": "new-media"})),
            (
                "sales-advisor",
                lambda ctx: fake_runner({**ctx, "_overlay_key": "sales-advisor"}),
            ),
        ]

        with patch(
            "salary_pipeline.pipelines.sales.load_hub_snapshot",
            return_value=(summary.copy(), perf),
        ), patch(
            "salary_pipeline.pipelines.sales.PERFORMANCE_OVERLAY_REGISTRY",
            registry,
        ):
            result = pipeline.run(from_stage="hub", only=["sales-advisor"])

        ran_modules = [m.module_name for m in result["module_results"]]
        self.assertEqual(ran_modules, ["sales_advisor_performance"])
        self.assertEqual(result["summary"].loc[0, "整车绩效"], 999.0)
        pipeline.summary_builder.export_excel.assert_called_once()


class ResolveCacheDirTests(unittest.TestCase):
    def test_fallback_to_commission_parent_cache(self) -> None:
        cfg = {
            "outputs": {
                "commission_summary_file": "output/2026-05/提成汇总.xlsx",
            }
        }
        cache_dir = resolve_cache_dir(cfg)
        self.assertTrue(str(cache_dir).endswith("output/2026-05/cache"))

    def test_explicit_cache_dir(self) -> None:
        cfg = {"outputs": {"cache_dir": "output/custom/cache"}}
        self.assertEqual(
            resolve_cache_dir(cfg).name,
            "cache",
        )


if __name__ == "__main__":
    unittest.main()
