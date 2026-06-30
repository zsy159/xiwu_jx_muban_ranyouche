"""邀约专员字段拉通 ↔ InviteDccInput 映射。"""

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
from salary_pipeline.calculators.invite_specialist.migrate import coerce_invite_inputs
from salary_pipeline.calculators.invite_specialist.types import InviteDccInput

_FAMILY_ID = "invite_specialist"


def load_invite_alignment() -> FieldAlignmentFamily:
    return load_alignment_family(_FAMILY_ID)


def is_field_applicable(field: FieldDef, template: str) -> bool:
    return template in field.applicable


def not_applicable_reason(field: FieldDef, template: str) -> str:
    return field.not_applicable_note.get(template, "当前版式子表无此列")


def field_label_for_template(field: FieldDef, template: str) -> str:
    return field.label_by_template.get(template, field.label)


def values_from_inputs(inputs: InviteDccInput) -> dict[str, Any]:
    data = coerce_invite_inputs(inputs)
    return {f.name: getattr(data, f.name) for f in dataclass_fields(InviteDccInput)}


def inputs_from_values(
    base: InviteDccInput | None,
    updates: dict[str, Any],
) -> InviteDccInput:
    data = values_from_inputs(base or InviteDccInput())
    data.update(updates)
    valid = {f.name for f in dataclass_fields(InviteDccInput)}
    return InviteDccInput(**{k: data[k] for k in valid if k in data})


def applicability_matrix(family: FieldAlignmentFamily | None = None) -> pd.DataFrame:
    """纵表：字段为行、版式为列（供程序处理）。"""
    family = family or load_invite_alignment()
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
            if is_field_applicable(field_def, tid):
                row[label] = "✓"
            else:
                row[label] = "—"
        rows.append(row)
    cols = ["分组", "字段", *[family.templates[t]["label"] for t in template_ids]]
    return pd.DataFrame(rows)[cols]


def applicability_matrix_wide(family: FieldAlignmentFamily | None = None) -> pd.DataFrame:
    """横表：字段为列头、版式为行（界面展示）。"""
    family = family or load_invite_alignment()
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
            [
                "✓" if is_field_applicable(fd, tid) else "—"
                for fd in field_defs
            ]
        )

    columns = pd.MultiIndex.from_tuples(col_tuples, names=["分组", "字段"])
    field_df = pd.DataFrame(rows, columns=columns)
    field_df.index = pd.Index(index_labels, name="版式")
    return field_df


def applicability_matrix_display(family: FieldAlignmentFamily | None = None) -> pd.DataFrame:
    """界面展示用扁平行列（版式 + 字段列名换行）。"""
    wide = applicability_matrix_wide(family)
    field_headers = [f"{grp}\n{fld}" for grp, fld in wide.columns]
    rows = [[wide.index[i], *wide.iloc[i].tolist()] for i in range(len(wide))]
    return pd.DataFrame(rows, columns=["版式", *field_headers])
