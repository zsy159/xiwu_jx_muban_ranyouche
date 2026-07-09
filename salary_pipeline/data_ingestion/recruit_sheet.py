"""Load 招聘当月子表（团队分配块 + 按人金额列）。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from salary_pipeline.calculators.recruit.registry import (
    get_team_block_config,
    list_roles,
)
from salary_pipeline.data_ingestion.data_loader import (
    WorkbookLoader,
    normalize_name,
)
from salary_pipeline.ops.basic import sumif_by_key

RECRUIT_SHEET = "招聘"
NAME_COL = "Q"
ONBOARD_COL = "S"
RATE_COL = "T"
TOTAL_COL = "U"
ALLOCATION_COL = "V"
AMOUNT_COL = "W"

_TEAM_COLS = {
    "name": NAME_COL,
    "onboard_count": ONBOARD_COL,
    "commission_per_hire": RATE_COL,
    "total_commission": TOTAL_COL,
    "allocation_ratio": ALLOCATION_COL,
    "amount": AMOUNT_COL,
}


def _num(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_recruit_frame(loader: WorkbookLoader) -> pd.DataFrame:
    if not loader.has_sheet(RECRUIT_SHEET):
        return pd.DataFrame(columns=[NAME_COL, AMOUNT_COL])
    frame = loader.read_sheet_columns(
        RECRUIT_SHEET,
        {NAME_COL: NAME_COL, AMOUNT_COL: AMOUNT_COL},
        label=f"{RECRUIT_SHEET}!{NAME_COL}:{AMOUNT_COL}",
    )
    frame[NAME_COL] = frame[NAME_COL].map(normalize_name)
    frame[AMOUNT_COL] = pd.to_numeric(frame[AMOUNT_COL], errors="coerce")
    return frame


def load_team_allocation_frame(loader: WorkbookLoader) -> pd.DataFrame:
    """读取招聘子表团队分配相关列（Q / S–W）。"""
    cfg = get_team_block_config()
    cols = cfg["cols"]
    sheet = cfg["sheet"]
    if not loader.has_sheet(sheet):
        return pd.DataFrame(columns=list(cols.keys()))
    frame = loader.read_sheet_columns(
        sheet,
        cols,
        label=f"{sheet}!team_block",
    )
    frame["name"] = frame["name"].map(normalize_name)
    for logical in (
        "onboard_count",
        "commission_per_hire",
        "total_commission",
        "allocation_ratio",
        "amount",
    ):
        if logical in frame.columns:
            frame[logical] = pd.to_numeric(frame[logical], errors="coerce")
    frame["excel_row"] = frame.index + 1
    role_names = {r["name"] for r in list_roles()}
    return frame[frame["name"].isin(role_names)].reset_index(drop=True)


def lookup_insurance_performance(
    frame: pd.DataFrame,
    name: str,
    *,
    name_col: str = NAME_COL,
    amount_col: str = AMOUNT_COL,
) -> float:
    """Same semantics as =SUMIF(招聘!Q:Q, 姓名, 招聘!W:W)."""
    if frame.empty or not name:
        return 0.0
    result = sumif_by_key(frame, name_col, amount_col, normalize_name(name))
    return float(result) if result is not None else 0.0
