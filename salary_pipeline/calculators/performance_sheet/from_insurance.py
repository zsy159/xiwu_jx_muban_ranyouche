"""保险明细 → 绩效整理表 AB / AJ / …（SUMIF by VIN）。"""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.insurance_detail_sheet import (
    VIN_COL,
    load_insurance_detail_frame,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.ops.basic import sumif_by_key

# 绩效整理表列 → 保险明细值列
INSURANCE_PERF_MAP: dict[str, str] = {
    "AB": "BP",
    "AJ": "BS",
    "AO": "BU",
    "AP": "BV",
}


def compute_insurance_columns(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = ("AB", "AJ"),
) -> pd.DataFrame:
    """
    Replicate ``=SUMIF(保险明细!D:D, O_row, 保险明细!XX:XX)`` per order row.

    *skeleton* must contain column ``O`` (VIN).
    """
    if skeleton.empty or "O" not in skeleton.columns:
        return pd.DataFrame()

    value_cols = tuple(
        INSURANCE_PERF_MAP[c] for c in target_cols if c in INSURANCE_PERF_MAP
    )
    detail = load_insurance_detail_frame(loader, value_cols=value_cols)

    out = skeleton[["O"]].copy()
    if "_excel_row" in skeleton.columns:
        out["_excel_row"] = skeleton["_excel_row"].values
    if "P" in skeleton.columns:
        out["P"] = skeleton["P"].values

    for perf_col in target_cols:
        src_col = INSURANCE_PERF_MAP.get(perf_col)
        if src_col is None:
            continue
        out[perf_col] = sumif_by_key(detail, VIN_COL, src_col, skeleton["O"])

    return out
