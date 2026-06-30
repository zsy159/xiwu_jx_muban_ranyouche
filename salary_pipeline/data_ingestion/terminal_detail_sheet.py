"""Load 终端明细表 — Phase B input for 绩效整理表 terminal rebate columns."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, _log_frame_shape
from salary_pipeline.data_ingestion.performance_sheet_golden import _normalize_vin

TERMINAL_DETAIL_SHEET = "终端明细表"
VIN_COL = "C"
DATA_START_ROW = 2  # Excel 1-based; row 1 = headers


def load_terminal_detail_frame(
    loader: WorkbookLoader,
    *,
    value_cols: tuple[str, ...] = ("D", "P"),
) -> pd.DataFrame:
    """Load terminal detail columns keyed by VIN (column C)."""
    columns = {VIN_COL: VIN_COL, **{c: c for c in value_cols}}
    frame = loader.read_sheet_columns(
        TERMINAL_DETAIL_SHEET,
        columns,
        label=f"{TERMINAL_DETAIL_SHEET}!{VIN_COL}",
    )
    skip = DATA_START_ROW - 1
    frame = frame.iloc[skip:].copy().reset_index(drop=True)
    frame[VIN_COL] = frame[VIN_COL].map(_normalize_vin)
    frame = frame[frame[VIN_COL].notna()].reset_index(drop=True)
    if "D" in frame.columns:
        frame["D"] = pd.to_datetime(frame["D"], errors="coerce")
    if "P" in frame.columns:
        frame["P"] = pd.to_numeric(frame["P"], errors="coerce")
    return _log_frame_shape(frame, TERMINAL_DETAIL_SHEET)
