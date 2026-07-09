"""Multi-month CLI and pipeline month_config injection tests."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from salary_pipeline.ingestion_upload.month_config import write_month_config
from salary_pipeline.observability.loaders import load_months_registry
from salary_pipeline.paths import PROJECT_ROOT


class MultiMonthCliTest(unittest.TestCase):
    def test_months_registry_has_default_imported_month(self) -> None:
        registry = load_months_registry()
        months = registry.get("months", {})
        self.assertIn("2026-05", months)
        self.assertEqual(months["2026-05"]["config"], "month-2026-05.yaml")
        self.assertEqual(months["2026-05"]["status"], "imported")

    def test_unknown_month_raises_system_exit(self) -> None:
        from salary_pipeline.main import _resolve_month_config

        with self.assertRaises(SystemExit) as ctx:
            _resolve_month_config("2099-12")
        self.assertIn("onboard-month", str(ctx.exception))

    def test_default_month_falls_back_when_registry_empty(self) -> None:
        from salary_pipeline.main import _default_month

        registry = load_months_registry()
        self.assertNotIn("default_month", registry)
        self.assertEqual(_default_month(), "2026-05")

    def test_has_golden_workbook_null(self) -> None:
        from salary_pipeline.main import _has_golden_workbook

        cfg = {"parity": {"golden_workbook": None}, "payout": {"xw": {"golden_workbook": None}}}
        self.assertFalse(_has_golden_workbook(cfg))
        self.assertFalse(_has_golden_workbook(cfg, channel="xw"))

    def test_reconcile_null_golden_skips(self) -> None:
        from salary_pipeline.main import cmd_reconcile

        cfg = _template_config("2026-05")
        cfg = json.loads(json.dumps(cfg))
        cfg["parity"]["golden_workbook"] = None
        args = _namespace(
            month="2026-05",
            computed=None,
            golden=None,
            sheet=None,
            report_dir=None,
            verbose=False,
        )
        with mock.patch("salary_pipeline.main._config_from_args", return_value=cfg):
            rc = cmd_reconcile(args)
        self.assertEqual(rc, 0)

    def test_compute_reconcile_null_golden_skips(self) -> None:
        from salary_pipeline.main import cmd_compute

        cfg = _template_config("2026-02")
        cfg = json.loads(json.dumps(cfg))
        cfg["parity"]["golden_workbook"] = None
        args = _namespace(
            month="2026-05",
            from_stage="full",
            only=None,
            reconcile=True,
            golden=None,
            sheet=None,
            report_dir=None,
            verbose=False,
        )
        fake_result = {
            "output_path": __import__("salary_pipeline.paths", fromlist=["PROJECT_ROOT"]).PROJECT_ROOT
            / "output/test/提成汇总.xlsx",
            "summary": mock.Mock(shape=(1, 1)),
        }
        with mock.patch("salary_pipeline.main._config_from_args", return_value=cfg), mock.patch(
            "salary_pipeline.main.SalesPipeline"
        ) as pipeline_cls:
            pipeline_cls.return_value.run.return_value = fake_result
            rc = cmd_compute(args)
        self.assertEqual(rc, 0)

    def test_pipeline_month_config_injection(self) -> None:
        from salary_pipeline.pipelines.aftersales import AftersalesPipeline
        from salary_pipeline.pipelines.xw_payout import ChannelPayoutPipeline

        cfg = _template_config("2026-02")
        payout = ChannelPayoutPipeline("xw", month_config=cfg)
        self.assertEqual(payout.month_config["month"], "2026-02")
        aftersales = AftersalesPipeline(store="wuhou", month_config=cfg)
        self.assertEqual(aftersales.month_config["month"], "2026-02")

    def test_write_month_config_uses_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / "cfg"
            path = write_month_config(
                "2099-03",
                sales_workbook="data/raw/2099-03/销售账套-合并-2099-03.xlsx",
                sales_topology="data/topology/2099-03/销售账套-合并-2099-03.topology.json",
                staging=True,
                config_dir=cfg_dir,
            )
            self.assertTrue(path.exists())
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("placeholder.xlsx", text)
            self.assertNotIn("燃油车-2026年05月吉利超市售后提成(终)(1)", text)

            cfg = yaml.safe_load(text)
            self.assertEqual(cfg["month"], "2099-03")
            self.assertEqual(
                cfg["workbooks"]["sales"],
                "data/raw/2099-03/销售账套-合并-2099-03.xlsx",
            )
            self.assertEqual(cfg["aftersales"]["stores"]["wuhou"]["golden_workbook"], "")
            self.assertEqual(cfg["topology"]["aftersales"], "")
            self.assertEqual(cfg["performance_sheet"]["billing_month"], "2099-03")

    def test_write_month_config_no_golden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / "cfg"
            path = write_month_config(
                "2099-04",
                sales_workbook="data/raw/2099-04/sales.xlsx",
                sales_topology="data/topology/2026-05/sales.topology.json",
                rules_topology="data/topology/2026-05/rules.topology.json",
                aftersales_topology="data/topology/2026-05/aftersales.topology.json",
                no_golden=True,
                config_dir=cfg_dir,
            )
            cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertIsNone(cfg["parity"]["golden_workbook"])
            for channel in ("xw", "direct_store", "cs"):
                self.assertIsNone(cfg["payout"][channel]["golden_workbook"])
            self.assertEqual(
                cfg["topology"]["sales"],
                "data/topology/2026-05/sales.topology.json",
            )
            self.assertEqual(
                cfg["topology"]["aftersales"],
                "data/topology/2026-05/aftersales.topology.json",
            )

    def test_onboard_inherit_topology_writes_null_golden(self) -> None:
        from salary_pipeline.main import cmd_onboard_month
        from salary_pipeline.paths import CONFIG_DIR as REAL_CONFIG_DIR

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sales = tmp_path / "sales.xlsx"
            sales.write_bytes(b"PK")
            cfg_dir = tmp_path / "cfg"
            cfg_dir.mkdir()
            shutil.copy2(REAL_CONFIG_DIR / "month.template.yaml", cfg_dir / "month.template.yaml")
            out_dir = tmp_path / "output"
            raw_dir = tmp_path / "data" / "raw" / "2099-06"
            topo_dir = tmp_path / "data" / "topology" / "2026-05"
            topo_dir.mkdir(parents=True)
            for name in ("sales", "rules", "aftersales"):
                (topo_dir / f"{name}.topology.json").write_text("{}", encoding="utf-8")

            inherit_cfg = {
                "month": "2026-05",
                "topology": {
                    "sales": "data/topology/2026-05/sales.topology.json",
                    "rules": "data/topology/2026-05/rules.topology.json",
                    "aftersales": "data/topology/2026-05/aftersales.topology.json",
                },
            }

            args = _namespace(
                month="2099-06",
                sales=str(sales),
                rules=None,
                sheet_sources=None,
                label=None,
                extract_topology=False,
                inherit_topology="2026-05",
            )

            with mock.patch("salary_pipeline.main.load_month_config_for", return_value=inherit_cfg), mock.patch(
                "salary_pipeline.main.resolve_project_path",
                side_effect=lambda p: tmp_path / p if not Path(p).is_absolute() else Path(p),
            ), mock.patch("salary_pipeline.main.PROJECT_ROOT", tmp_path), mock.patch(
                "salary_pipeline.ingestion_upload.month_config.PROJECT_ROOT", tmp_path
            ), mock.patch(
                "salary_pipeline.ingestion_upload.month_config.CONFIG_DIR", cfg_dir
            ), mock.patch(
                "salary_pipeline.main.output_month_dir", return_value=out_dir / "2099-06"
            ), mock.patch(
                "salary_pipeline.main.raw_month_dir", return_value=raw_dir
            ), mock.patch("salary_pipeline.main.register_month") as register_mock:
                rc = cmd_onboard_month(args)

            self.assertEqual(rc, 0)
            config_path = cfg_dir / "month-2099-06.yaml"
            self.assertTrue(config_path.exists())
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertIsNone(cfg["parity"]["golden_workbook"])
            self.assertEqual(
                cfg["topology"]["sales"],
                "data/topology/2026-05/sales.topology.json",
            )
            register_mock.assert_called_once()
            self.assertEqual(register_mock.call_args.kwargs["config"], "month-2099-06.yaml")

    def test_onboard_default_uses_canonical_rules(self) -> None:
        from salary_pipeline.main import cmd_onboard_month
        from salary_pipeline.paths import CONFIG_DIR as REAL_CONFIG_DIR

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sales = tmp_path / "sales.xlsx"
            sales.write_bytes(b"PK")
            cfg_dir = tmp_path / "cfg"
            cfg_dir.mkdir()
            shutil.copy2(REAL_CONFIG_DIR / "month.template.yaml", cfg_dir / "month.template.yaml")
            shutil.copy2(REAL_CONFIG_DIR / "default_rules.yaml", cfg_dir / "default_rules.yaml")
            out_dir = tmp_path / "output"
            raw_dir = tmp_path / "data" / "raw" / "2099-08"

            args = _namespace(
                month="2099-08",
                sales=str(sales),
                rules=None,
                sheet_sources=None,
                label=None,
                extract_topology=False,
                inherit_topology=None,
            )

            def _resolve(p: str | Path) -> Path:
                path = Path(p)
                if path.is_absolute():
                    return path
                candidate = tmp_path / path
                if candidate.exists():
                    return candidate
                repo = PROJECT_ROOT / path
                if repo.exists():
                    return repo
                return candidate

            with mock.patch("salary_pipeline.main.resolve_project_path", side_effect=_resolve), mock.patch(
                "salary_pipeline.main.PROJECT_ROOT", tmp_path
            ), mock.patch(
                "salary_pipeline.ingestion_upload.month_config.PROJECT_ROOT", tmp_path
            ), mock.patch(
                "salary_pipeline.ingestion_upload.month_config.CONFIG_DIR", cfg_dir
            ), mock.patch(
                "salary_pipeline.ingestion_upload.default_rules.CONFIG_DIR", cfg_dir
            ), mock.patch(
                "salary_pipeline.main.output_month_dir", return_value=out_dir / "2099-08"
            ), mock.patch(
                "salary_pipeline.main.raw_month_dir", return_value=raw_dir
            ), mock.patch("salary_pipeline.main.register_month") as register_mock:
                rc = cmd_onboard_month(args)

            self.assertEqual(rc, 0)
            config_path = cfg_dir / "month-2099-08.yaml"
            self.assertTrue(config_path.exists())
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertIsNone(cfg["parity"]["golden_workbook"])
            self.assertIn("2026-05", cfg["topology"]["sales"])
            self.assertIn("2026-05", cfg["topology"]["rules"])
            self.assertIn("2026-05", cfg["topology"]["aftersales"])
            register_mock.assert_called_once()

    def test_onboard_mutually_exclusive_flags(self) -> None:
        from salary_pipeline.main import cmd_onboard_month

        sales = PROJECT_ROOT / "dummy-test-sales.xlsx"
        sales.write_bytes(b"PK")
        try:
            args = _namespace(
                month="2099-07",
                sales="dummy-test-sales.xlsx",
                rules=None,
                sheet_sources=None,
                label=None,
                extract_topology=True,
                inherit_topology="2026-05",
            )
            rc = cmd_onboard_month(args)
            self.assertEqual(rc, 1)
        finally:
            sales.unlink(missing_ok=True)


class DefaultRulesTest(unittest.TestCase):
    def test_canonical_topology_paths_exist(self) -> None:
        from salary_pipeline.ingestion_upload.default_rules import (
            canonical_topology,
            validate_topology_paths,
        )

        topo = canonical_topology()
        errors = validate_topology_paths(topo)
        self.assertEqual(errors, [], msg=f"topology errors: {errors}")
        self.assertIn("2026-05", topo["sales"])
        self.assertIn("提成依据", topo["rules"])

    def test_default_rule_mode_label(self) -> None:
        from salary_pipeline.app.onboard_helpers import default_rule_mode_label

        label = default_rule_mode_label()
        self.assertIn("2026-05", label)


def _template_config(month_id: str) -> dict:
    template_path = PROJECT_ROOT / "salary_pipeline" / "config" / "month.template.yaml"
    cfg = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    cfg["month"] = month_id
    cfg.setdefault("parity", {})["golden_workbook"] = None
    for channel in ("xw", "direct_store", "cs"):
        cfg.setdefault("payout", {}).setdefault(channel, {})["golden_workbook"] = None
    return cfg


def _namespace(**kwargs: object) -> mock.Mock:
    ns = mock.Mock()
    for key, value in kwargs.items():
        setattr(ns, key, value)
    return ns


if __name__ == "__main__":
    unittest.main()
