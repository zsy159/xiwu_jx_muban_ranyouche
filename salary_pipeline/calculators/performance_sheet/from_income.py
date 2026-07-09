"""绩效整理表收入列 — AC/AE/AD（按揭/爱车保/上户/延保收入）。"""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.closure_input_sheets import (
    load_car_insurance_product_frame,
    load_registration_commission_frame,
    load_warranty_commission_frame,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.mortgage_detail_sheet import (
    VIN_COL as MORTGAGE_VIN_COL,
    load_mortgage_detail_frame,
)
from salary_pipeline.ops.basic import sumif_by_key
from salary_pipeline.ops.lookup import lookup_match_index

INCOME_PERF_COLUMNS = ("AC", "AD", "AE", "AF")


def compute_income_columns(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = INCOME_PERF_COLUMNS,
) -> pd.DataFrame:
    """Replicate golden income columns from detail sheets."""
    if skeleton.empty or "O" not in skeleton.columns:
        return pd.DataFrame()

    need = frozenset(target_cols)
    out = skeleton[["O"]].copy()
    if "_excel_row" in skeleton.columns:
        out["_excel_row"] = skeleton["_excel_row"].values
    if "P" in skeleton.columns:
        out["P"] = skeleton["P"].values

    if "AC" in need:
        detail = load_mortgage_detail_frame(loader, value_cols=("Z",))
        out["AC"] = lookup_match_index(
            skeleton["O"], detail[MORTGAGE_VIN_COL], detail["Z"]
        )
    if "AD" in need:
        detail = load_car_insurance_product_frame(loader)
        out["AD"] = sumif_by_key(detail, "F", "K", skeleton["O"])
    if "AE" in need:
        detail = load_registration_commission_frame(loader)
        out["AE"] = sumif_by_key(detail, "B", "C", skeleton["O"])
    if "AF" in need:
        detail = load_warranty_commission_frame(loader)
        out["AF"] = sumif_by_key(detail, "F", "BE", skeleton["O"])

    return out
