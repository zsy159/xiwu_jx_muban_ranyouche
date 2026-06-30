"""客户专员字段拉通 — 必做 / 机动 / 增值 分组对照。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from salary_pipeline.calculators.customer_specialist.baoke_metric_catalog import (
    BAOKE_METRIC_SPECS,
    BAOKE_TEMPLATES,
    BaokeMetricSpec,
)
from salary_pipeline.calculators.customer_specialist.line_item_catalog import (
    ALL_LINE_ITEMS,
    LEFT_LINE_TEMPLATES,
    LINE_ITEM_SECTIONS,
    LineItemSpec,
)
from salary_pipeline.calculators.customer_specialist.types import (
    ActivityRowInput,
    BaokeMetricRow,
    BaokeStoreInput,
    CustomerSpecialistInput,
    LeftLineItemsInput,
    LineItem,
)
from salary_pipeline.calculators.field_alignment.schema import (
    FieldAlignmentFamily,
    FieldDef,
    FieldSection,
    iter_fields,
    load_alignment_family,
)

_FAMILY_ID = "customer_specialist"
_LEFT_APPLICABLE = list(LEFT_LINE_TEMPLATES)


def _line_attr(spec_id: str) -> str:
    return f"line_{spec_id}"


def _line_field_def(spec: LineItemSpec) -> FieldDef:
    return FieldDef(
        id=f"{spec.category}_{spec.id}",
        label=spec.label,
        input_attr=_line_attr(spec.id),
        value_type="line_item",
        applicable=_LEFT_APPLICABLE,
        excel_col={
            "row": spec.excel_row,
            "achievement_rate": "C",
            "coefficient": "D",
            "qty_dengfang": "E",
            "subtotal_dengfang": "F",
            "qty_zhangbaozhen": "G",
            "subtotal_zhangbaozhen": "H",
        },
    )


def _build_line_item_sections() -> list[FieldSection]:
    sections: list[FieldSection] = []
    for block in LINE_ITEM_SECTIONS:
        fields = [_line_field_def(spec) for spec in block.items]
        if block.id == "bizuo":
            fields.append(
                FieldDef(
                    id="fixed_vehicle_performance",
                    label="整车绩效固定额（Hub W）",
                    input_attr="fixed_vehicle_performance",
                    value_type="number",
                    applicable=["left_line_items"],
                    default=2000,
                )
            )
        sections.append(
            FieldSection(
                id=block.id,
                label=block.label,
                fields=fields,
                section_note=f"子表 A–H 列 · {block.label}类行项（C 达成率 · D 系数 · E/G 数量 · F/H 小计）",
            )
        )
    return sections


def _baoke_attr(spec_id: str, field: str) -> str:
    return f"baoke_{spec_id}_{field}"


def _baoke_field_defs(spec: BaokeMetricSpec) -> list[FieldDef]:
    fields = [
        FieldDef(
            id=f"baoke_{spec.id}_baseline",
            label=f"{spec.label} · 1-3月基线",
            input_attr=_baoke_attr(spec.id, "baseline_rate"),
            value_type="baoke_metric",
            applicable=list(BAOKE_TEMPLATES),
            excel_col="AO",
        ),
        FieldDef(
            id=f"baoke_{spec.id}_actual",
            label=f"{spec.label} · 5月实际",
            input_attr=_baoke_attr(spec.id, "actual_rate"),
            value_type="baoke_metric",
            applicable=list(BAOKE_TEMPLATES),
            excel_col="AP",
        ),
        FieldDef(
            id=f"baoke_{spec.id}_improvement",
            label=f"{spec.label} · 达成提升(%)",
            input_attr=_baoke_attr(spec.id, "improvement_pct"),
            value_type="baoke_metric",
            applicable=list(BAOKE_TEMPLATES),
            excel_col="AQ",
        ),
        FieldDef(
            id=f"baoke_{spec.id}_delivery",
            label=f"{spec.label} · 台次",
            input_attr=_baoke_attr(spec.id, "delivery_count"),
            value_type="baoke_metric",
            applicable=list(BAOKE_TEMPLATES),
            excel_col="AR",
        ),
    ]
    if spec.metric_type == "phone_callback":
        fields.append(
            FieldDef(
                id=f"baoke_{spec.id}_flat",
                label=f"{spec.label} · 固定金额",
                input_attr=_baoke_attr(spec.id, "flat_amount"),
                value_type="baoke_metric",
                applicable=list(BAOKE_TEMPLATES),
                excel_col="AT",
            )
        )
    return fields


def _build_baoke_section() -> FieldSection:
    fields: list[FieldDef] = []
    for spec in BAOKE_METRIC_SPECS:
        fields.extend(_baoke_field_defs(spec))
    return FieldSection(
        id="baoke_block",
        label="保客营销",
        fields=fields,
        section_note="子表 AN–AT · 四行指标 + 绩效合计（AT 合计写入 hub 权限结余/子表合计）",
    )


def _build_activity_section() -> FieldSection:
    return FieldSection(
        id="activity_row",
        label="活动合计行",
        section_note="周舟 K–AB 行 · 数量列输入，P/R/T/V/X 等为公式小计",
        fields=[
            FieldDef(
                id="prospect_callbacks",
                label="潜客回访",
                input_attr="prospect_callbacks",
                applicable=["activity_summary"],
                excel_col="L",
            ),
            FieldDef(
                id="five_day_callbacks",
                label="5天新车回访",
                input_attr="five_day_callbacks",
                applicable=["activity_summary"],
                excel_col="M",
            ),
            FieldDef(
                id="thirty_day_callbacks",
                label="30天新车回访",
                input_attr="thirty_day_callbacks",
                applicable=["activity_summary"],
                excel_col="N",
            ),
            FieldDef(
                id="defeat_callbacks",
                label="潜客战败回访",
                input_attr="defeat_callbacks",
                applicable=["activity_summary"],
                excel_col="O",
            ),
            FieldDef(
                id="visit_count",
                label="面访量",
                input_attr="visit_count",
                applicable=["activity_summary"],
                excel_col="Q",
            ),
            FieldDef(
                id="group_chat_count",
                label="群聊建立量",
                input_attr="group_chat_count",
                applicable=["activity_summary"],
                excel_col="S",
            ),
            FieldDef(
                id="birthday_count",
                label="生日关怀接通量",
                input_attr="birthday_count",
                applicable=["activity_summary"],
                excel_col="U",
            ),
            FieldDef(
                id="reputation_posts",
                label="口碑/发帖量",
                input_attr="reputation_posts",
                applicable=["activity_summary"],
                excel_col="W",
            ),
            FieldDef(
                id="complaint_handling",
                label="投诉处理",
                input_attr="complaint_handling",
                applicable=["activity_summary"],
                excel_col="Y",
            ),
            FieldDef(
                id="satisfaction_score",
                label="销售满意度得分",
                input_attr="satisfaction_score",
                applicable=["activity_summary"],
                excel_col="Z",
            ),
            FieldDef(
                id="satisfaction_bonus",
                label="销售满意度绩效",
                input_attr="satisfaction_bonus",
                applicable=["activity_summary"],
                excel_col="AA",
            ),
            FieldDef(
                id="baoke_marketing_flat",
                label="保客营销（活动行）",
                input_attr="baoke_marketing_flat",
                applicable=["activity_summary"],
                excel_col="AB",
            ),
        ],
    )


def enrich_customer_alignment(family: FieldAlignmentFamily) -> FieldAlignmentFamily:
    """将 YAML 占位替换为必做/机动/增值行项 + 活动行 + 保客营销明细。"""
    tail: list[FieldSection] = []
    for section in family.sections:
        if section.id in ("left_block", "activity_row", "baoke_block"):
            continue
        tail.append(section)
    return FieldAlignmentFamily(
        family_id=family.family_id,
        family_label=family.family_label,
        rules_sheet=family.rules_sheet,
        templates=family.templates,
        sections=[
            *_build_line_item_sections(),
            _build_activity_section(),
            _build_baoke_section(),
            *tail,
        ],
    )


def load_customer_alignment() -> FieldAlignmentFamily:
    return enrich_customer_alignment(load_alignment_family(_FAMILY_ID))


def is_field_applicable(field: FieldDef, template: str) -> bool:
    return template in field.applicable


def not_applicable_reason(field: FieldDef, template: str) -> str:
    return field.not_applicable_note.get(template, "当前版式子表无此列")


def field_label_for_template(field: FieldDef, template: str) -> str:
    return field.label_by_template.get(template, field.label)


def _find_line_item(items: list[LineItem], label: str) -> LineItem | None:
    for item in items:
        if item.item_name == label:
            return item
    return None


def _find_baoke_metric(
    metrics: list[BaokeMetricRow], spec: BaokeMetricSpec
) -> BaokeMetricRow | None:
    for row in metrics:
        if row.metric_type == spec.metric_type or row.label == spec.label:
            return row
    return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def values_from_inputs(inputs: CustomerSpecialistInput) -> dict[str, Any]:
    out: dict[str, Any] = {"template": getattr(inputs, "template", "")}
    if inputs.left:
        out["left_person"] = inputs.left.person
        for spec in ALL_LINE_ITEMS:
            prefix = _line_attr(spec.id)
            item = _find_line_item(inputs.left.line_items, spec.label)
            out[f"{prefix}_achievement_rate"] = (
                item.achievement_rate if item else None
            )
            out[f"{prefix}_coefficient"] = float(item.coefficient or 0) if item else 0.0
            out[f"{prefix}_qty_dengfang"] = float(item.qty_dengfang or 0) if item else 0.0
            out[f"{prefix}_qty_zhangbaozhen"] = (
                float(item.qty_zhangbaozhen or 0) if item else 0.0
            )
        out["fixed_vehicle_performance"] = float(inputs.left.fixed_vehicle_performance or 0)
    if inputs.activity:
        act = inputs.activity
        out.update(
            {
                "prospect_callbacks": act.prospect_callbacks,
                "five_day_callbacks": act.five_day_callbacks,
                "thirty_day_callbacks": act.thirty_day_callbacks,
                "defeat_callbacks": act.defeat_callbacks,
                "visit_count": act.visit_count,
                "group_chat_count": act.group_chat_count,
                "birthday_count": act.birthday_count,
                "reputation_posts": act.reputation_posts,
                "complaint_handling": act.complaint_handling,
                "satisfaction_score": act.satisfaction_score,
                "satisfaction_bonus": act.satisfaction_bonus,
                "baoke_marketing_flat": act.baoke_marketing_flat,
            }
        )
    if inputs.baoke:
        for spec in BAOKE_METRIC_SPECS:
            row = _find_baoke_metric(inputs.baoke.metrics, spec)
            prefix = f"baoke_{spec.id}"
            out[f"{prefix}_baseline_rate"] = row.baseline_rate if row else None
            out[f"{prefix}_actual_rate"] = row.actual_rate if row else None
            out[f"{prefix}_improvement_pct"] = row.improvement_pct if row else None
            out[f"{prefix}_delivery_count"] = float(row.delivery_count or 0) if row else 0.0
            out[f"{prefix}_flat_amount"] = float(row.flat_amount or 0) if row else 0.0
    return out


def _line_items_from_values(
    base_items: list[LineItem],
    updates: dict[str, Any],
) -> list[LineItem]:
    items: list[LineItem] = []
    for spec in ALL_LINE_ITEMS:
        prefix = _line_attr(spec.id)
        base_item = _find_line_item(base_items, spec.label)
        ar_key = f"{prefix}_achievement_rate"
        if ar_key in updates:
            achievement_rate = _optional_float(updates[ar_key])
        else:
            achievement_rate = base_item.achievement_rate if base_item else None

        coefficient = float(
            updates.get(
                f"{prefix}_coefficient",
                base_item.coefficient if base_item else 0,
            )
            or 0
        )
        qty_d = float(
            updates.get(
                f"{prefix}_qty_dengfang",
                base_item.qty_dengfang if base_item else 0,
            )
            or 0
        )
        qty_z = float(
            updates.get(
                f"{prefix}_qty_zhangbaozhen",
                base_item.qty_zhangbaozhen if base_item else 0,
            )
            or 0
        )
        items.append(
            LineItem(
                category=spec.category,
                item_name=spec.label,
                achievement_rate=achievement_rate,
                coefficient=coefficient,
                qty_dengfang=qty_d,
                qty_zhangbaozhen=qty_z,
            )
        )
    return items


def _baoke_from_values(
    base: BaokeStoreInput,
    updates: dict[str, Any],
) -> BaokeStoreInput:
    metrics: list[BaokeMetricRow] = []
    for spec in BAOKE_METRIC_SPECS:
        base_row = _find_baoke_metric(base.metrics, spec)
        prefix = f"baoke_{spec.id}"

        def _pick(field: str, default: Any = None) -> Any:
            key = f"{prefix}_{field}"
            if key in updates:
                return updates[key]
            return getattr(base_row, field, default) if base_row else default

        metrics.append(
            BaokeMetricRow(
                metric_type=spec.metric_type,
                label=spec.label,
                baseline_rate=_optional_float(_pick("baseline_rate")),
                actual_rate=_optional_float(_pick("actual_rate")),
                improvement_pct=_optional_float(_pick("improvement_pct")),
                delivery_count=float(_pick("delivery_count", 0) or 0),
                flat_amount=float(_pick("flat_amount", 0) or 0),
            )
        )
    return BaokeStoreInput(store_label=base.store_label, metrics=metrics)


def inputs_from_values(
    base: CustomerSpecialistInput | None,
    updates: dict[str, Any],
    template: str = "",
) -> CustomerSpecialistInput:
    base = base or CustomerSpecialistInput(template=template or "left_and_baoke")
    tpl = template or base.template

    left = base.left
    activity = base.activity
    baoke = base.baoke

    if tpl in _LEFT_APPLICABLE and base.left:
        fixed = float(
            updates.get(
                "fixed_vehicle_performance",
                base.left.fixed_vehicle_performance,
            )
            or 0
        )
        left = LeftLineItemsInput(
            person=str(updates.get("left_person", base.left.person)),
            line_items=_line_items_from_values(base.left.line_items, updates),
            fixed_vehicle_performance=fixed,
        )

    if tpl == "activity_summary" and base.activity:
        act = base.activity
        activity = ActivityRowInput(
            prospect_callbacks=float(updates.get("prospect_callbacks", act.prospect_callbacks) or 0),
            five_day_callbacks=float(updates.get("five_day_callbacks", act.five_day_callbacks) or 0),
            thirty_day_callbacks=float(
                updates.get("thirty_day_callbacks", act.thirty_day_callbacks) or 0
            ),
            defeat_callbacks=float(updates.get("defeat_callbacks", act.defeat_callbacks) or 0),
            visit_count=float(updates.get("visit_count", act.visit_count) or 0),
            group_chat_count=float(updates.get("group_chat_count", act.group_chat_count) or 0),
            birthday_count=float(updates.get("birthday_count", act.birthday_count) or 0),
            reputation_posts=float(updates.get("reputation_posts", act.reputation_posts) or 0),
            complaint_handling=float(updates.get("complaint_handling", act.complaint_handling) or 0),
            satisfaction_score=float(updates.get("satisfaction_score", act.satisfaction_score) or 0),
            satisfaction_bonus=float(updates.get("satisfaction_bonus", act.satisfaction_bonus) or 0),
            baoke_marketing_flat=float(
                updates.get("baoke_marketing_flat", act.baoke_marketing_flat) or 0
            ),
        )

    if tpl in BAOKE_TEMPLATES and base.baoke:
        baoke = _baoke_from_values(base.baoke, updates)

    return CustomerSpecialistInput(
        template=tpl,
        left=left,
        activity=activity,
        baoke=baoke,
    )


def coerce_customer_inputs(raw: Any, template: str) -> CustomerSpecialistInput:
    from salary_pipeline.calculators.customer_specialist.registry import (
        default_input_for_role,
    )

    if isinstance(raw, CustomerSpecialistInput):
        return raw
    return default_input_for_role({"template": template})


def applicability_matrix_wide(
    family: FieldAlignmentFamily | None = None,
) -> pd.DataFrame:
    family = family or load_customer_alignment()
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
