"""Load 按揭明细 — Phase B input for 绩效整理表 mortgage columns."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, _log_frame_shape

MORTGAGE_SHEET = "按揭明细"
VIN_COL = "G"


def load_mortgage_detail_frame(
    loader: WorkbookLoader,
    *,
    value_cols: tuple[str, ...] = ("BO", "BR"),
) -> pd.DataFrame:
    """Load mortgage detail columns keyed by VIN (column G)."""
    columns = {VIN_COL: VIN_COL, **{c: c for c in value_cols}}
    frame = loader.read_sheet_columns(
        MORTGAGE_SHEET,
        columns,
        label=f"{MORTGAGE_SHEET}!{VIN_COL}",
    )
    for col in value_cols:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return _log_frame_shape(frame, MORTGAGE_SHEET)
