"""Build 绩效整理表 order skeleton (O/P/K/G) from detail inputs — Slice 4."""

from __future__ import annotations

from typing import Any

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.data_ingestion.performance_sheet_golden import DATA_START_ROW, _normalize_vin
from salary_pipeline.data_ingestion.system_sales_gross_sheet import (
    ADVISOR_COL,
    ORDER_COL,
    ORDER_DATE_COL,
    ORDER_TYPE_COL,
    VIN_COL,
    load_system_sales_gross_frame,
)
from salary_pipeline.ops.lookup import lookup_match_index

VEHICLE_ORDER_TYPE = "含整车订单"


def build_performance_order_skeleton(
    loader: WorkbookLoader,
    skeleton_config: dict[str, Any],
    *,
    billing_month: str | None = None,
) -> pd.DataFrame:
    """
    Rebuild order keys for 绩效整理表 without golden bootstrap.

    * O / G / base P / K from ``系统销售毛利`` (month filter + 含整车订单)
    * P per-row overrides + supplement service rows from ``performance_sheet_columns.yaml``
    * ``终端明细表`` registered for downstream BC SUMIFS (Slice 4 validates VIN overlap)
    """
    month = billing_month or skeleton_config.get("billing_month")
    if not month:
        raise ValueError("billing_month required for order skeleton")

    year, mon = (int(part) for part in month.split("-"))
    sg = load_system_sales_gross_frame(loader)

    month_mask = (
        (sg[ORDER_DATE_COL].dt.year == year)
        & (sg[ORDER_DATE_COL].dt.month == mon)
        & (sg[ORDER_TYPE_COL] == VEHICLE_ORDER_TYPE)
    )
    month_orders = sg.loc[month_mask].drop_duplicates(VIN_COL, keep="first")

    frame = pd.DataFrame(
        {
            "O": month_orders[VIN_COL].values,
            "G": month_orders[ORDER_COL].astype(str).values,
            "P": month_orders[ADVISOR_COL].values,
            "K": 1.0,
        }
    )

  # ``=INDEX(系统销售毛利!BJ:BJ, MATCH(O, BD, 0))`` — already applied via join;
  # overrides capture hub-linked advisor aliases (袁萍/沈燕1/余才万N).
    overrides: dict[str, str] = skeleton_config.get("p_overrides_by_vin") or {}
    if overrides:
        norm_overrides = {_normalize_vin(k): normalize_name(v) for k, v in overrides.items()}
        mask = frame["O"].isin(norm_overrides)
        frame.loc[mask, "P"] = frame.loc[mask, "O"].map(norm_overrides)

    supplements = skeleton_config.get("supplement_rows") or []
    if supplements:
        sg_lookup = sg.drop_duplicates(VIN_COL, keep="first").set_index(VIN_COL)
        extra_rows: list[dict[str, Any]] = []
        for row in supplements:
            vin = _normalize_vin(row.get("vin"))
            if not vin:
                continue
            advisor = row.get("P")
            if advisor is None and vin in sg_lookup.index:
                advisor = sg_lookup.at[vin, ADVISOR_COL]
            extra_rows.append(
                {
                    "O": vin,
                    "G": row.get("G"),
                    "P": normalize_name(advisor),
                    "K": row.get("K"),
                }
            )
        if extra_rows:
            frame = pd.concat([frame, pd.DataFrame(extra_rows)], ignore_index=True)

    frame = frame[frame["O"].notna()].reset_index(drop=True)
    frame["_excel_row"] = range(DATA_START_ROW, DATA_START_ROW + len(frame))
    return frame


def lookup_advisor_by_vin(
    vins: pd.Series,
    loader: WorkbookLoader,
) -> pd.Series:
    """Replicate ``INDEX(系统销售毛利!BJ:BJ, MATCH(O, BD, 0))``."""
    sg = load_system_sales_gross_frame(loader, value_cols=(ADVISOR_COL,))
    return lookup_match_index(vins, sg[VIN_COL], sg[ADVISOR_COL])
