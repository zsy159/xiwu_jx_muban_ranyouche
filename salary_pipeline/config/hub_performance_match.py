"""Hub 岗位族行匹配 — 用于 parity_gate 子集对账。"""

from __future__ import annotations

from typing import Any

import pandas as pd


def row_matches_family(row: pd.Series, match: dict[str, Any]) -> bool:
    for key, expected in match.items():
        if key not in row.index:
            return False
        actual = row[key]
        if pd.isna(actual):
            return False
        if isinstance(expected, list):
            if str(actual) not in {str(v) for v in expected}:
                return False
        elif str(actual) != str(expected):
            return False
    return True


def family_row_mask(df: pd.DataFrame, match: dict[str, Any]) -> pd.Series:
    if not match or df.empty:
        return pd.Series(False, index=df.index)
    return df.apply(lambda row: row_matches_family(row, match), axis=1)


def gated_families(hub_cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    families = hub_cfg.get("role_families", {})
    return {
        name: spec
        for name, spec in families.items()
        if spec.get("parity_gate") and spec.get("module")
    }


def gated_performance_columns(hub_cfg: dict[str, Any]) -> list[str]:
    cols: list[str] = []
    seen: set[str] = set()
    for spec in gated_families(hub_cfg).values():
        for col in spec.get("hub_columns", []):
            if col not in seen:
                seen.add(col)
                cols.append(col)
    return cols


def combined_gated_row_mask(df: pd.DataFrame, hub_cfg: dict[str, Any]) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    for spec in gated_families(hub_cfg).values():
        match = spec.get("match", {})
        if match:
            mask = mask | family_row_mask(df, match)
    return mask
