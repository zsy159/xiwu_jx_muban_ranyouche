"""销售顾问字段拉通 ↔ AdvisorAlignedInput 映射。"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any

import pandas as pd

from salary_pipeline.calculators.field_alignment.schema import (
    FieldAlignmentFamily,
    FieldDef,
    iter_fields,
    load_alignment_family,
)
from salary_pipeline.calculators.sales_advisor.aligned_input import (
    AdvisorAlignedInput,
    coerce_aligned_input,
    detect_template,
)

_FAMILY_ID = "sales_advisor"


def load_sales_advisor_alignment() -> FieldAlignmentFamily:
    return load_alignment_family(_FAMILY_ID)


def is_field_applicable(field: FieldDef, template: str) -> bool:
    return template in field.applicable


def not_applicable_reason(field: FieldDef, template: str) -> str:
    return field.not_applicable_note.get(template, "当前版式无此项")


def field_label_for_template(field: FieldDef, template: str) -> str:
    return field.label_by_template.get(template, field.label)


def values_from_inputs(inputs: AdvisorAlignedInput) -> dict[str, Any]:
    data = coerce_aligned_input(inputs)
    return {f.name: getattr(data, f.name) for f in dataclass_fields(AdvisorAlignedInput)}


def inputs_from_values(
    base: AdvisorAlignedInput | None,
    updates: dict[str, Any],
    template: str = "",
) -> AdvisorAlignedInput:
    data = values_from_inputs(base or AdvisorAlignedInput())
    data.update(updates)
    valid = {f.name for f in dataclass_fields(AdvisorAlignedInput)}
    return AdvisorAlignedInput(**{k: data[k] for k in valid if k in data})


def applicability_matrix_wide(family: FieldAlignmentFamily | None = None) -> pd.DataFrame:
    family = family or load_sales_advisor_alignment()
    template_ids = list(family.templates.keys())
    col_tuples: list[tuple[str, str]] = []
    field_defs: list[FieldDef] = []
    for section, field_def in iter_fields(family):
        col_tuples.append((section.label, field_def.label))
        field_defs.append(field_def)

    rows: list[list[str]] = []
    index_labels: list[str] = []
    for tid in template_ids:
        index_labels.append(family.templates[tid]["label"])
        rows.append(["✓" if is_field_applicable(fd, tid) else "—" for fd in field_defs])

    columns = pd.MultiIndex.from_tuples(col_tuples, names=["分组", "字段"])
    field_df = pd.DataFrame(rows, columns=columns)
    field_df.index = pd.Index(index_labels, name="版式")
    return field_df


def template_for_role(role: dict[str, Any]) -> str:
    if role.get("template"):
        return str(role["template"])
    hub_row = role.get("hub_excel_row")
    if hub_row:
        return detect_template(int(hub_row))
    return "personal_h"
