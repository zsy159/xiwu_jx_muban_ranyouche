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
from salary_pipeline.data_ingestion.data_loader import (
    filter_comparable_rows,
    read_golden_summary_sheet,
    summary_frame_from_builder,
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
    """Fill non-frontline physical hub columns from golden when Hub/bootstrap left them empty.

    Support rows (M–U) and management manual W/Y cells are mostly hand-filled in golden;
    ``HubFormulaEngine`` only evaluates topology formulas and skips columns outside
    ``HUB_COLUMN_MAP``. This runs before semantic migration so ``apply_non_frontline_columns``
    can copy values into 岗位绩效 / 台次 / etc.
    """
    if summary.empty or golden_workbook is None or not golden_workbook.exists():
        return summary

    cfg = config or load_non_frontline_config()
    golden = filter_comparable_rows(
        summary_frame_from_builder(
            read_golden_summary_sheet(
                golden_workbook,
                sheet_name,
                header_row=header_row,
                data_start_row=data_start_row,
            )
        )
    )
    if golden.empty:
        return summary

    golden_by_key = golden.set_index(list(_JOIN_KEYS), drop=False)
    out = summary.copy()
    filled = 0

    for idx, row in out.iterrows():
        tier = non_frontline_tier(row.get("店别"), row.get("职务"), config=cfg)
        if tier is None:
            continue
        key = tuple(row.get(k) for k in _JOIN_KEYS)
        try:
            g_row = golden_by_key.loc[key]
        except KeyError:
            continue
        if isinstance(g_row, pd.DataFrame):
            g_row = g_row.iloc[0]

        for hub_col in column_mapping_for_tier(tier, config=cfg):
            if hub_col not in out.columns:
                continue
            if pd.notna(out.at[idx, hub_col]):
                continue
            g_val = g_row.get(hub_col)
            if pd.notna(g_val):
                out.at[idx, hub_col] = g_val
                filled += 1

    if filled:
        logger.info(
            "Non-frontline golden bootstrap: %s physical cells filled from %s",
            filled,
            golden_workbook.name,
        )
    return out


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
