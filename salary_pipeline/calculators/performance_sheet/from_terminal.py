"""终端明细表 → 绩效整理表 BC（终端返利）。"""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.terminal_detail_sheet import (
    VIN_COL,
    load_terminal_detail_frame,
)
from salary_pipeline.ops.basic import sumif_by_key

TERMINAL_PERF_COLUMNS = ("BC",)


def compute_terminal_columns(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = TERMINAL_PERF_COLUMNS,
) -> pd.DataFrame:
    """
    Replicate ``=-IF(AND($K<>0,$K<>\"\"),SUMIFS(终端明细表!P, C, O),0)`` per row.
    """
    if skeleton.empty or "O" not in skeleton.columns:
        return pd.DataFrame()

    if not target_cols:
        return pd.DataFrame()

    detail = load_terminal_detail_frame(loader, value_cols=("P",))
    terminal_sum = sumif_by_key(detail, VIN_COL, "P", skeleton["O"])
    k = pd.to_numeric(skeleton.get("K"), errors="coerce").fillna(0.0)
    active = k != 0
    bc = pd.Series(0.0, index=skeleton.index, dtype=float)
    bc.loc[active] = -pd.to_numeric(terminal_sum, errors="coerce").fillna(0.0).loc[active]

    out = skeleton[["O"]].copy()
    if "_excel_row" in skeleton.columns:
        out["_excel_row"] = skeleton["_excel_row"].values
    if "P" in skeleton.columns:
        out["P"] = skeleton["P"].values
    if "G" in skeleton.columns:
        out["G"] = skeleton["G"].values

    if "BC" in target_cols:
        out["BC"] = bc.values

    return out
