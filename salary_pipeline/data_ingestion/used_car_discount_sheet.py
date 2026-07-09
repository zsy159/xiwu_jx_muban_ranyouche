"""Load 系统二手车降价 — 绩效整理表 BE(代交车佣金) INDEX/MATCH by VIN."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, _log_frame_shape
from salary_pipeline.data_ingestion.performance_sheet_golden import _normalize_vin

USED_CAR_DISCOUNT_SHEET = "系统二手车降价"
USED_CAR_DISCOUNT_FILENAME = "系统二手车降价.xlsx"
VIN_COL = "CL"
COMMISSION_COL = "BE"
HEADER_ROWS = 2


def load_used_car_discount_frame(
    loader: WorkbookLoader,
) -> pd.DataFrame:
    frame = loader.read_sheet_columns(
        USED_CAR_DISCOUNT_SHEET,
        {VIN_COL: VIN_COL, COMMISSION_COL: COMMISSION_COL},
        label=f"{USED_CAR_DISCOUNT_SHEET}!{VIN_COL}",
    )
    frame = frame.iloc[HEADER_ROWS:].copy().reset_index(drop=True)
    frame[VIN_COL] = frame[VIN_COL].map(_normalize_vin)
    frame[COMMISSION_COL] = pd.to_numeric(frame[COMMISSION_COL], errors="coerce")
    return _log_frame_shape(frame.dropna(subset=[VIN_COL]), USED_CAR_DISCOUNT_SHEET)
