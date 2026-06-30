"""Load 装饰台账 — Phase B input for 绩效整理表 decoration columns."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, _log_frame_shape

DECORATION_SHEET = "装饰台账"
ORDER_COL = "N"
NUMERIC_COLS = frozenset({"AK", "AR"})
TEXT_COLS = frozenset({"H", "M", "N"})


def load_decoration_ledger_frame(
    loader: WorkbookLoader,
    *,
    value_cols: tuple[str, ...] = ("AK",),
) -> pd.DataFrame:
    """Load decoration ledger columns keyed by order number (column N)."""
    columns = {ORDER_COL: ORDER_COL, **{c: c for c in value_cols}}
    frame = loader.read_sheet_columns(
        DECORATION_SHEET,
        columns,
        label=f"{DECORATION_SHEET}!{ORDER_COL}",
    )
    for col in value_cols:
        if col in NUMERIC_COLS:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        elif col in TEXT_COLS:
            frame[col] = frame[col].astype(str).str.strip()
        else:
            frame[col] = frame[col].astype(str)
    return _log_frame_shape(frame, DECORATION_SHEET)
