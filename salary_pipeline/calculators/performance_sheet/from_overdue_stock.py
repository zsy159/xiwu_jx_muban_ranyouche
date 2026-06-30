"""库存超期 — 绩效整理表 E(库存天数) / AU(超期追加) → 提成汇总「超期」。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from salary_pipeline.calculators.performance_sheet.overdue_au_policy import (
    load_au_policy_by_vin,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.performance_sheet_golden import _normalize_vin
from salary_pipeline.data_ingestion.system_sales_gross_sheet import (
    ORDER_DATE_COL,
    VIN_COL,
    load_system_sales_gross_frame,
)
from salary_pipeline.ops.lookup import lookup_match_index_series

OVERDUE_STOCK_COLUMNS = ("E", "AU")
VEHICLE_COST_SHEET = "整车成本"
VEHICLE_COST_VIN_COL = "K"
VEHICLE_COST_SETTLE_COL = "B"


def _load_vehicle_settle_dates(loader: WorkbookLoader) -> pd.DataFrame:
    frame = loader.read_sheet_columns(
        VEHICLE_COST_SHEET,
        {VEHICLE_COST_VIN_COL: VEHICLE_COST_VIN_COL, VEHICLE_COST_SETTLE_COL: "B"},
        label=f"{VEHICLE_COST_SHEET}!{VEHICLE_COST_VIN_COL}",
    )
    frame = frame.iloc[2:].copy().reset_index(drop=True)
    frame[VEHICLE_COST_VIN_COL] = frame[VEHICLE_COST_VIN_COL].map(_normalize_vin)
    frame["B"] = pd.to_datetime(frame["B"], errors="coerce")
    return frame.dropna(subset=[VEHICLE_COST_VIN_COL]).drop_duplicates(
        VEHICLE_COST_VIN_COL, keep="last"
    )


def compute_inventory_days(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
) -> pd.Series:
    """``绩效整理表!E`` — INT(结算日期) − INDEX(整车成本!B, MATCH(O, K))."""
    if skeleton.empty or "O" not in skeleton.columns:
        return pd.Series(dtype=float)

    sg = load_system_sales_gross_frame(loader, value_cols=(ORDER_DATE_COL,))
    vc = _load_vehicle_settle_dates(loader)

    order_settle = lookup_match_index_series(
        skeleton["O"],
        sg[VIN_COL],
        sg[ORDER_DATE_COL],
        default=pd.NaT,
        coerce="datetime",
    )
    vehicle_settle = lookup_match_index_series(
        skeleton["O"],
        vc[VEHICLE_COST_VIN_COL],
        vc["B"],
        default=pd.NaT,
        coerce="datetime",
    )

    order_day = pd.to_datetime(order_settle, errors="coerce").dt.normalize()
    vehicle_day = pd.to_datetime(vehicle_settle, errors="coerce").dt.normalize()
    days = (order_day - vehicle_day).dt.days
    return pd.to_numeric(days, errors="coerce")


def compute_overdue_stock_columns(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = OVERDUE_STOCK_COLUMNS,
    topology_path: Path | None = None,
    inventory_days: pd.Series | None = None,
) -> pd.DataFrame:
    """Recompute E / AU for Hub ``SUMIF(..., AU)`` → 提成汇总「超期」."""
    if skeleton.empty or "O" not in skeleton.columns:
        return pd.DataFrame()

    need = frozenset(target_cols)
    out = skeleton[["O"]].copy()
    if "_excel_row" in skeleton.columns:
        out["_excel_row"] = skeleton["_excel_row"].values
    if "P" in skeleton.columns:
        out["P"] = skeleton["P"].values

    days = inventory_days if inventory_days is not None else compute_inventory_days(
        skeleton, loader
    )
    if "E" in need:
        out["E"] = days

    if "AU" in need:
        if topology_path is None:
            out["AU"] = 0.0
        else:
            policy_by_vin = load_au_policy_by_vin(
                str(loader.workbook_path),
                str(topology_path),
            )
            bonuses: list[float] = []
            for vin, inv_days in zip(skeleton["O"], days, strict=True):
                key = _normalize_vin(vin)
                if not key or key not in policy_by_vin:
                    bonuses.append(0.0)
                    continue
                min_days, amount = policy_by_vin[key]
                if pd.isna(inv_days) or float(inv_days) < float(min_days):
                    bonuses.append(0.0)
                else:
                    bonuses.append(float(amount))
            out["AU"] = pd.Series(bonuses, index=skeleton.index, dtype=float)

    return out
