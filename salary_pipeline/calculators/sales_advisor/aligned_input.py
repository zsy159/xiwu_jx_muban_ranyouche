"""销售顾问字段拉通 — 按人汇总绩效整理表列的手工输入与复算。"""

from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import pandas as pd

from salary_pipeline.calculators.sales_advisor.extract import (
    _fill_static_hub_columns,
    build_eval_perf_frame,
)
from salary_pipeline.calculators.sales_advisor.formulas import (
    HUB_SHEET,
    _num,
    resolve_sumif_criteria,
)
from salary_pipeline.calculators.sales_advisor.registry import get_role
from salary_pipeline.calculators.sales_advisor.topology_specs import load_row_specs
from salary_pipeline.calculators.sales_advisor.types import (
    AdvisorPerformanceResult,
    HubColumnFormula,
)
from salary_pipeline.data_ingestion.data_loader import (
    WorkbookLoader,
    lookup_combined_completion_rate,
    normalize_name,
)

# 对账门槛六项（hub_performance.yaml parity_gate）
GATE_HUB_COLUMNS = (
    "整车绩效",
    "加装绩效",
    "保险绩效",
    "金融绩效",
    "爱车宝绩效",
    "上户绩效",
)

# Hub W–AI 全部 13 列（提成汇总字母序 W→AI）
ALL_HUB_COLUMNS = (
    "整车绩效",
    "权限结余绩效",
    "加装绩效",
    "保险绩效",
    "金融绩效",
    "爱车宝绩效",
    "上户绩效",
    "盈利产品绩效",
    "延保提成",
    "特殊车型+指定车型",
    "座位险提成",
    "二手车提成",
    "玻碎险提成",
)

PERF_ATTR_BY_COL = {
    "AG": "perf_ag_sum",
    "AH": "perf_ah_sum",
    "AI": "perf_ai_sum",
    "AJ": "perf_aj_sum",
    "AK": "perf_ak_sum",
    "AL": "perf_al_sum",
    "AM": "perf_am_sum",
    "AN": "perf_an_sum",
    "AO": "perf_ao_sum",
    "AP": "perf_ap_sum",
    "AQ": "perf_aq_sum",
    "AR": "perf_ar_sum",
    "AS": "perf_as_sum",
    "AT": "perf_at_sum",
}


@dataclass
class AdvisorAlignedInput:
    """绩效整理表按人汇总后的手工填写项（对应 Hub SUMIF/SUMIFS 来源列）。"""

    sales_completion_rate: float = 1.0
    store_completion_rate: float = 1.0
    insurance_add_const: float = 0.0
    perf_ag_sum: float = 0.0
    perf_ah_sum: float = 0.0
    perf_ai_sum: float = 0.0
    perf_aj_sum: float = 0.0
    perf_ak_sum: float = 0.0
    perf_al_sum: float = 0.0
    perf_am_sum: float = 0.0
    perf_an_sum: float = 0.0
    perf_ao_sum: float = 0.0
    perf_ap_sum: float = 0.0
    perf_aq_sum: float = 0.0
    perf_ar_sum: float = 0.0
    perf_as_sum: float = 0.0
    perf_at_sum: float = 0.0

    def perf_sum(self, col: str) -> float:
        attr = PERF_ATTR_BY_COL.get(col.upper())
        if not attr:
            return 0.0
        return float(getattr(self, attr, 0.0) or 0.0)


@dataclass
class AdvisorAlignedResult:
    name: str
    hub_metrics: dict[str, float] = field(default_factory=dict)
    breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def performance_salary(self) -> float:
        return float(self.hub_metrics.get("整车绩效", 0.0))

    @property
    def hub_vehicle_performance(self) -> float:
        return self.performance_salary


def detect_template(excel_row: int) -> str:
    """Topology 行号回放判定模板（reconcile / 字段拉通 GUI 专用，非生产路径）。

    生产路径（SalesAdvisorPerformanceModule）改用
    ``hub_rule_engine.resolve_sales_advisor_template``（按店别 + 姓名覆盖），
    不依赖金标准行号；行号回放对行号漂移（人员调店/排班变化）不健壮，仅保留
    用于 topology reconcile 对比与手工字段拉通编辑器。
    """
    specs = load_row_specs(excel_row)
    vehicle = specs.get("整车绩效")
    if vehicle and vehicle.multiply_ref and vehicle.multiply_ref.upper().startswith("BA"):
        return "store_ba"
    insurance = specs.get("保险绩效")
    if insurance and insurance.add_const:
        return "insurance_add"
    return "personal_h"


def _resolve_multiplier_aligned(
    ref: str | None,
    *,
    advisor_name: str,
    excel_row: int,
    aligned: AdvisorAlignedInput,
    loader: WorkbookLoader,
) -> float:
    if not ref:
        return 1.0
    ref = ref.upper()
    if ref.startswith("H"):
        row_num = int(ref[1:])
        if row_num == excel_row:
            return aligned.sales_completion_rate
        val = loader.read_cell_value(HUB_SHEET, ref)
        return _num(val) if val is not None else aligned.sales_completion_rate
    if ref.startswith("BA"):
        rate = lookup_combined_completion_rate(loader, advisor_name)
        if rate is not None:
            return rate
        return aligned.store_completion_rate
    val = loader.read_cell_value(HUB_SHEET, ref)
    return _num(val)


def eval_hub_column_aligned(
    spec: HubColumnFormula,
    *,
    advisor_name: str,
    excel_row: int,
    aligned: AdvisorAlignedInput,
    loader: WorkbookLoader,
) -> float:
    if spec.kind == "sumifs":
        base = sum(aligned.perf_sum(col) for col in spec.perf_columns)
        rate = _resolve_multiplier_aligned(
            spec.multiply_ref,
            advisor_name=advisor_name,
            excel_row=excel_row,
            aligned=aligned,
            loader=loader,
        )
        add = float(spec.add_const or 0)
        if spec.hub_column == "保险绩效" and not add:
            add = float(aligned.insurance_add_const or 0)
        return base * rate + add

    if spec.kind == "sumif_chain":
        return sum(aligned.perf_sum(col) for col in spec.perf_columns)

    if spec.kind == "sumif":
        if spec.sumif_criteria_ref:
            criteria = resolve_sumif_criteria(
                spec.sumif_criteria_ref,
                advisor_name=advisor_name,
                loader=loader,
            )
            _ = criteria
        return sum(aligned.perf_sum(col) for col in spec.perf_columns)

    return 0.0


def compute_aligned(
    role_name: str,
    aligned: AdvisorAlignedInput,
    loader: WorkbookLoader,
) -> AdvisorAlignedResult:
    role = get_role(role_name)
    if role is None:
        raise KeyError(role_name)
    excel_row = int(role.get("hub_excel_row") or 0)
    if not excel_row:
        raise ValueError(f"{role_name} 无 hub_excel_row，仅子表顾问请用销售提成标准")

    specs = load_row_specs(excel_row)
    hub_metrics: dict[str, float] = {}
    breakdown: dict[str, float] = {}

    for hub_col, spec in specs.items():
        hub_metrics[hub_col] = eval_hub_column_aligned(
            spec,
            advisor_name=role_name,
            excel_row=excel_row,
            aligned=aligned,
            loader=loader,
        )
        if spec.kind == "sumifs" and spec.perf_columns:
            col = spec.perf_columns[0]
            breakdown[f"绩效整理表 {col}"] = aligned.perf_sum(col)

    perf_result = _fill_static_hub_columns(
        AdvisorPerformanceResult(name=role_name, hub_metrics=hub_metrics),
        excel_row,
        loader,
    )
    hub_metrics = perf_result.hub_metrics

    return AdvisorAlignedResult(
        name=role_name,
        hub_metrics=hub_metrics,
        breakdown=breakdown,
    )


def default_aligned_input(role: dict[str, Any]) -> AdvisorAlignedInput:
    excel_row = int(role.get("hub_excel_row") or 0)
    aligned = AdvisorAlignedInput()
    if excel_row:
        specs = load_row_specs(excel_row)
        ins = specs.get("保险绩效")
        if ins and ins.add_const:
            aligned.insurance_add_const = float(ins.add_const)
    return aligned


def _sum_perf_column(perf: pd.DataFrame, col: str, advisor_name: str) -> float:
    if perf.empty or col not in perf.columns or "P" not in perf.columns:
        return 0.0
    mask = perf["P"].astype(str).map(normalize_name) == normalize_name(advisor_name)
    return float(pd.to_numeric(perf.loc[mask, col], errors="coerce").fillna(0).sum())


def extract_aligned_inputs(
    loader: WorkbookLoader,
    perf: pd.DataFrame,
    person_row: pd.Series,
) -> AdvisorAlignedInput:
    name = str(person_row["姓名"])
    excel_row = int(person_row["_excel_row"])
    template = detect_template(excel_row)
    rate = person_row.get("销量完成率")
    sales_rate = float(rate) if pd.notna(rate) else 0.0
    h_val = loader.read_cell_value(HUB_SHEET, f"H{excel_row}")
    if sales_rate <= 0 and h_val is not None:
        sales_rate = _num(h_val)
    aligned = AdvisorAlignedInput(
        sales_completion_rate=sales_rate,
        perf_ag_sum=_sum_perf_column(perf, "AG", name),
        perf_ah_sum=_sum_perf_column(perf, "AH", name),
        perf_ai_sum=_sum_perf_column(perf, "AI", name),
        perf_aj_sum=_sum_perf_column(perf, "AJ", name),
        perf_ak_sum=_sum_perf_column(perf, "AK", name),
        perf_al_sum=_sum_perf_column(perf, "AL", name),
        perf_am_sum=_sum_perf_column(perf, "AM", name),
        perf_an_sum=_sum_perf_column(perf, "AN", name),
        perf_ao_sum=_sum_perf_column(perf, "AO", name),
        perf_ap_sum=_sum_perf_column(perf, "AP", name),
        perf_aq_sum=_sum_perf_column(perf, "AQ", name),
        perf_ar_sum=_sum_perf_column(perf, "AR", name),
        perf_as_sum=_sum_perf_column(perf, "AS", name),
        perf_at_sum=_sum_perf_column(perf, "AT", name),
    )
    if template == "store_ba":
        ba_rate = lookup_combined_completion_rate(loader, name)
        if ba_rate is not None:
            aligned.store_completion_rate = ba_rate

    specs = load_row_specs(excel_row)
    ins = specs.get("保险绩效")
    if ins and ins.add_const:
        aligned.insurance_add_const = float(ins.add_const)

    return aligned


def registration_performance_total(aligned: AdvisorAlignedInput) -> float:
    """Hub「上户绩效」= 绩效整理表 AN + AS 按人汇总。"""
    return float(aligned.perf_an_sum or 0) + float(aligned.perf_as_sum or 0)


def aligned_input_to_dict(aligned: AdvisorAlignedInput) -> dict[str, Any]:
    return asdict(aligned)


def _field_default(field_def: Any) -> Any:
    if field_def.default is not MISSING:
        return field_def.default
    if field_def.default_factory is not MISSING:
        return field_def.default_factory()
    raise ValueError(f"AdvisorAlignedInput.{field_def.name} has no default")


def coerce_aligned_input(raw: Any) -> AdvisorAlignedInput:
    """Normalize dict / legacy session instances to a full AdvisorAlignedInput."""
    field_defs = fields(AdvisorAlignedInput)
    if isinstance(raw, AdvisorAlignedInput):
        data = {
            f.name: getattr(raw, f.name)
            if hasattr(raw, f.name)
            else _field_default(f)
            for f in field_defs
        }
        return AdvisorAlignedInput(**data)
    if isinstance(raw, dict):
        valid = {f.name for f in field_defs}
        return AdvisorAlignedInput(**{k: raw[k] for k in valid if k in raw})
    return AdvisorAlignedInput()


def extract_role_inputs(
    loader: WorkbookLoader,
    role_name: str,
    *,
    perf: pd.DataFrame,
    person_row: pd.Series,
    topology_path: Path | None = None,
) -> AdvisorAlignedInput:
    if topology_path is not None:
        eval_perf = build_eval_perf_frame(loader, perf, topology_path)
    else:
        eval_perf = perf
    return extract_aligned_inputs(loader, eval_perf, person_row)


def list_roles_with_template() -> list[dict[str, Any]]:
    from salary_pipeline.calculators.field_alignment.sales_advisor import template_for_role
    from salary_pipeline.calculators.sales_advisor.registry import list_roles

    return [{**role, "template": template_for_role(role)} for role in list_roles()]
