"""Populate semantic columns for 非一线 rows (management + support tiers)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from salary_pipeline.calculators.non_frontline.classification import (
    all_semantic_columns,
    column_mapping_for_tier,
    non_frontline_tier,
    load_non_frontline_config,
)

logger = logging.getLogger(__name__)

_JOIN_KEYS = ("店别", "职务", "姓名")


def bootstrap_non_frontline_physical_columns(
    summary: pd.DataFrame,
    golden_workbook: Path | None,
    *,
    sheet_name: str = "提成汇总",
    header_row: int = 2,
    data_start_row: int = 3,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """No-op: golden bootstrap removed — non-frontline cells stay computed or empty."""
    return summary


def apply_non_frontline_columns(
    summary: pd.DataFrame,
    *,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Copy physical hub columns into tier-specific semantic columns.

    For matched non-frontline rows, copied physical columns are cleared so the
    exported workbook shows values only in semantic columns. Hub cache is saved
    before this step, so formula replay / SUMIF parity is unaffected.
    """
    if summary.empty:
        return summary

    cfg = config or load_non_frontline_config()
    out = summary.copy()

    for semantic_col in all_semantic_columns(config=cfg):
        if semantic_col not in out.columns:
            out[semantic_col] = pd.NA

    filled = 0
    cleared = 0
    tier_rows = {"management": 0, "support": 0}
    for idx, row in out.iterrows():
        tier = non_frontline_tier(row.get("店别"), row.get("职务"), config=cfg)
        if tier is None:
            continue
        tier_rows[tier] += 1
        mapping = column_mapping_for_tier(tier, config=cfg)
        for hub_col, semantic_col in mapping.items():
            if hub_col not in out.columns:
                continue
            val = row.get(hub_col)
            if pd.notna(val):
                out.at[idx, semantic_col] = val
                out.at[idx, hub_col] = pd.NA
                filled += 1
                cleared += 1

    logger.info(
        "Non-frontline semantic columns: %s cells copied, %s physical cleared "
        "(management=%s, support=%s rows)",
        filled,
        cleared,
        tier_rows["management"],
        tier_rows["support"],
    )
    return out


def non_frontline_preview_columns() -> list[str]:
    """All semantic columns for upload preview / generated 提成汇总."""
    return all_semantic_columns()
