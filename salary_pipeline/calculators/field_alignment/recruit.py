"""招聘字段拉通 ↔ RecruitTeamInput 映射。"""

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
from salary_pipeline.calculators.recruit.types import RecruitTeamInput

_FAMILY_ID = "recruit"


def load_recruit_alignment() -> FieldAlignmentFamily:
    return load_alignment_family(_FAMILY_ID)


def is_field_applicable(field: FieldDef, template: str) -> bool:
    return template in field.applicable


def not_applicable_reason(field: FieldDef, template: str) -> str:
    return field.not_applicable_note.get(template, "当前版式子表无此列")


def field_label_for_template(field: FieldDef, template: str) -> str:
    return field.label_by_template.get(template, field.label)


def values_from_inputs(inputs: RecruitTeamInput) -> dict[str, Any]:
    return {f.name: getattr(inputs, f.name) for f in dataclass_fields(RecruitTeamInput)}


def inputs_from_values(
    base: RecruitTeamInput | None,
    updates: dict[str, Any],
    template: str = "",
) -> RecruitTeamInput:
    data = values_from_inputs(base or RecruitTeamInput(
        name="",
        onboard_count=0.0,
        commission_per_hire=0.0,
        total_commission=0.0,
        allocation_ratio=0.0,
    ))
    data.update(updates)
    valid = {f.name for f in dataclass_fields(RecruitTeamInput)}
    return RecruitTeamInput(**{k: data[k] for k in valid if k in data})


def coerce_recruit_inputs(raw: Any, template: str = "") -> RecruitTeamInput:
    if isinstance(raw, RecruitTeamInput):
        return raw
    if isinstance(raw, dict):
        return inputs_from_values(None, raw, template)
    from salary_pipeline.calculators.recruit.registry import default_input_for_role

    return default_input_for_role({"name": "", "template": template or "team_allocation"})


def applicability_matrix(family: FieldAlignmentFamily | None = None) -> pd.DataFrame:
    family = family or load_recruit_alignment()
    template_ids = list(family.templates.keys())
    rows: list[dict[str, str]] = []
    for section, field_def in iter_fields(family):
        row: dict[str, str] = {
            "分组": section.label,
            "字段": field_def.label,
            "field_id": field_def.id,
        }
        for tid in template_ids:
            label = family.templates[tid]["label"]
            row[label] = "✓" if is_field_applicable(field_def, tid) else "—"
        rows.append(row)
    cols = ["分组", "字段", *[family.templates[t]["label"] for t in template_ids]]
    return pd.DataFrame(rows)[cols]


def applicability_matrix_wide(family: FieldAlignmentFamily | None = None) -> pd.DataFrame:
    family = family or load_recruit_alignment()
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
        rows.append(
            ["✓" if is_field_applicable(fd, tid) else "—" for fd in field_defs]
        )

    columns = pd.MultiIndex.from_tuples(col_tuples, names=["分组", "字段"])
    field_df = pd.DataFrame(rows, columns=columns)
    field_df.index = pd.Index(index_labels, name="版式")
    return field_df
