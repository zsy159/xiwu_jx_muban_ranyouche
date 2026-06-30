"""整车成本 → 绩效整理表 AW–BB（INDEX/MATCH by VIN）。"""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.vehicle_cost_sheet import (
    VIN_COL,
    load_vehicle_cost_frame,
)
from salary_pipeline.ops.lookup import lookup_match_index

# 绩效整理表列 → 整车成本值列
VEHICLE_COST_INDEX_MAP: dict[str, str] = {
    "AW": "R",
    "AX": "S",
    "AY": "T",
    "AZ": "U",
    "BA": "V",
    "BB": "W",
}


def compute_vehicle_cost_columns(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = ("AW", "AX", "AY", "AZ", "BA", "BB"),
) -> pd.DataFrame:
    """
    Replicate ``=INDEX(整车成本!XX:XX, MATCH(O_row, 整车成本!K:K, 0))`` per order row.

    *skeleton* must contain column ``O`` (VIN).
    """
    if skeleton.empty or "O" not in skeleton.columns:
        return pd.DataFrame()

    value_cols = tuple(
        VEHICLE_COST_INDEX_MAP[c] for c in target_cols if c in VEHICLE_COST_INDEX_MAP
    )
    detail = load_vehicle_cost_frame(loader, value_cols=value_cols)

    out = skeleton[["O"]].copy()
    if "_excel_row" in skeleton.columns:
        out["_excel_row"] = skeleton["_excel_row"].values
    if "P" in skeleton.columns:
        out["P"] = skeleton["P"].values

    for perf_col in target_cols:
        src_col = VEHICLE_COST_INDEX_MAP.get(perf_col)
        if src_col is None:
            continue
        out[perf_col] = lookup_match_index(
            skeleton["O"],
            detail[VIN_COL],
            detail[src_col],
        )

    return out
