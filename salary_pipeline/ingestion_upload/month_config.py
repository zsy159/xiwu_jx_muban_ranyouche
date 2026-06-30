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


def write_month_config(
    month_id: str,
    *,
    sales_workbook: str,
    rules_workbook: str | None = None,
    sales_topology: str,
    rules_topology: str | None = None,
    sheet_sources_file: str | None = None,
    staging: bool = False,
    config_dir: Path | None = None,
) -> Path:
    """
    Write month-YYYY-MM.yaml from month.yaml template.

    Paths are relative to project root. When staging=True, outputs go to
    output/<month>/.staging/ instead of formal output/.
    """
    if not _MONTH_RE.match(month_id):
        raise ValueError(f"Invalid month id: {month_id}")

    template_path = CONFIG_DIR / "month.yaml"
    with template_path.open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    cfg = json.loads(json.dumps(cfg))  # deep copy
    cfg = _patch_month_paths(cfg, month_id)
    cfg["month"] = month_id

    cfg["workbooks"]["sales"] = sales_workbook
    if rules_workbook:
        cfg["workbooks"]["rules"] = rules_workbook
    else:
        # Sales-only upload: reuse sales topology path placeholder for rules
        cfg["workbooks"]["rules"] = sales_workbook

    cfg["topology"]["sales"] = sales_topology
    if rules_topology:
        cfg["topology"]["rules"] = rules_topology
    else:
        cfg["topology"]["rules"] = sales_topology

    if sheet_sources_file:
        cfg["workbooks"]["sheet_sources_file"] = sheet_sources_file
    else:
        cfg["workbooks"].pop("sheet_sources_file", None)

    parity = cfg.setdefault("parity", {})
    if parity.get("golden_workbook"):
        parity["reference_golden_workbook"] = parity["golden_workbook"]
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

    target_dir = config_dir or CONFIG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"month-{month_id}.yaml"
    with out_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, allow_unicode=True, sort_keys=False)
    return out_path


def load_written_month_config(month_id: str, *, staging: bool = False) -> dict[str, Any]:
    path = CONFIG_DIR / f"month-{month_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing config: {path}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)
