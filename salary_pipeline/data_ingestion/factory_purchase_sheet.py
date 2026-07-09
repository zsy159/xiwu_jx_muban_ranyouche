"""Load 工厂购进 — 绩效整理表 F(购进公司) INDEX/MATCH by VIN."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, _log_frame_shape
from salary_pipeline.data_ingestion.performance_sheet_golden import _normalize_vin

FACTORY_PURCHASE_SHEET = "工厂购进"
FACTORY_PURCHASE_FILENAME = "工厂购进.xlsx"
VIN_COL = "C"
PURCHASE_COMPANY_COL = "CA"
HEADER_ROWS = 2


def load_factory_purchase_frame(
    loader: WorkbookLoader,
) -> pd.DataFrame:
    frame = loader.read_sheet_columns(
        FACTORY_PURCHASE_SHEET,
        {VIN_COL: VIN_COL, PURCHASE_COMPANY_COL: PURCHASE_COMPANY_COL},
        label=f"{FACTORY_PURCHASE_SHEET}!{VIN_COL}",
    )
    frame = frame.iloc[HEADER_ROWS:].copy().reset_index(drop=True)
    frame[VIN_COL] = frame[VIN_COL].map(_normalize_vin)
    return _log_frame_shape(frame.dropna(subset=[VIN_COL]), FACTORY_PURCHASE_SHEET)
