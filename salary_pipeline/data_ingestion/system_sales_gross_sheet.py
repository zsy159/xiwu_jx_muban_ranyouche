"""Load 系统销售毛利 — Phase B input for 绩效整理表 order skeleton keys."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name, _log_frame_shape
from salary_pipeline.data_ingestion.performance_sheet_golden import _normalize_vin

SYSTEM_SALES_GROSS_SHEET = "系统销售毛利"
VIN_COL = "BD"
ORDER_COL = "B"
ADVISOR_COL = "BJ"
ORDER_DATE_COL = "BA"
SETTLE_DATE_COL = ORDER_DATE_COL  # 绩效整理表 M — 结算日期Refresh
ORDER_TYPE_COL = "AZ"
# 闭包列上下文（中文表头 → 列字母，见 Excel row 2）
DEPARTMENT_COL = "BL"  # 部门 → 绩效整理表 R
ORDER_TOTAL_COL = "AO"  # 订单合计(含税) → L
DECORATION_FLOOR_COL = "BQ"  # 精品最低价金额 → S
VEHICLE_TYPE_COL = "D"  # 车种 → H
VEHICLE_MODEL_COL = "F"  # 车型 → J
CHANNEL_COL = "E"  # 销售渠道 → I
OWNER_NAME_COL = "BC"  # 车主名称 → N
REVIEWER_COL = "BK"  # 审核人 → Q
ORDER_CONTEXT_COLS = (
    VEHICLE_TYPE_COL,
    CHANNEL_COL,
    DEPARTMENT_COL,
    ORDER_TOTAL_COL,
    DECORATION_FLOOR_COL,
)
ORDER_METADATA_COLS = ORDER_CONTEXT_COLS + (
    VEHICLE_MODEL_COL,
    SETTLE_DATE_COL,
    OWNER_NAME_COL,
    REVIEWER_COL,
)
HEADER_ROWS = 2  # rows 1–2 are headers / month label


def load_system_sales_gross_frame(
    loader: WorkbookLoader,
    *,
    value_cols: tuple[str, ...] = (ORDER_COL, ADVISOR_COL, ORDER_DATE_COL, ORDER_TYPE_COL),
) -> pd.DataFrame:
    """Load 系统销售毛利 order-level columns keyed by VIN (column BD)."""
    columns = {VIN_COL: VIN_COL, **{c: c for c in value_cols}}
    frame = loader.read_sheet_columns(
        SYSTEM_SALES_GROSS_SHEET,
        columns,
        label=f"{SYSTEM_SALES_GROSS_SHEET}!{VIN_COL}",
    )
    skip = HEADER_ROWS
    frame = frame.iloc[skip:].copy().reset_index(drop=True)
    frame[VIN_COL] = frame[VIN_COL].map(_normalize_vin)
    frame = frame[frame[VIN_COL].notna()].reset_index(drop=True)
    if ADVISOR_COL in frame.columns:
        frame[ADVISOR_COL] = frame[ADVISOR_COL].map(normalize_name)
    if ORDER_DATE_COL in frame.columns:
        frame[ORDER_DATE_COL] = pd.to_datetime(frame[ORDER_DATE_COL], errors="coerce")
    if ORDER_COL in frame.columns:
        frame[ORDER_COL] = frame[ORDER_COL].astype(str).str.strip()
    return _log_frame_shape(frame, SYSTEM_SALES_GROSS_SHEET)
