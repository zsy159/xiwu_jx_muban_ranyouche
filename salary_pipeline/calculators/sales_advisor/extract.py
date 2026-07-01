"""抽取销售顾问算薪输入与金标准对照。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from salary_pipeline.calculators.performance_sheet.order_context import enrich_order_context
from salary_pipeline.calculators.sales_advisor.formulas import compute_advisor_performance
from salary_pipeline.calculators.sales_advisor.registry import get_role
from salary_pipeline.calculators.sales_advisor.topology_specs import (
    HUB_LETTERS_W_AI,
    _topology_cells,
    hub_column_name,
    load_row_specs,
)
from salary_pipeline.calculators.sales_advisor.types import (
    AdvisorPerformanceInput,
    AdvisorPerformanceResult,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.pipelines.hub_formula_engine import HUB_COLUMN_MAP, HubFormulaEngine

HUB_SHEET = "提成汇总"
PERF_SHEET = "绩效整理表"
_LETTER_BY_HUB_NAME = {name: letter for letter, name in HUB_COLUMN_MAP.items()}


def _fill_static_hub_columns(
    result: AdvisorPerformanceResult,
    excel_row: int,
    loader: WorkbookLoader,
    *,
    bootstrap_from_golden: bool = False,
) -> AdvisorPerformanceResult:
    """无 topology 公式时不再回读金标准；留空由对账标灰提示手工填入。"""
    if not bootstrap_from_golden:
        return result
    cells = _topology_cells()
    for letter in HUB_LETTERS_W_AI:
        col_name = hub_column_name(letter)
        if col_name in result.hub_metrics:
            continue
        key = f"提成汇总!{letter}{excel_row}"
        if cells.get(key, {}).get("formula"):
            continue
        val = loader.read_cell_value(HUB_SHEET, f"{letter}{excel_row}")
        if val is None:
            continue
        try:
            result.hub_metrics[col_name] = float(val)
        except (TypeError, ValueError):
            continue
    return result


def build_eval_perf_frame(
    loader: WorkbookLoader,
    computed: pd.DataFrame,
    topology_path: Path,
    *,
    use_golden_perf_sheet: bool = False,
) -> pd.DataFrame:
    """Hub 一致的绩效整理表；默认仅用 computed，不读金标准整理表数值。"""
    engine = HubFormulaEngine(
        topology_path,
        loader,
        computed_perf_frame=computed,
        use_golden_perf_sheet=use_golden_perf_sheet,
        bootstrap_from_golden=False,
    )
    return engine._sheet_frame(PERF_SHEET)


def enrich_perf_frame(perf: pd.DataFrame, loader: WorkbookLoader) -> pd.DataFrame:
    """补全 topology 公式可能引用的车型列 H（如保险排除新博瑞）。"""
    if perf.empty:
        return perf
    out = perf.copy()
    if "H" not in out.columns and "O" in out.columns:
        ctx = enrich_order_context(out, loader)
        if "H" in ctx.columns:
            out["H"] = ctx["H"].values
    return out


def extract_advisor_input(row: pd.Series) -> AdvisorPerformanceInput:
    rate = row.get("销量完成率")
    return AdvisorPerformanceInput(
        name=str(row["姓名"]),
        store=str(row.get("店别") or ""),
        title=str(row.get("职务") or ""),
        excel_row=int(row["_excel_row"]),
        sales_completion_rate=float(rate) if pd.notna(rate) else 0.0,
    )


def compute_for_advisor(
    row: pd.Series,
    perf: pd.DataFrame,
    loader: WorkbookLoader,
    *,
    topology_path: Path | None = None,
    use_golden_perf_sheet: bool = False,
    bootstrap_from_golden: bool = False,
) -> AdvisorPerformanceResult:
    person = extract_advisor_input(row)
    specs = load_row_specs(person.excel_row)
    if topology_path is not None:
        eval_perf = build_eval_perf_frame(
            loader,
            perf,
            topology_path,
            use_golden_perf_sheet=use_golden_perf_sheet,
        )
    else:
        eval_perf = enrich_perf_frame(perf, loader)
    person.perf_frame_row_count = len(eval_perf)
    result = compute_advisor_performance(person, eval_perf, specs, loader)
    return _fill_static_hub_columns(
        result,
        person.excel_row,
        loader,
        bootstrap_from_golden=bootstrap_from_golden,
    )


def lookup_golden_hub(
    loader: WorkbookLoader,
    role_name: str,
    hub_column: str,
) -> float | None:
    role = get_role(role_name)
    if role is None:
        return None
    hub_row = role.get("hub_excel_row")
    if not hub_row:
        return None
    letter = _LETTER_BY_HUB_NAME.get(hub_column)
    if not letter:
        return None
    val = loader.read_cell_value(HUB_SHEET, f"{letter}{int(hub_row)}")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def lookup_golden_hub_all(
    loader: WorkbookLoader,
    role_name: str,
    columns: tuple[str, ...],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for col in columns:
        val = lookup_golden_hub(loader, role_name, col)
        if val is not None:
            out[col] = val
    return out


def match_advisor_row(row: pd.Series) -> bool:
    title = normalize_name(str(row.get("职务", "")))
    name = str(row.get("姓名", "")).strip()
    if not name or name == "空白":
        return False
    return title == normalize_name("销售顾问")
