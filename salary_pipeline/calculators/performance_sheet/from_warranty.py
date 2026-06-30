"""延保提成 → 绩效整理表 AF/AT（Hub AE 上游）。"""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.closure_input_sheets import (
    load_warranty_commission_frame,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.ops.basic import sumif_by_key

WARRANTY_PERF_COLUMNS = ("AT",)


def _at_from_af(af: pd.Series) -> pd.Series:
    """``=IF(AF<0,-200,(IF(AF>0,200,0)))`` per order row."""
    numeric = pd.to_numeric(af, errors="coerce").fillna(0.0)
    return numeric.apply(
        lambda value: -200.0 if value < 0 else (200.0 if value > 0 else 0.0)
    )


def compute_warranty_columns(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = WARRANTY_PERF_COLUMNS,
) -> pd.DataFrame:
    """
    Replicate 绩效整理表 AF/AT chain:

    * ``AF`` = ``SUMIF(延保提成!F:F, O, 延保提成!BE:BE)``
    * ``AT`` = piecewise on AF
    """
    if skeleton.empty or "O" not in skeleton.columns:
        return pd.DataFrame()

    need = frozenset(target_cols)
    if not need:
        return pd.DataFrame()

    detail = load_warranty_commission_frame(loader)
    af = sumif_by_key(detail, "F", "BE", skeleton["O"])

    out = skeleton[["O"]].copy()
    if "_excel_row" in skeleton.columns:
        out["_excel_row"] = skeleton["_excel_row"].values
    if "P" in skeleton.columns:
        out["P"] = skeleton["P"].values

    if "AT" in need:
        out["AT"] = _at_from_af(af).values

    return out
