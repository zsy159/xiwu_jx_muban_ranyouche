"""Load 整车成本 — Phase B input for 绩效整理表 INDEX/MATCH columns."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, _log_frame_shape

VEHICLE_COST_SHEET = "整车成本"
VIN_COL = "K"


def load_vehicle_cost_frame(
    loader: WorkbookLoader,
    *,
    value_cols: tuple[str, ...] = ("R", "S", "T", "U", "V", "W"),
) -> pd.DataFrame:
    """Load vehicle cost columns keyed by VIN (column K)."""
    columns = {VIN_COL: VIN_COL, **{c: c for c in value_cols}}
    frame = loader.read_sheet_columns(
        VEHICLE_COST_SHEET,
        columns,
        label=f"{VEHICLE_COST_SHEET}!{VIN_COL}",
    )
    for col in value_cols:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return _log_frame_shape(frame, VEHICLE_COST_SHEET)
