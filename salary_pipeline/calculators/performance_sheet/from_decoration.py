"""装饰台账 → 绩效整理表 BH 等（SUMIFS by 订单号 G）。"""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.decoration_ledger_sheet import (
    ORDER_COL,
    load_decoration_ledger_frame,
)
from salary_pipeline.ops.basic import sumif_by_key

# 绩效整理表列 → (criteria 列 in 装饰台账, value 列)
DECORATION_PERF_MAP: dict[str, tuple[str, str]] = {
    "BH": (ORDER_COL, "AK"),
}


def compute_decoration_columns(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = ("BH",),
) -> pd.DataFrame:
    """
    Replicate ``=SUMIFS(装饰台账!AK:AK, 装饰台账!N:N, G_row)`` per order row.

    *skeleton* must contain column ``G`` (订单号).
    """
    if skeleton.empty or "G" not in skeleton.columns:
        return pd.DataFrame()

    value_cols = tuple(
        mapping[1]
        for col in target_cols
        if (mapping := DECORATION_PERF_MAP.get(col)) is not None
    )
    detail = load_decoration_ledger_frame(loader, value_cols=value_cols)

    out = skeleton[["G"]].copy()
    if "_excel_row" in skeleton.columns:
        out["_excel_row"] = skeleton["_excel_row"].values
    if "O" in skeleton.columns:
        out["O"] = skeleton["O"].values
    if "P" in skeleton.columns:
        out["P"] = skeleton["P"].values

    for perf_col in target_cols:
        mapping = DECORATION_PERF_MAP.get(perf_col)
        if mapping is None:
            continue
        key_col, value_col = mapping
        out[perf_col] = sumif_by_key(detail, key_col, value_col, skeleton["G"])

    return out
