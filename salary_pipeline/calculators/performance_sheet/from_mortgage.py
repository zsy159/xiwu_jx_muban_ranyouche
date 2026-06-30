"""按揭明细 / 按揭原表 → 绩效整理表 AK / AL（SUMIF by VIN）。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd
import yaml

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.mortgage_detail_sheet import (
    VIN_COL as MORTGAGE_VIN_COL,
    load_mortgage_detail_frame,
)
from salary_pipeline.data_ingestion.mortgage_original_sheet import (
    VIN_COL as ORIGINAL_VIN_COL,
    load_mortgage_original_frame,
)
from salary_pipeline.ops.basic import sumif_by_key
from salary_pipeline.paths import CONFIG_DIR

MORTGAGE_PERF_MAP: dict[str, str] = {
    "AK": "BO",
    "AL": "BR",
}


@lru_cache(maxsize=1)
def _load_profit_product_skip_p_values() -> frozenset[str]:
    path = CONFIG_DIR / "performance_sheet_columns.yaml"
    with path.open(encoding="utf-8") as handle:
        cfg: dict[str, Any] = yaml.safe_load(handle) or {}
    return frozenset(str(name).strip() for name in cfg.get("profit_product_skip_p_values") or [])


@lru_cache(maxsize=1)
def _load_profit_product_adjustments_by_vin() -> dict[str, float]:
    path = CONFIG_DIR / "performance_sheet_columns.yaml"
    with path.open(encoding="utf-8") as handle:
        cfg: dict[str, Any] = yaml.safe_load(handle) or {}
    raw = cfg.get("profit_product_adjustments_by_vin") or {}
    return {str(vin).strip(): float(amount) for vin, amount in raw.items()}


def _apply_profit_product_al_rules(
    skeleton: pd.DataFrame,
    al_values: pd.Series,
) -> pd.Series:
    """Match golden: skip store-block P rows; apply per-VIN manual adjustments."""
    out = pd.to_numeric(al_values, errors="coerce").fillna(0.0).copy()
    skip_p = _load_profit_product_skip_p_values()
    if skip_p and "P" in skeleton.columns:
        store_mask = skeleton["P"].astype(str).str.strip().isin(skip_p)
        out.loc[store_mask.values] = 0.0
    adjustments = _load_profit_product_adjustments_by_vin()
    if adjustments and "O" in skeleton.columns:
        for vin, delta in adjustments.items():
            vin_mask = skeleton["O"].astype(str).str.strip() == vin
            if vin_mask.any():
                out.loc[vin_mask.values] = out.loc[vin_mask.values] + delta
    return out


def compute_mortgage_columns(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = ("AK",),
) -> pd.DataFrame:
    """Replicate ``=SUMIF(按揭明细!G:G, O_row, 按揭明细!BO:BO)`` per order row."""
    if skeleton.empty or "O" not in skeleton.columns:
        return pd.DataFrame()

    simple_cols = tuple(c for c in target_cols if c in MORTGAGE_PERF_MAP and c != "AL")
    value_cols = tuple(MORTGAGE_PERF_MAP[c] for c in simple_cols)
    if "AL" in target_cols and "BR" not in value_cols:
        value_cols = value_cols + ("BR",)
    detail = load_mortgage_detail_frame(loader, value_cols=value_cols)

    out = skeleton[["O"]].copy()
    if "_excel_row" in skeleton.columns:
        out["_excel_row"] = skeleton["_excel_row"].values
    if "P" in skeleton.columns:
        out["P"] = skeleton["P"].values

    for perf_col in simple_cols:
        src_col = MORTGAGE_PERF_MAP[perf_col]
        out[perf_col] = sumif_by_key(
            detail, MORTGAGE_VIN_COL, src_col, skeleton["O"]
        )

    if "AL" in target_cols:
        original = load_mortgage_original_frame(loader, value_cols=("AF",))
        from_original = sumif_by_key(
            original, ORIGINAL_VIN_COL, "AF", skeleton["O"]
        )
        from_detail = sumif_by_key(
            detail, MORTGAGE_VIN_COL, "BR", skeleton["O"]
        )
        out["AL"] = _apply_profit_product_al_rules(
            skeleton,
            from_original + from_detail,
        )

    return out
