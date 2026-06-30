"""新媒体字段拉通 ↔ LiveAnchorInput / VideoOpsInput / … 映射。"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import pandas as pd

from salary_pipeline.calculators.field_alignment.schema import (
    FieldAlignmentFamily,
    FieldDef,
    iter_fields,
    load_alignment_family,
)
from salary_pipeline.calculators.new_media.types import (
    LiveAnchorInput,
    ManualPerformanceInput,
    MetricPair,
    OpsManagerInput,
    VideoOpsInput,
)

_FAMILY_ID = "new_media"
_PAIR_ATTRS = (
    "live_sessions",
    "leads",
    "fans",
    "videos",
    "play_count",
    "short_video_fans",
    "xiaohongshu",
    "video_creations",
    "store_visits",
)


def load_new_media_alignment() -> FieldAlignmentFamily:
    return load_alignment_family(_FAMILY_ID)


def is_field_applicable(field: FieldDef, template: str) -> bool:
    return template in field.applicable


def not_applicable_reason(field: FieldDef, template: str) -> str:
    return field.not_applicable_note.get(template, "当前版式子表无此列")


def field_label_for_template(field: FieldDef, template: str) -> str:
    return field.label_by_template.get(template, field.label)


def _pair_from_flat(data: dict[str, Any], key: str) -> MetricPair:
    return MetricPair(
        target=float(data.get(f"{key}_target", 0) or 0),
        actual=float(data.get(f"{key}_actual", 0) or 0),
    )


def values_from_inputs(inputs: Any) -> dict[str, Any]:
    if isinstance(inputs, ManualPerformanceInput):
        return {"performance_salary": inputs.performance_salary}

    flat: dict[str, Any] = {}
    for key, value in asdict(inputs).items():
        if isinstance(value, dict) and "target" in value and "actual" in value:
            flat[f"{key}_target"] = value["target"]
            flat[f"{key}_actual"] = value["actual"]
        else:
            flat[key] = value
    return flat


def inputs_from_values(
    base: Any | None,
    updates: dict[str, Any],
    template: str,
) -> Any:
    data = values_from_inputs(base) if base is not None else {}
    data.update(updates)

    if template == "manual":
        return ManualPerformanceInput(
            performance_salary=float(data.get("performance_salary", 0) or 0),
        )

    if template == "live_anchor":
        return LiveAnchorInput(
            live_sessions=_pair_from_flat(data, "live_sessions"),
            leads=_pair_from_flat(data, "leads"),
            fans=_pair_from_flat(data, "fans"),
            videos=_pair_from_flat(data, "videos"),
            kpi_base=float(data.get("kpi_base", 7000) or 0),
            score_weights=tuple(data.get("score_weights", (40.0, 40.0, 10.0, 10.0))),
            terminal_unit_rate=float(data.get("terminal_unit_rate", 50) or 0),
            terminal_count=float(data.get("terminal_count", 0) or 0),
            lead_excess_unit_rate=float(data.get("lead_excess_unit_rate", 10) or 0),
            lead_excess_cap=float(data.get("lead_excess_cap", 1000) or 0),
            session_excess_unit_rate=float(data.get("session_excess_unit_rate", 100) or 0),
            session_excess_cap=float(data.get("session_excess_cap", 500) or 0),
            session_excess_threshold=float(data.get("session_excess_threshold", 5) or 0),
            track_session_excess=bool(data.get("track_session_excess", False)),
        )

    if template == "video_ops":
        return VideoOpsInput(
            videos=_pair_from_flat(data, "videos"),
            play_count=_pair_from_flat(data, "play_count"),
            short_video_fans=_pair_from_flat(data, "short_video_fans"),
            xiaohongshu=_pair_from_flat(data, "xiaohongshu"),
            kpi_base=float(data.get("kpi_base", 6000) or 0),
            score_weights=tuple(data.get("score_weights", (40.0, 20.0, 20.0, 20.0))),
            terminal_unit_rate=float(data.get("terminal_unit_rate", 20) or 0),
            terminal_count=float(data.get("terminal_count", 0) or 0),
            quality_video_unit_rate=float(data.get("quality_video_unit_rate", 50) or 0),
            quality_video_count=float(data.get("quality_video_count", 0) or 0),
            excess_video_unit_rate=float(data.get("excess_video_unit_rate", 50) or 0),
            excess_video_cap=float(data.get("excess_video_cap", 500) or 0),
        )

    if template == "ops_manager":
        return OpsManagerInput(
            live_sessions=_pair_from_flat(data, "live_sessions"),
            video_creations=_pair_from_flat(data, "video_creations"),
            leads=_pair_from_flat(data, "leads"),
            store_visits=_pair_from_flat(data, "store_visits"),
            kpi_base=float(data.get("kpi_base", 8000) or 0),
            score_weights=tuple(data.get("score_weights", (25.0, 25.0, 25.0, 25.0))),
            terminal_unit_rate=float(data.get("terminal_unit_rate", 40) or 0),
            terminal_count=float(data.get("terminal_count", 0) or 0),
        )

    raise ValueError(f"unknown template: {template}")


def coerce_new_media_inputs(raw: Any, template: str) -> Any:
    """保持 session 中已是正确 dataclass 的实例。"""
    expected = {
        "live_anchor": LiveAnchorInput,
        "video_ops": VideoOpsInput,
        "ops_manager": OpsManagerInput,
        "manual": ManualPerformanceInput,
    }
    cls = expected.get(template)
    if cls and isinstance(raw, cls):
        return raw
    if is_dataclass(raw) or isinstance(raw, dict):
        flat = values_from_inputs(raw) if is_dataclass(raw) else dict(raw)
        return inputs_from_values(None, flat, template)
    from salary_pipeline.calculators.new_media.registry import default_input_for_role

    return default_input_for_role({"template": template, "defaults": {}})


def applicability_matrix(family: FieldAlignmentFamily | None = None) -> pd.DataFrame:
    family = family or load_new_media_alignment()
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
    family = family or load_new_media_alignment()
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
