"""直营店经理字段拉通 ↔ StoreBlockInput 映射。"""

from __future__ import annotations

from dataclasses import asdict, fields as dataclass_fields
from typing import Any

import pandas as pd

from salary_pipeline.calculators.direct_store_manager.types import StoreBlockInput
from salary_pipeline.calculators.field_alignment.schema import (
    FieldAlignmentFamily,
    FieldDef,
    iter_fields,
    load_alignment_family,
)

_FAMILY_ID = "direct_store_manager"
_AGG_KEYS = (
    "showroom_task",
    "showroom_actual",
    "showroom_ev_actual",
    "channel_task",
    "channel_actual",
    "channel_ev_task",
    "attach_commission",
    "fixed_performance",
    "extra_vehicle_commission",
)


def load_direct_store_manager_alignment() -> FieldAlignmentFamily:
    return load_alignment_family(_FAMILY_ID)


def is_field_applicable(field: FieldDef, template: str) -> bool:
    if template == "store_block":
        return "store_block" in field.applicable
    return template in field.applicable


def not_applicable_reason(field: FieldDef, template: str) -> str:
    return field.not_applicable_note.get(template, "当前版式子表无此列")


def field_label_for_template(field: FieldDef, template: str) -> str:
    return field.label_by_template.get(template, field.label)


def _aggregate_blocks(blocks: list[StoreBlockInput]) -> dict[str, Any]:
    if not blocks:
        return {}
    if len(blocks) == 1:
        return asdict(blocks[0])
    merged = asdict(blocks[0])
    for block in blocks[1:]:
        data = asdict(block)
        for key in _AGG_KEYS:
            merged[key] = float(merged.get(key, 0) or 0) + float(data.get(key, 0) or 0)
    labels = [b.store_label for b in blocks if b.store_label]
    merged["store_label"] = " + ".join(labels) if labels else merged.get("store_label", "")
    merged["_block_count"] = len(blocks)
    return merged


def values_from_inputs(inputs: list[StoreBlockInput] | StoreBlockInput) -> dict[str, Any]:
    if isinstance(inputs, StoreBlockInput):
        return asdict(inputs)
    return _aggregate_blocks(list(inputs))


def inputs_from_values(
    base: list[StoreBlockInput] | None,
    updates: dict[str, Any],
    template: str = "",
) -> list[StoreBlockInput]:
    blocks = list(base or [StoreBlockInput()])
    if len(blocks) == 1:
        data = asdict(blocks[0])
        data.update(updates)
        valid = {f.name for f in dataclass_fields(StoreBlockInput)}
        return [StoreBlockInput(**{k: data[k] for k in valid if k in data})]

    updated: list[StoreBlockInput] = []
    valid = {f.name for f in dataclass_fields(StoreBlockInput)}
    for block in blocks:
        data = asdict(block)
        for key, value in updates.items():
            if key.startswith("_") or key not in valid:
                continue
            data[key] = value
        updated.append(StoreBlockInput(**{k: data[k] for k in valid}))
    return updated


def coerce_direct_store_manager_inputs(
    raw: Any, template: str = ""
) -> list[StoreBlockInput]:
    if isinstance(raw, list) and raw and isinstance(raw[0], StoreBlockInput):
        return raw
    if isinstance(raw, StoreBlockInput):
        return [raw]
    if isinstance(raw, dict):
        valid = {f.name for f in dataclass_fields(StoreBlockInput)}
        return [StoreBlockInput(**{k: raw[k] for k in valid if k in raw})]
    from salary_pipeline.calculators.direct_store_manager.registry import (
        default_input_for_role,
    )

    return default_input_for_role({"template": template or "store_block", "store": ""})


def applicability_matrix(family: FieldAlignmentFamily | None = None) -> pd.DataFrame:
    family = family or load_direct_store_manager_alignment()
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
    family = family or load_direct_store_manager_alignment()
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
