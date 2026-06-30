"""Load 按揭原表 — Phase B input for 绩效整理表 AL column."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, _log_frame_shape

MORTGAGE_ORIGINAL_SHEET = "按揭原表"
VIN_COL = "AC"


def load_mortgage_original_frame(
    loader: WorkbookLoader,
    *,
    value_cols: tuple[str, ...] = ("AF",),
) -> pd.DataFrame:
    """Load mortgage original columns keyed by VIN (column AC)."""
    columns = {VIN_COL: VIN_COL, **{c: c for c in value_cols}}
    frame = loader.read_sheet_columns(
        MORTGAGE_ORIGINAL_SHEET,
        columns,
        label=f"{MORTGAGE_ORIGINAL_SHEET}!{VIN_COL}",
    )
    for col in value_cols:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return _log_frame_shape(frame, MORTGAGE_ORIGINAL_SHEET)
