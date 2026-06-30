"""Enrich 绩效整理表 skeleton with closure prerequisite columns from detail inputs."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd
import yaml

from salary_pipeline.data_ingestion.closure_input_sheets import (
    load_comparison_table_frame,
    load_system_excess_frame,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.mortgage_original_sheet import (
    VIN_COL as MORTGAGE_ORIGINAL_VIN_COL,
    load_mortgage_original_frame,
)
from salary_pipeline.data_ingestion.system_sales_gross_sheet import (
    CHANNEL_COL,
    DECORATION_FLOOR_COL,
    DEPARTMENT_COL,
    ORDER_CONTEXT_COLS,
    ORDER_TOTAL_COL,
    VEHICLE_TYPE_COL,
    VIN_COL,
    load_system_sales_gross_frame,
)
from salary_pipeline.ops.basic import sumif_by_key
from salary_pipeline.ops.lookup import lookup_match_index
from salary_pipeline.paths import CONFIG_DIR


@lru_cache(maxsize=1)
def _load_manager_permission_by_vin() -> dict[str, float]:
    """VIN → 经理权限 X；金标准无公式，样本月为手工常数 1000。"""
    path = CONFIG_DIR / "performance_sheet_columns.yaml"
    with path.open(encoding="utf-8") as handle:
        cfg: dict[str, Any] = yaml.safe_load(handle) or {}
    raw = cfg.get("manager_permission_by_vin") or {}
    return {str(vin).strip(): float(amount) for vin, amount in raw.items()}


def _channel_label(dept: str, channel: str) -> str:
    """Replicate 绩效整理表 ``D`` from ``A`` + ``I``."""
    if "直营店" in str(dept):
        if channel in (
            "直营店",
            "店面特价",
            "国际车展",
            "按揭专享",
            "国际车展按揭专享",
        ):
            return "直营店店面"
        if channel in ("直营店二网", "重点经销商"):
            return "直营店二网"
        return ""
    text = str(dept)
    return text[-3:] if len(text) >= 3 else text


def enrich_order_context(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
) -> pd.DataFrame:
    """
    Add columns used by closure formulas: H/I/R/L/S/A/D and V/Y/Z/AA chain.

    Sources:
    - ``系统销售毛利`` BL/AO/BQ/D/E by VIN
    - ``比对表`` A from R
    - ``系统超额`` V; ``按揭原表`` Z → Y/AA
    """
    if skeleton.empty or "O" not in skeleton.columns:
        return skeleton.copy()

    out = skeleton.copy()
    sg = load_system_sales_gross_frame(loader, value_cols=ORDER_CONTEXT_COLS)
    sg = sg.drop_duplicates(VIN_COL, keep="first")
    sg_map = sg.set_index(VIN_COL)
    vins = out["O"].astype(str).str.strip()

    out["H"] = vins.map(sg_map[VEHICLE_TYPE_COL])
    out["I"] = vins.map(sg_map[CHANNEL_COL])
    out["R"] = vins.map(sg_map[DEPARTMENT_COL])
    out["L"] = pd.to_numeric(vins.map(sg_map[ORDER_TOTAL_COL]), errors="coerce")
    out["S"] = pd.to_numeric(vins.map(sg_map[DECORATION_FLOOR_COL]), errors="coerce")

    comparison = load_comparison_table_frame(loader)
    dept_to_summary = dict(
        zip(
            comparison["A"].astype(str).str.strip(),
            comparison["B"].astype(str).str.strip(),
        )
    )
    out["A"] = out["R"].astype(str).str.strip().map(dept_to_summary)
    out["D"] = [
        _channel_label(a, i) for a, i in zip(out["A"], out["I"], strict=True)
    ]

    excess = load_system_excess_frame(loader)
    out["V"] = lookup_match_index(out["O"], excess["W"], excess["P"])
    original = load_mortgage_original_frame(loader, value_cols=("AN",))
    out["Z"] = sumif_by_key(
        original, MORTGAGE_ORIGINAL_VIN_COL, "AN", out["O"]
    )
    perm = _load_manager_permission_by_vin()
    out["X"] = vins.map(perm).fillna(0.0).astype(float)
    out["Y"] = out["V"] + out["X"]
    out["AA"] = out.apply(
        lambda row: 0.0
        if pd.notna(row["Z"]) and float(row["Z"]) != 0
        else float(row["Y"]) - float(row["Z"] or 0),
        axis=1,
    )
    return out
