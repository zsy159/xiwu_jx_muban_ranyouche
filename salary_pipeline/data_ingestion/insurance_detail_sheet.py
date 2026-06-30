"""Load 保险明细 — Phase B input for 绩效整理表 insurance columns."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, _log_frame_shape

INSURANCE_SHEET = "保险明细"
VIN_COL = "D"


def load_insurance_detail_frame(
    loader: WorkbookLoader,
    *,
    value_cols: tuple[str, ...] = ("BP", "BS", "BU", "BV"),
) -> pd.DataFrame:
    """Load insurance detail columns keyed by VIN (column D)."""
    columns = {VIN_COL: VIN_COL, **{c: c for c in value_cols}}
    frame = loader.read_sheet_columns(
        INSURANCE_SHEET,
        columns,
        label=f"{INSURANCE_SHEET}!{VIN_COL}",
    )
    for col in value_cols:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return _log_frame_shape(frame, INSURANCE_SHEET)
