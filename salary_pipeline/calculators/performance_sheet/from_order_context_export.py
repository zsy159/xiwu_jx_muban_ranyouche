"""Export 绩效整理表 order-context columns (A–AA chain) from detail inputs."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.calculators.performance_sheet.from_closure import (
    _compute_decoration_u,
)
from salary_pipeline.calculators.performance_sheet.order_context import (
    enrich_order_context,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.factory_purchase_sheet import (
    PURCHASE_COMPANY_COL,
    VIN_COL as FACTORY_VIN_COL,
    load_factory_purchase_frame,
)

ORDER_CONTEXT_EXPORT_COLUMNS = (
    "A",
    "B",
    "C",
    "D",
    "F",
    "H",
    "I",
    "J",
    "L",
    "M",
    "N",
    "Q",
    "R",
    "S",
    "T",
    "U",
    "V",
    "W",
    "X",
    "Y",
    "Z",
    "AA",
)

_EMISSION_STANDARD = "整车订单"


def compute_order_context_export_columns(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = ORDER_CONTEXT_EXPORT_COLUMNS,
) -> pd.DataFrame:
    """Recompute descriptive / closure-prerequisite columns for export."""
    if skeleton.empty or "O" not in skeleton.columns:
        return pd.DataFrame()

    need = frozenset(target_cols)
    ctx = enrich_order_context(skeleton, loader)
    out = skeleton[["O"]].copy()
    if "_excel_row" in skeleton.columns:
        out["_excel_row"] = skeleton["_excel_row"].values
    for key in ("G", "P", "K"):
        if key in skeleton.columns:
            out[key] = skeleton[key].values

    if need & {"B"}:
        out["B"] = _EMISSION_STANDARD
    if need & {"C"} and "C" in ctx.columns:
        out["C"] = ctx["C"].values
    if need & {"F"}:
        factory = load_factory_purchase_frame(loader)
        factory_map = dict(
            zip(
                factory[FACTORY_VIN_COL].astype(str).str.strip(),
                factory[PURCHASE_COMPANY_COL],
            )
        )
        out["F"] = skeleton["O"].astype(str).str.strip().map(factory_map)
    if need & {"T"}:
        out["T"] = skeleton["O"].astype(str).str.strip().str[-8:]

    for col in (
        "A",
        "D",
        "H",
        "I",
        "J",
        "L",
        "M",
        "N",
        "Q",
        "R",
        "S",
        "V",
        "X",
        "Y",
        "Z",
        "AA",
    ):
        if col in need and col in ctx.columns:
            out[col] = ctx[col].values

    if need & {"U"}:
        if "G" in skeleton.columns:
            out["U"] = _compute_decoration_u(skeleton["G"], loader).values
        else:
            out["U"] = 0.0

    if need & {"W"} and {"L", "S", "Y"}.issubset(out.columns):
        l_n = pd.to_numeric(out["L"], errors="coerce").fillna(0)
        s_n = pd.to_numeric(out["S"], errors="coerce").fillna(0)
        y_n = pd.to_numeric(out["Y"], errors="coerce").fillna(0)
        out["W"] = (l_n - s_n) - y_n

    return out
