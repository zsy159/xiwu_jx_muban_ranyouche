"""将旧版 session / JSON 输入迁移为 InviteDccInput。"""

from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from typing import Any

from salary_pipeline.calculators.invite_specialist.types import InviteDccInput


def _field_names() -> set[str]:
    return {f.name for f in fields(InviteDccInput)}


def coerce_invite_inputs(raw: Any) -> InviteDccInput:
    """兼容旧 session 中的 WuhouDccInput / ChaoshiDccInput 实例。"""
    if isinstance(raw, InviteDccInput) and hasattr(raw, "dms_achieved_count"):
        return raw

    data: dict[str, Any] = asdict(raw) if is_dataclass(raw) else dict(raw)
    if "dms_achieved_count" in data:
        return InviteDccInput(**{k: data[k] for k in _field_names() if k in data})

    migrated: dict[str, Any] = {}

    if "six_dimension_score" in data:
        score = float(data.get("six_dimension_score", 600))
        unit = float(data.get("dms_per_item_reward", 100))
        migrated["dms_achieved_count"] = score / unit if unit else score
        bonus = float(data.get("six_dimension_bonus", 0))
        migrated["dms_all_seven_achieved"] = bonus >= 100

    for key in (
        "invite_groups",
        "invite_unit_rate",
        "invite_rate_bonus_per_group",
        "deal_count",
        "deal_unit_rate",
        "deal_rate_bonus_per_unit",
        "achieved_invite_volume",
        "per_group_store_bonus",
        "heavy_attack_bonus",
        "heavy_attack_multiplier",
        "task_adjustment",
        "task_penalty",
        "call_answer_penalty",
        "dms_per_item_reward",
        "dms_all_seven_bonus",
    ):
        if key in data:
            migrated[key] = data[key]

    if "invite_store_visits" in data and "invite_groups" not in migrated:
        migrated["invite_groups"] = data["invite_store_visits"]

    if "deal_bonus_per_unit" in data and "deal_rate_bonus_per_unit" not in migrated:
        migrated["deal_rate_bonus_per_unit"] = data["deal_bonus_per_unit"]

    return InviteDccInput(**{k: migrated[k] for k in _field_names() if k in migrated})
