"""销售顾问 Hub W–AI 显式算薪 — 绩效整理表 SUMIF/SUMIFS + 完成率。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from salary_pipeline.calculators.sales_advisor.types import (
    AdvisorPerformanceInput,
    AdvisorPerformanceResult,
    HubColumnFormula,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.ops.basic import sumif_by_key

HUB_SHEET = "提成汇总"


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sumif_perf(
    perf: pd.DataFrame,
    key_col: str,
    val_col: str,
    criteria: Any,
) -> float:
    if perf.empty or val_col not in perf.columns:
        return 0.0
    if key_col not in perf.columns:
        return 0.0
    return float(sumif_by_key(perf, key_col, val_col, str(criteria)))


def _sumifs_by_advisor(
    perf: pd.DataFrame,
    val_col: str,
    advisor_name: str,
    *,
    exclude_vehicle: str | None = None,
) -> float:
    if perf.empty or val_col not in perf.columns or "P" not in perf.columns:
        return 0.0
    mask = perf["P"].astype(str).map(normalize_name) == normalize_name(advisor_name)
    if exclude_vehicle and "H" in perf.columns:
        mask &= perf["H"].astype(str) != exclude_vehicle
    subset = perf.loc[mask, val_col]
    return float(pd.to_numeric(subset, errors="coerce").fillna(0).sum())


def resolve_multiplier(
    ref: str | None,
    *,
    excel_row: int,
    person: AdvisorPerformanceInput,
    loader: WorkbookLoader,
) -> float:
    if not ref:
        return 1.0
    ref = ref.upper()
    if ref.startswith("H"):
        row_num = int(ref[1:])
        if row_num == excel_row and person.sales_completion_rate > 0:
            return person.sales_completion_rate
        val = loader.read_cell_value(HUB_SHEET, ref)
        if val is not None:
            return _num(val)
        return person.sales_completion_rate
    if ref.startswith("BA") or ref[0].isalpha():
        val = loader.read_cell_value(HUB_SHEET, ref)
        return _num(val)
    return 1.0


def resolve_sumif_criteria(
    criteria_ref: str | None,
    *,
    advisor_name: str,
    loader: WorkbookLoader,
) -> Any:
    if not criteria_ref:
        return advisor_name
    val = loader.read_cell_value(HUB_SHEET, criteria_ref.upper())
    if val is None:
        return advisor_name
    return val


def eval_hub_column(
    spec: HubColumnFormula,
    perf: pd.DataFrame,
    person: AdvisorPerformanceInput,
    loader: WorkbookLoader,
) -> float:
    if spec.kind == "sumifs":
        base = _sumifs_by_advisor(
            perf,
            spec.perf_columns[0],
            person.name,
            exclude_vehicle=spec.exclude_vehicle,
        )
        rate = resolve_multiplier(
            spec.multiply_ref,
            excel_row=person.excel_row,
            person=person,
            loader=loader,
        )
        return base * rate + spec.add_const

    if spec.kind == "sumif_chain":
        total = 0.0
        for col in spec.perf_columns:
            total += _sumif_perf(perf, "P", col, person.name)
        return total

    if spec.kind == "sumif":
        criteria = resolve_sumif_criteria(
            spec.sumif_criteria_ref,
            advisor_name=person.name,
            loader=loader,
        )
        return _sumif_perf(perf, spec.sumif_key_col, spec.perf_columns[0], criteria)

    return 0.0


def compute_advisor_performance(
    person: AdvisorPerformanceInput,
    perf: pd.DataFrame,
    specs: dict[str, HubColumnFormula],
    loader: WorkbookLoader,
) -> AdvisorPerformanceResult:
    metrics: dict[str, float] = {}
    for hub_col, spec in specs.items():
        metrics[hub_col] = eval_hub_column(spec, perf, person, loader)
    return AdvisorPerformanceResult(name=person.name, hub_metrics=metrics)
