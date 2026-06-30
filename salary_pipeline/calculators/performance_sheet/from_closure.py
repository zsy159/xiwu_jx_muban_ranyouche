"""绩效整理表闭包列 — AG/AH/AI/AM/AN/AS/AQ/AR（Hub W–AI 间接引用）。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd
import yaml

from salary_pipeline.calculators.performance_sheet.order_context import (
    enrich_order_context,
)
from salary_pipeline.data_ingestion.closure_input_sheets import (
    load_big_customer_frame,
    load_car_insurance_product_frame,
    load_commission_standard_frame,
    load_overdue_campaign_frame,
    load_registration_commission_frame,
    load_trade_in_service_frame,
    load_used_car_trade_frame,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.data_ingestion.decoration_ledger_sheet import (
    load_decoration_ledger_frame,
)
from salary_pipeline.ops.basic import sumif_by_key
from salary_pipeline.paths import CONFIG_DIR

CLOSURE_PERF_COLUMNS = ("AG", "AH", "AI", "AM", "AN", "AS", "AQ", "AR")

_EXCLUDED_D = frozenset({"分公司", "网络部", "大客户", ""})
_STORE_D = frozenset({"直营店店面", "自有店"})


@lru_cache(maxsize=1)
def _load_supplement_g_labels() -> frozenset[str]:
    """G labels for service supplement rows (AH blank in golden)."""
    path = CONFIG_DIR / "performance_sheet_columns.yaml"
    with path.open(encoding="utf-8") as handle:
        cfg: dict[str, Any] = yaml.safe_load(handle) or {}
    skeleton_cfg = cfg.get("order_skeleton") or {}
    rows = skeleton_cfg.get("supplement_rows") or []
    return frozenset(str(row.get("G", "")).strip() for row in rows if row.get("G"))


def compute_closure_columns(
    skeleton: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    target_cols: tuple[str, ...] = CLOSURE_PERF_COLUMNS,
    context: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Recompute Hub-linked closure columns from registered detail inputs."""
    if skeleton.empty or "O" not in skeleton.columns:
        return pd.DataFrame()

    ctx = context if context is not None else enrich_order_context(skeleton, loader)
    out = skeleton[["O"]].copy()
    if "_excel_row" in skeleton.columns:
        out["_excel_row"] = skeleton["_excel_row"].values
    if "P" in skeleton.columns:
        out["P"] = skeleton["P"].values
    if "G" in skeleton.columns:
        out["G"] = skeleton["G"].values

    ctx = ctx.copy()
    if "K" not in ctx.columns and "K" in skeleton.columns:
        ctx["K"] = pd.to_numeric(skeleton["K"], errors="coerce")
    if "U" not in ctx.columns and "G" in ctx.columns:
        ctx["U"] = _compute_decoration_u(ctx["G"], loader)

    need = frozenset(target_cols)
    standard: pd.DataFrame | None = None
    if need & {"AG", "AQ"}:
        standard = load_commission_standard_frame(loader)

    if "AG" in need:
        assert standard is not None
        out["AG"] = _compute_ag(ctx, standard)
    if "AI" in need:
        out["AI"] = _compute_ai(ctx)
    if "AH" in need:
        if standard is None:
            standard = load_commission_standard_frame(loader)
        ag = out["AG"] if "AG" in out.columns else _compute_ag(ctx, standard)
        ai = out["AI"] if "AI" in out.columns else _compute_ai(ctx)
        aj = skeleton["AJ"] if "AJ" in skeleton.columns else 0.0
        ak = skeleton["AK"] if "AK" in skeleton.columns else 0.0
        out["AH"] = _compute_ah(ctx, ag, ai, aj, ak)

    if "AM" in need:
        detail = load_car_insurance_product_frame(loader)
        out["AM"] = sumif_by_key(detail, "F", "BA", ctx["O"])
    if "AN" in need:
        detail = load_registration_commission_frame(loader)
        out["AN"] = sumif_by_key(detail, "B", "H", ctx["O"])
    if "AS" in need:
        detail = load_trade_in_service_frame(loader)
        out["AS"] = sumif_by_key(detail, "G", "BB", ctx["O"])
    if "AR" in need:
        used = load_used_car_trade_frame(loader)
        big = load_big_customer_frame(loader)
        from_used = sumif_by_key(used, "T", "AE", ctx["O"])
        from_big = sumif_by_key(big, "O", "R", ctx["O"])
        out["AR"] = pd.to_numeric(from_used, errors="coerce").fillna(0) + pd.to_numeric(
            from_big, errors="coerce"
        ).fillna(0)
    if "AQ" in need:
        assert standard is not None
        overdue = load_overdue_campaign_frame(loader)
        overdue_part = sumif_by_key(overdue, "E", "N", ctx["O"])
        std_part = _compute_aq_standard(ctx, standard)
        out["AQ"] = pd.to_numeric(overdue_part, errors="coerce").fillna(0) + pd.to_numeric(
            std_part, errors="coerce"
        ).fillna(0)

    return out


def _compute_decoration_u(order_ids: pd.Series, loader: WorkbookLoader) -> pd.Series:
    """``绩效整理表!U`` — 不提成精品（装饰台账多段 SUMIFS）。"""
    detail = load_decoration_ledger_frame(loader, value_cols=("AR", "H", "N", "M"))
    detail["AR"] = pd.to_numeric(detail["AR"], errors="coerce").fillna(0)
    detail["N"] = detail["N"].astype(str).str.strip()
    detail["M"] = detail["M"].astype(str).str.strip()
    detail["H"] = detail["H"].astype(str)

    totals: dict[str, float] = {}
    for key_col, needle, exact in (
        ("N", "吉利全系下护板", False),
        ("M", "吉利原厂星瑞贯穿尾灯", True),
        ("N", "吉利全系皮老头豪华脚垫", False),
        ("N", "保养", False),
    ):
        if exact:
            part = detail[detail["H"].str.strip() == needle]
            grouped = part.groupby(key_col)["AR"].sum()
        else:
            part = detail[detail["H"].str.contains(needle, na=False)]
            grouped = part.groupby(key_col)["AR"].sum()
        for key, amount in grouped.items():
            totals[key] = totals.get(key, 0.0) + float(amount)

    return order_ids.astype(str).str.strip().map(lambda k: totals.get(k, 0.0))


def _store_key(dept: object) -> str:
    text = str(dept)
    return "直营店" if "直营店" in text else text


def _lookup_standard(
    standard: pd.DataFrame,
    *,
    vehicle: object,
    channel: object,
    dept: object,
    value_col: str,
) -> float:
    store = _store_key(dept)
    matched = standard[
        (standard["E"].astype(str) == str(vehicle))
        & (standard["D"].astype(str) == str(channel))
        & (standard["C"].astype(str) == store)
    ]
    if matched.empty:
        return 0.0
    val = pd.to_numeric(matched[value_col].iloc[0], errors="coerce")
    if pd.isna(val):
        return 0.0
    return float(val)


def _k_units(k_raw: object) -> float:
    if k_raw is None or (isinstance(k_raw, float) and pd.isna(k_raw)):
        return 0.0
    val = pd.to_numeric(k_raw, errors="coerce")
    if pd.isna(val):
        return 0.0
    return float(val)


def _compute_ag(ctx: pd.DataFrame, standard: pd.DataFrame) -> pd.Series:
    rows: list[float] = []
    for row in ctx.itertuples(index=False):
        k = _k_units(getattr(row, "K", 0))
        if str(getattr(row, "A", "")) == "武侯自有店" and str(getattr(row, "H", "")) == "星越L":
            rows.append(200.0 * k)
            continue
        rate = _lookup_standard(
            standard,
            vehicle=getattr(row, "H", ""),
            channel=getattr(row, "I", ""),
            dept=getattr(row, "A", ""),
            value_col="F",
        )
        rows.append(rate * k)
    return pd.Series(rows, index=ctx.index, dtype=float)


def _compute_aq_standard(ctx: pd.DataFrame, standard: pd.DataFrame) -> pd.Series:
    rows: list[float] = []
    for row in ctx.itertuples(index=False):
        k = _k_units(getattr(row, "K", 0))
        rate = _lookup_standard(
            standard,
            vehicle=getattr(row, "H", ""),
            channel=getattr(row, "I", ""),
            dept=getattr(row, "A", ""),
            value_col="H",
        )
        rows.append(rate * k)
    return pd.Series(rows, index=ctx.index, dtype=float)


def _compute_ai(ctx: pd.DataFrame) -> pd.Series:
    """``绩效整理表!AI`` — 加装绩效（K/L/S/U 闭包）。"""
    rows: list[float] = []
    for row in ctx.itertuples(index=False):
        k_raw = getattr(row, "K", None)
        if k_raw is None or (isinstance(k_raw, float) and pd.isna(k_raw)):
            rows.append(0.0)
            continue
        k = float(k_raw)
        order_total = float(pd.to_numeric(getattr(row, "L", None), errors="coerce") or 0)
        floor = float(pd.to_numeric(getattr(row, "S", None), errors="coerce") or 0)
        non_commission = float(pd.to_numeric(getattr(row, "U", None), errors="coerce") or 0)
        diff = floor - non_commission
        if k == 0:
            rows.append(order_total * 0.12)
        elif diff > 0:
            rows.append(diff * 0.12)
        else:
            rows.append(0.0)
    return pd.Series(rows, index=ctx.index, dtype=float)


def _compute_ah(
    ctx: pd.DataFrame,
    ag: pd.Series,
    ai: pd.Series,
    aj: pd.Series | float,
    ak: pd.Series | float,
) -> pd.Series:
    aj_n = pd.to_numeric(aj, errors="coerce").fillna(0)
    ak_n = pd.to_numeric(ak, errors="coerce").fillna(0)
    perf_sum = pd.to_numeric(ag, errors="coerce").fillna(0) + pd.to_numeric(ai, errors="coerce").fillna(0) + aj_n + ak_n
    aa = pd.to_numeric(ctx["AA"], errors="coerce").fillna(0)
    supplement_g = _load_supplement_g_labels()
    if "G" in ctx.columns:
        g_labels = ctx["G"].astype(str).str.strip()
    else:
        g_labels = pd.Series([""] * len(ctx), index=ctx.index)
    rows: list[float] = []
    for g_label, d_label, aa_val, sum_val in zip(
        g_labels, ctx["D"], aa, perf_sum, strict=True
    ):
        if g_label in supplement_g:
            rows.append(float("nan"))
            continue
        d_text = str(d_label)
        if d_text in _EXCLUDED_D or "二网" in d_text:
            rows.append(float("nan"))
            continue
        is_store = d_text in _STORE_D
        base = float(aa_val) * 0.14 if is_store else 0.0
        if is_store and float(aa_val) > 0:
            rows.append(float(aa_val) * 0.2)
            continue
        if base + float(sum_val) < 150:
            rows.append(150.0 - float(sum_val))
            continue
        rows.append(base if is_store else float("nan"))
    return pd.Series(rows, index=ctx.index, dtype=float)
