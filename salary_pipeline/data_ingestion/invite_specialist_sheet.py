"""Load 邀约专员提成子表（形态 B：姓名 C → 发放金额 AF）。"""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.ops.basic import sumif_by_key

INVITE_SHEET = "邀约专员提成"
NAME_COL = "C"
PAYOUT_COL = "AF"  # 发放金额 → hub 整车绩效 W


def load_invite_specialist_frame(loader: WorkbookLoader) -> pd.DataFrame:
    if not loader.has_sheet(INVITE_SHEET):
        return pd.DataFrame(columns=[NAME_COL, PAYOUT_COL])
    frame = loader.read_sheet_columns(
        INVITE_SHEET,
        {NAME_COL: NAME_COL, PAYOUT_COL: PAYOUT_COL},
        label=f"{INVITE_SHEET}!{NAME_COL}:{PAYOUT_COL}",
    )
    frame[NAME_COL] = frame[NAME_COL].map(normalize_name)
    frame[PAYOUT_COL] = pd.to_numeric(frame[PAYOUT_COL], errors="coerce")
    return frame


def lookup_vehicle_performance(
    frame: pd.DataFrame,
    name: str,
    *,
    name_col: str = NAME_COL,
    payout_col: str = PAYOUT_COL,
) -> float:
    """Same semantics as =SUMIF(邀约专员提成!C:C, 姓名, 邀约专员提成!AF:AF)."""
    if frame.empty or not name:
        return 0.0
    result = sumif_by_key(frame, name_col, payout_col, normalize_name(name))
    return float(result) if result is not None else 0.0
