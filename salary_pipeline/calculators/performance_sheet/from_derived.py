"""绩效整理表派生毛利列 — AV/BE–BN（闭包算术链）。"""

from __future__ import annotations

import pandas as pd
from openpyxl.utils import column_index_from_string, get_column_letter

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.used_car_discount_sheet import (
    COMMISSION_COL,
    VIN_COL as DISCOUNT_VIN_COL,
    load_used_car_discount_frame,
)
from salary_pipeline.ops.lookup import lookup_match_index

DERIVED_PERF_COLUMNS = ("AV", "BE", "BF", "BG", "BI", "BJ", "BL", "BM", "BN")

_PERF_SUM_START = column_index_from_string("AG")
_PERF_SUM_END = column_index_from_string("AU")
_INCOME_SUM_START = column_index_from_string("AB")
_INCOME_SUM_END = column_index_from_string("AF")
_COST_SUM_START = column_index_from_string("AW")
_COST_SUM_END = column_index_from_string("BE")
_BN_START = column_index_from_string("AG")
_BN_END = column_index_from_string("AT")


def _letter_range(start: int, end: int) -> tuple[str, ...]:
    return tuple(get_column_letter(i) for i in range(start, end + 1))


def _row_sum(frame: pd.DataFrame, letters: tuple[str, ...]) -> pd.Series:
    cols = [c for c in letters if c in frame.columns]
    if not cols:
        return pd.Series(0.0, index=frame.index, dtype=float)
    numeric = frame[cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    return numeric.sum(axis=1)


def compute_derived_columns(
    frame: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = DERIVED_PERF_COLUMNS,
) -> pd.DataFrame:
    """Replicate golden derived margin / total columns."""
    if frame.empty or "O" not in frame.columns:
        return pd.DataFrame()

    need = frozenset(target_cols)
    out = frame[["O"]].copy()
    if "_excel_row" in frame.columns:
        out["_excel_row"] = frame["_excel_row"].values
    if "P" in frame.columns:
        out["P"] = frame["P"].values

    working = frame.copy()
    if "BE" in need:
        discount = load_used_car_discount_frame(loader)
        working["BE"] = lookup_match_index(
            frame["O"], discount[DISCOUNT_VIN_COL], discount[COMMISSION_COL]
        )

    cost_cols = _letter_range(_COST_SUM_START, _COST_SUM_END)
    if "BF" in need:
        working["BF"] = _row_sum(working, cost_cols)
    if "BG" in need and "L" in working.columns:
        working["BG"] = pd.to_numeric(working["L"], errors="coerce").fillna(0) - _row_sum(
            working, cost_cols
        )
    if "BI" in need and {"S", "BH"}.issubset(working.columns):
        working["BI"] = pd.to_numeric(working["S"], errors="coerce").fillna(0) - pd.to_numeric(
            working["BH"], errors="coerce"
        ).fillna(0)
    if "BJ" in need and {"BG", "BI"}.issubset(working.columns):
        working["BJ"] = pd.to_numeric(working["BG"], errors="coerce").fillna(0) + pd.to_numeric(
            working["BI"], errors="coerce"
        ).fillna(0)

    income_cols = _letter_range(_INCOME_SUM_START, _INCOME_SUM_END)
    income_sum = _row_sum(working, income_cols)
    if "BL" in need and "BJ" in working.columns:
        working["BL"] = pd.to_numeric(working["BJ"], errors="coerce").fillna(0) + income_sum
    if "BM" in need and "BJ" in working.columns:
        working["BM"] = pd.to_numeric(working["BJ"], errors="coerce").fillna(0) / 1.13 + income_sum / 1.06
    if "BN" in need:
        working["BN"] = _row_sum(working, _letter_range(_BN_START, _BN_END))
    if "AV" in need:
        working["AV"] = _row_sum(working, _letter_range(_PERF_SUM_START, _PERF_SUM_END))

    for col in target_cols:
        if col in working.columns:
            out[col] = working[col].values

    return out
