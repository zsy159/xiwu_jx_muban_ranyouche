"""Write per-month YAML config for sales-side upload (skip aftersales)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _patch_month_paths(obj: Any, month_id: str) -> Any:
    if isinstance(obj, str) and re.search(r"\d{4}-\d{2}", obj):
        return re.sub(r"\d{4}-\d{2}", month_id, obj)
    if isinstance(obj, dict):
        return {k: _patch_month_paths(v, month_id) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_patch_month_paths(v, month_id) for v in obj]
    return obj


def build_month_config_dict(
    month_id: str,
    *,
    sales_workbook: str,
    rules_workbook: str | None = None,
    sales_topology: str,
    rules_topology: str | None = None,
    aftersales_topology: str | None = None,
    sheet_sources_file: str | None = None,
    staging: bool = False,
    no_golden: bool = False,
) -> dict[str, Any]:
    """
    Assemble month config from month.template.yaml without writing to disk.

    Paths are relative to project root. When staging=True, outputs go to
    output/<month>/.staging/ instead of formal output/.
    """
    if not _MONTH_RE.match(month_id):
        raise ValueError(f"Invalid month id: {month_id}")

    template_path = CONFIG_DIR / "month.template.yaml"
    with template_path.open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    cfg = json.loads(json.dumps(cfg))  # deep copy
    cfg = _patch_month_paths(cfg, month_id)
    cfg["month"] = month_id

    cfg["workbooks"]["sales"] = sales_workbook
    if rules_workbook:
        cfg["workbooks"]["rules"] = rules_workbook
    else:
        # Sales-only upload: reuse sales workbook path for rules
        cfg["workbooks"]["rules"] = sales_workbook

    cfg["topology"]["sales"] = sales_topology
    if rules_topology:
        cfg["topology"]["rules"] = rules_topology
    else:
        cfg["topology"]["rules"] = sales_topology

    if aftersales_topology:
        cfg["topology"]["aftersales"] = aftersales_topology

    if sheet_sources_file:
        cfg["workbooks"]["sheet_sources_file"] = sheet_sources_file
    else:
        cfg["workbooks"].pop("sheet_sources_file", None)

    parity = cfg.setdefault("parity", {})
    if no_golden:
        parity["golden_workbook"] = None
        for channel in ("xw", "direct_store", "cs"):
            if channel in cfg.get("payout", {}):
                cfg["payout"][channel]["golden_workbook"] = None
    else:
        existing_golden = parity.get("golden_workbook")
        if existing_golden:
            parity["reference_golden_workbook"] = existing_golden
        elif not parity.get("reference_golden_workbook"):
            from salary_pipeline.ingestion_upload.default_rules import load_default_rules

            ref = load_default_rules().get("skeleton_reference_workbook")
            if ref:
                parity["reference_golden_workbook"] = ref
        parity["golden_workbook"] = sales_workbook
        for channel in ("xw", "direct_store", "cs"):
            if channel in cfg.get("payout", {}):
                cfg["payout"][channel]["golden_workbook"] = sales_workbook

    perf = cfg.setdefault("performance_sheet", {})
    perf["billing_month"] = month_id

    out_cfg = cfg.setdefault("outputs", {})
    if staging:
        prefix = f"output/{month_id}/.staging"
        out_cfg["cache_dir"] = f"{prefix}/cache"
        out_cfg["commission_summary_file"] = f"{prefix}/提成汇总.xlsx"
        out_cfg["performance_sheet_file"] = f"{prefix}/绩效整理表-系统生成.xlsx"
        out_cfg["report_dir"] = f"{prefix}/reports"
        for key in (
            "aftersales_wuhou",
            "aftersales_airport",
            "xw_payout",
            "direct_store_payout",
            "cs_payout",
        ):
            out_cfg.pop(key, None)
    else:
        prefix = f"output/{month_id}"
        out_cfg["cache_dir"] = f"{prefix}/cache"
        out_cfg["commission_summary_file"] = f"{prefix}/提成汇总.xlsx"
        out_cfg["performance_sheet_file"] = f"{prefix}/绩效整理表-系统生成.xlsx"
        out_cfg["report_dir"] = f"{prefix}/reports"

    return cfg


def persist_month_config(
    month_id: str,
    cfg: dict[str, Any],
    *,
    config_dir: Path | None = None,
) -> Path:
    """Write an assembled month config dict to month-YYYY-MM.yaml."""
    target_dir = config_dir or CONFIG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"month-{month_id}.yaml"
    with out_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, allow_unicode=True, sort_keys=False)
    return out_path


def write_month_config(
    month_id: str,
    *,
    sales_workbook: str,
    rules_workbook: str | None = None,
    sales_topology: str,
    rules_topology: str | None = None,
    aftersales_topology: str | None = None,
    sheet_sources_file: str | None = None,
    staging: bool = False,
    no_golden: bool = False,
    config_dir: Path | None = None,
) -> Path:
    """Write month-YYYY-MM.yaml from month.template.yaml template."""
    cfg = build_month_config_dict(
        month_id,
        sales_workbook=sales_workbook,
        rules_workbook=rules_workbook,
        sales_topology=sales_topology,
        rules_topology=rules_topology,
        aftersales_topology=aftersales_topology,
        sheet_sources_file=sheet_sources_file,
        staging=staging,
        no_golden=no_golden,
    )
    return persist_month_config(month_id, cfg, config_dir=config_dir)


def load_written_month_config(month_id: str, *, staging: bool = False) -> dict[str, Any]:
    path = CONFIG_DIR / f"month-{month_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing config: {path}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)
