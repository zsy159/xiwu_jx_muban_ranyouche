"""Phase B closure inputs — 上户提成、爱车保、置换服务、提成标准等。"""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, _log_frame_shape

COMPARISON_SHEET = "比对表"
COMMISSION_STANDARD_SHEET = "提成标准"
REGISTRATION_COMMISSION_SHEET = "上户提成"
CAR_INSURANCE_PRODUCT_SHEET = "爱车保"
TRADE_IN_SERVICE_SHEET = "置换服务"
USED_CAR_TRADE_SHEET = "二手置换 "
BIG_CUSTOMER_SHEET = "大客户"
OVERDUE_CAMPAIGN_SHEET = "重功超期+活动"
SYSTEM_EXCESS_SHEET = "系统超额"
WARRANTY_COMMISSION_SHEET = "延保提成"

# 系统销售毛利 — 闭包列上下文（列字母见 row-2 表头）
SG_DEPARTMENT_COL = "BL"  # 部门 → 绩效整理表 R
SG_ORDER_TOTAL_COL = "AO"  # 订单合计(含税) → L
SG_DECORATION_FLOOR_COL = "BQ"  # 精品最低价金额 → S
SG_VEHICLE_TYPE_COL = "D"  # 车种 → H
SG_CHANNEL_COL = "E"  # 销售渠道 → I

ORDER_CONTEXT_COLS = (
    SG_VEHICLE_TYPE_COL,
    SG_CHANNEL_COL,
    SG_DEPARTMENT_COL,
    SG_ORDER_TOTAL_COL,
    SG_DECORATION_FLOOR_COL,
)


def _load_sheet(
    loader: WorkbookLoader,
    sheet: str,
    columns: dict[str, str],
    *,
    label: str | None = None,
) -> pd.DataFrame:
    frame = loader.read_sheet_columns(
        sheet,
        columns,
        label=label or sheet,
    )
    return _log_frame_shape(frame, sheet)


def load_comparison_table_frame(loader: WorkbookLoader) -> pd.DataFrame:
    return _load_sheet(loader, COMPARISON_SHEET, {"A": "A", "B": "B"})


def load_commission_standard_frame(loader: WorkbookLoader) -> pd.DataFrame:
    return _load_sheet(
        loader,
        COMMISSION_STANDARD_SHEET,
        {"C": "C", "D": "D", "E": "E", "F": "F", "H": "H"},
    )


def load_registration_commission_frame(loader: WorkbookLoader) -> pd.DataFrame:
    frame = _load_sheet(
        loader,
        REGISTRATION_COMMISSION_SHEET,
        {"B": "B", "H": "H"},
    )
    frame["H"] = pd.to_numeric(frame["H"], errors="coerce")
    return frame


def load_car_insurance_product_frame(loader: WorkbookLoader) -> pd.DataFrame:
    frame = _load_sheet(
        loader,
        CAR_INSURANCE_PRODUCT_SHEET,
        {"F": "F", "BA": "BA"},
    )
    frame["BA"] = pd.to_numeric(frame["BA"], errors="coerce")
    return frame


def load_trade_in_service_frame(loader: WorkbookLoader) -> pd.DataFrame:
    frame = _load_sheet(
        loader,
        TRADE_IN_SERVICE_SHEET,
        {"G": "G", "BB": "BB"},
    )
    frame["BB"] = pd.to_numeric(frame["BB"], errors="coerce")
    return frame


def load_used_car_trade_frame(loader: WorkbookLoader) -> pd.DataFrame:
    frame = _load_sheet(
        loader,
        USED_CAR_TRADE_SHEET,
        {"T": "T", "AE": "AE"},
    )
    frame["AE"] = pd.to_numeric(frame["AE"], errors="coerce")
    return frame


def load_big_customer_frame(loader: WorkbookLoader) -> pd.DataFrame:
    frame = _load_sheet(
        loader,
        BIG_CUSTOMER_SHEET,
        {"O": "O", "R": "R"},
    )
    frame["R"] = pd.to_numeric(frame["R"], errors="coerce")
    return frame


def load_overdue_campaign_frame(loader: WorkbookLoader) -> pd.DataFrame:
    frame = _load_sheet(
        loader,
        OVERDUE_CAMPAIGN_SHEET,
        {"E": "E", "N": "N"},
    )
    frame["N"] = pd.to_numeric(frame["N"], errors="coerce")
    return frame


def load_system_excess_frame(loader: WorkbookLoader) -> pd.DataFrame:
    frame = _load_sheet(
        loader,
        SYSTEM_EXCESS_SHEET,
        {"W": "W", "P": "P"},
    )
    frame["P"] = pd.to_numeric(frame["P"], errors="coerce")
    return frame


def load_warranty_commission_frame(loader: WorkbookLoader) -> pd.DataFrame:
    """延保提成 — AF/AT 链：SUMIF(F, VIN, BE) → 延保收入。"""
    frame = _load_sheet(
        loader,
        WARRANTY_COMMISSION_SHEET,
        {"F": "F", "BE": "BE"},
    )
    frame = frame.iloc[1:].copy().reset_index(drop=True)
    frame["BE"] = pd.to_numeric(frame["BE"], errors="coerce")
    return frame
