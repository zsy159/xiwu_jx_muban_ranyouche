"""岗位字段拉通 — 按岗位族分发矩阵与输入映射。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from salary_pipeline.calculators.field_alignment import (
    direct_store_manager as dsm_align,
    invite_specialist as invite_align,
    new_media as nm_align,
    recruit as recruit_align,
    sales_advisor as sa_align,
)
from salary_pipeline.calculators.field_alignment.schema import FieldAlignmentFamily, FieldDef


@dataclass(frozen=True)
class AlignmentFamilyRuntime:
    applicability_matrix_wide: Callable[[FieldAlignmentFamily | None], pd.DataFrame]
    field_label_for_template: Callable[[FieldDef, str], str]
    is_field_applicable: Callable[[FieldDef, str], bool]
    not_applicable_reason: Callable[[FieldDef, str], str]
    values_from_inputs: Callable[[Any], dict[str, Any]]
    inputs_from_values: Callable[..., Any]
    coerce_inputs: Callable[..., Any]
    list_roles: Callable[[], list[dict[str, Any]]]
    extract_role_inputs: Callable[..., Any]
    default_input_for_role: Callable[[dict[str, Any]], Any]
    compute_for_role: Callable[..., Any]
    lookup_golden: Callable[..., float | None]
    hub_label: str
    save_filename: str
    role_format: Callable[[dict[str, Any], FieldAlignmentFamily], str]
    supports_alignment_form: bool = True
    eager_extract: bool = True


def _customer_role_format(role: dict[str, Any], alignment: FieldAlignmentFamily) -> str:
    tpl = alignment.templates.get(role["template"], {}).get("label", role["template"])
    return f"{role['name']}（{role.get('title', '')} · {tpl}）"


def _invite_role_format(role: dict[str, Any], alignment: FieldAlignmentFamily) -> str:
    tpl = alignment.templates.get(role["template"], {}).get("label", role["template"])
    return f"{role['name']}（{role.get('company', '')} · {tpl}）"


def _new_media_role_format(role: dict[str, Any], alignment: FieldAlignmentFamily) -> str:
    tpl = alignment.templates.get(role["template"], {}).get("label", role["template"])
    return f"{role['name']}（{role.get('title', '')} · {tpl}）"


def _recruit_role_format(role: dict[str, Any], alignment: FieldAlignmentFamily) -> str:
    from salary_pipeline.calculators.recruit import is_hub_linked

    tpl = alignment.templates.get(role["template"], {}).get("label", role["template"])
    hub_tag = "" if is_hub_linked(role) else " · 仅子表"
    return f"{role['name']}（{role.get('store', '')} · {role.get('title', '')} · {tpl}{hub_tag}）"


def _sales_advisor_role_format(role: dict[str, Any], alignment: FieldAlignmentFamily) -> str:
    tpl = alignment.templates.get(role.get("template", ""), {}).get(
        "label", role.get("template", "")
    )
    hub_tag = "" if role.get("hub_linked", True) else " · 仅子表"
    return f"{role['name']}（{tpl}{hub_tag}）"


def _direct_store_manager_role_format(
    role: dict[str, Any], alignment: FieldAlignmentFamily
) -> str:
    blocks = role.get("excel_blocks") or []
    if len(blocks) > 1:
        tpl = alignment.templates.get("store_block_dual", {}).get(
            "label", "双店门店块"
        )
    else:
        tpl = alignment.templates.get(role["template"], {}).get("label", role["template"])
    return f"{role['name']}（{role.get('store', '')} · {tpl}）"


def get_family_runtime(family_id: str) -> AlignmentFamilyRuntime:
    if family_id == "invite_specialist":
        from salary_pipeline.calculators.invite_specialist import (
            compute_for_role,
            extract_role_inputs,
            list_roles,
            lookup_golden_af,
        )
        from salary_pipeline.calculators.invite_specialist.migrate import coerce_invite_inputs
        from salary_pipeline.calculators.invite_specialist.registry import (
            default_input_for_role,
        )

        def _inputs_from_values(base: Any, updates: dict[str, Any], template: str = "") -> Any:
            return invite_align.inputs_from_values(base, updates)

        def _coerce(raw: Any, template: str = "") -> Any:
            return coerce_invite_inputs(raw)

        return AlignmentFamilyRuntime(
            applicability_matrix_wide=invite_align.applicability_matrix_wide,
            field_label_for_template=invite_align.field_label_for_template,
            is_field_applicable=invite_align.is_field_applicable,
            not_applicable_reason=invite_align.not_applicable_reason,
            values_from_inputs=invite_align.values_from_inputs,
            inputs_from_values=_inputs_from_values,
            coerce_inputs=_coerce,
            list_roles=list_roles,
            extract_role_inputs=extract_role_inputs,
            default_input_for_role=default_input_for_role,
            compute_for_role=compute_for_role,
            lookup_golden=lookup_golden_af,
            hub_label="子表 AF / 崇州 AD",
            save_filename="invite_specialist_aligned_inputs.json",
            role_format=_invite_role_format,
        )

    if family_id == "new_media":
        from salary_pipeline.calculators.new_media import (
            compute_for_role,
            extract_role_inputs,
            list_roles,
            lookup_golden_ab,
        )
        from salary_pipeline.calculators.new_media.registry import default_input_for_role

        return AlignmentFamilyRuntime(
            applicability_matrix_wide=nm_align.applicability_matrix_wide,
            field_label_for_template=nm_align.field_label_for_template,
            is_field_applicable=nm_align.is_field_applicable,
            not_applicable_reason=nm_align.not_applicable_reason,
            values_from_inputs=nm_align.values_from_inputs,
            inputs_from_values=nm_align.inputs_from_values,
            coerce_inputs=nm_align.coerce_new_media_inputs,
            list_roles=list_roles,
            extract_role_inputs=extract_role_inputs,
            default_input_for_role=default_input_for_role,
            compute_for_role=compute_for_role,
            lookup_golden=lookup_golden_ab,
            hub_label="子表 Q / Hub W（AB 汇总）",
            save_filename="new_media_aligned_inputs.json",
            role_format=_new_media_role_format,
        )

    if family_id == "customer_specialist":
        from salary_pipeline.calculators.customer_specialist import (
            compute_for_role,
            extract_role_inputs,
            list_roles,
            lookup_golden_cells,
        )
        from salary_pipeline.calculators.field_alignment import (
            customer_specialist as cs_align,
        )
        from salary_pipeline.calculators.customer_specialist.registry import (
            default_input_for_role,
        )

        def _lookup_golden(loader: Any, name: str) -> dict[str, float] | None:
            cells = lookup_golden_cells(loader, name)
            return cells or None

        return AlignmentFamilyRuntime(
            applicability_matrix_wide=cs_align.applicability_matrix_wide,
            field_label_for_template=cs_align.field_label_for_template,
            is_field_applicable=cs_align.is_field_applicable,
            not_applicable_reason=cs_align.not_applicable_reason,
            values_from_inputs=cs_align.values_from_inputs,
            inputs_from_values=cs_align.inputs_from_values,
            coerce_inputs=cs_align.coerce_customer_inputs,
            list_roles=list_roles,
            extract_role_inputs=extract_role_inputs,
            default_input_for_role=default_input_for_role,
            compute_for_role=compute_for_role,
            lookup_golden=_lookup_golden,
            hub_label="按人直引（W/X/Y 等）",
            save_filename="customer_specialist_aligned_inputs.json",
            role_format=_customer_role_format,
            supports_alignment_form=True,
        )

    if family_id == "recruit":
        from salary_pipeline.calculators.recruit import (
            compute_for_role,
            extract_role_inputs,
            is_hub_linked,
            list_roles,
            lookup_golden_cells,
            lookup_golden_hub,
        )
        from salary_pipeline.calculators.recruit.registry import default_input_for_role

        def _lookup_golden(loader: Any, name: str) -> float | None:
            role = next((r for r in list_roles() if r["name"] == name), None)
            if role and is_hub_linked(role):
                return lookup_golden_hub(loader, name)
            cells = lookup_golden_cells(loader, name)
            return cells.get("提成金额")

        return AlignmentFamilyRuntime(
            applicability_matrix_wide=recruit_align.applicability_matrix_wide,
            field_label_for_template=recruit_align.field_label_for_template,
            is_field_applicable=recruit_align.is_field_applicable,
            not_applicable_reason=recruit_align.not_applicable_reason,
            values_from_inputs=recruit_align.values_from_inputs,
            inputs_from_values=recruit_align.inputs_from_values,
            coerce_inputs=recruit_align.coerce_recruit_inputs,
            list_roles=list_roles,
            extract_role_inputs=extract_role_inputs,
            default_input_for_role=default_input_for_role,
            compute_for_role=compute_for_role,
            lookup_golden=_lookup_golden,
            hub_label="子表 W / Hub Z（保险绩效）",
            save_filename="recruit_aligned_inputs.json",
            role_format=_recruit_role_format,
        )

    if family_id == "sales_advisor":
        import streamlit as st

        from salary_pipeline.app._pipeline_cache import (
            get_advisor_person_row,
            get_eval_perf_frame,
            get_workbook_loader,
        )
        from salary_pipeline.calculators.sales_advisor.aligned_input import (
            coerce_aligned_input,
            compute_aligned,
            default_aligned_input,
            extract_aligned_inputs,
            list_roles_with_template,
        )
        from salary_pipeline.calculators.sales_advisor import lookup_golden_hub
        from salary_pipeline.calculators.sales_advisor.registry import is_hub_linked

        def _month_id() -> str:
            return str(st.session_state.get("month_id", ""))

        def _person_row(name: str) -> pd.Series | None:
            return get_advisor_person_row(_month_id(), name)

        def _list_roles() -> list[dict[str, Any]]:
            return [r for r in list_roles_with_template() if is_hub_linked(r)]

        def _extract_role_inputs(loader: Any, name: str) -> Any:
            row = _person_row(name)
            month_id = _month_id()
            eval_perf = get_eval_perf_frame(month_id)
            if row is None or eval_perf is None:
                role = next((r for r in _list_roles() if r["name"] == name), None)
                return default_aligned_input(role or {"name": name})
            return extract_aligned_inputs(loader, eval_perf, row)

        def _compute_for_role(name: str, inputs: Any, loader: Any = None) -> Any:
            if loader is None:
                loader = get_workbook_loader(_month_id())
            if loader is None:
                raise ValueError("当月 Excel 不存在")
            return compute_aligned(name, coerce_aligned_input(inputs), loader)

        def _default_input_for_role(role: dict[str, Any]) -> Any:
            return default_aligned_input(role)

        def _lookup_golden(loader: Any, name: str) -> float | None:
            return lookup_golden_hub(loader, name, "整车绩效")

        def _inputs_from_values(base: Any, updates: dict[str, Any], template: str = "") -> Any:
            return sa_align.inputs_from_values(base, updates, template)

        def _coerce(raw: Any, template: str = "") -> Any:
            return coerce_aligned_input(raw)

        return AlignmentFamilyRuntime(
            applicability_matrix_wide=sa_align.applicability_matrix_wide,
            field_label_for_template=sa_align.field_label_for_template,
            is_field_applicable=sa_align.is_field_applicable,
            not_applicable_reason=sa_align.not_applicable_reason,
            values_from_inputs=sa_align.values_from_inputs,
            inputs_from_values=_inputs_from_values,
            coerce_inputs=_coerce,
            list_roles=_list_roles,
            extract_role_inputs=_extract_role_inputs,
            default_input_for_role=_default_input_for_role,
            compute_for_role=_compute_for_role,
            lookup_golden=_lookup_golden,
            hub_label="Hub 绩效六项（绩效整理表汇总）",
            save_filename="sales_advisor_aligned_inputs.json",
            role_format=_sales_advisor_role_format,
            eager_extract=False,
        )

    if family_id == "direct_store_manager":
        from salary_pipeline.calculators.direct_store_manager import (
            compute_for_role,
            extract_role_inputs,
            list_roles,
            lookup_golden_r,
        )
        from salary_pipeline.calculators.direct_store_manager.registry import (
            default_input_for_role,
        )

        return AlignmentFamilyRuntime(
            applicability_matrix_wide=dsm_align.applicability_matrix_wide,
            field_label_for_template=dsm_align.field_label_for_template,
            is_field_applicable=dsm_align.is_field_applicable,
            not_applicable_reason=dsm_align.not_applicable_reason,
            values_from_inputs=dsm_align.values_from_inputs,
            inputs_from_values=dsm_align.inputs_from_values,
            coerce_inputs=dsm_align.coerce_direct_store_manager_inputs,
            list_roles=list_roles,
            extract_role_inputs=extract_role_inputs,
            default_input_for_role=default_input_for_role,
            compute_for_role=compute_for_role,
            lookup_golden=lookup_golden_r,
            hub_label="子表 R / Hub AK（整车完成考核）",
            save_filename="direct_store_manager_aligned_inputs.json",
            role_format=_direct_store_manager_role_format,
        )

    raise KeyError(f"unsupported alignment family: {family_id}")
