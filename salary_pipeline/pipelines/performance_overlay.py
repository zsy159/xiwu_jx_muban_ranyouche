"""Merge role-specific hub performance modules onto the commission summary."""

from __future__ import annotations

import logging

import pandas as pd

from salary_pipeline.modules.base import SUMMARY_KEY_COLUMNS, ModuleResult

logger = logging.getLogger(__name__)


def clear_bootstrap_for_overlay(
    summary: pd.DataFrame, module: ModuleResult
) -> pd.DataFrame:
    """仅清空本模块即将写入的 hub 格，保留拓扑回放的其他列。"""
    metrics = module.metrics
    if metrics.empty:
        return summary

    out = summary.copy()
    metric_cols = [c for c in metrics.columns if c not in SUMMARY_KEY_COLUMNS]
    keyed = metrics.set_index(SUMMARY_KEY_COLUMNS, drop=False)

    for idx, row in out.iterrows():
        key = tuple(row[col] for col in SUMMARY_KEY_COLUMNS)
        if key not in keyed.index:
            continue
        src = keyed.loc[key]
        if isinstance(src, pd.DataFrame):
            src = src.iloc[0]
        for col in metric_cols:
            if col not in out.columns:
                continue
            val = src[col]
            if pd.notna(val):
                out.at[idx, col] = pd.NA
    return out


def overlay_module_metrics(
    summary: pd.DataFrame, module: ModuleResult
) -> pd.DataFrame:
    """Overwrite metric columns where the module produced values."""
    metrics = module.metrics
    if metrics.empty:
        return summary

    out = summary.copy()
    metric_cols = [c for c in metrics.columns if c not in SUMMARY_KEY_COLUMNS]
    keyed = metrics.set_index(SUMMARY_KEY_COLUMNS, drop=False)
    updated = 0

    for idx, row in out.iterrows():
        key = tuple(row[col] for col in SUMMARY_KEY_COLUMNS)
        if key not in keyed.index:
            continue
        src = keyed.loc[key]
        if isinstance(src, pd.DataFrame):
            src = src.iloc[0]
        for col in metric_cols:
            val = src[col]
            if pd.notna(val):
                if col not in out.columns:
                    out[col] = pd.NA
                out.at[idx, col] = val
                updated += 1

    logger.info(
        "Overlay module %s: %s cells on %s rows",
        module.module_name,
        updated,
        len(metrics),
    )
    return out
