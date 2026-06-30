"""邀约专员岗位模板登记。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.calculators.invite_specialist.formulas import (
    compute_chaoshi_dcc,
    compute_chongzhou_invite,
    compute_wuhou_dcc,
)
from salary_pipeline.calculators.invite_specialist.types import (
    InviteDccInput,
    PerformanceResult,
)
from salary_pipeline.paths import CONFIG_DIR

_REGISTRY_PATH = CONFIG_DIR / "invite_specialist_roles.yaml"


def load_role_registry(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or _REGISTRY_PATH
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def list_roles(registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return list((registry or load_role_registry()).get("roles", []))


def get_role(name: str, registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    for role in list_roles(registry):
        if role["name"] == name:
            return role
    return None


def _is_xiwu_template(template: str) -> bool:
    return template in ("xiwu_dcc", "wuhou_dcc")


def _is_chaoshi_template(template: str) -> bool:
    return template in ("chaoshi_dcc", "airport_dcc")


def _is_chongzhou_template(template: str) -> bool:
    return template == "chongzhou_invite"


def hub_column_for_role(role: dict[str, Any]) -> str:
    return str(role.get("hub_column") or "整车绩效")


def default_input_for_role(role: dict[str, Any]) -> Any:
    template = role["template"]
    defaults = role.get("defaults", {})
    if _is_xiwu_template(template):
        return InviteDccInput(
            invite_unit_rate=float(defaults.get("invite_unit_rate", 60)),
            deal_unit_rate=float(defaults.get("deal_unit_rate", 40)),
            deal_rate_bonus_per_unit=float(defaults.get("deal_rate_bonus_per_unit", 20)),
        )
    if _is_chaoshi_template(template):
        return InviteDccInput(
            invite_unit_rate=float(defaults.get("invite_unit_rate", 60)),
            deal_unit_rate=float(defaults.get("deal_unit_rate", 40)),
            per_group_store_bonus=float(defaults.get("per_group_store_bonus", 100)),
        )
    if _is_chongzhou_template(template):
        return InviteDccInput(
            invite_unit_rate=float(defaults.get("invite_unit_rate", 60)),
            deal_unit_rate=float(defaults.get("deal_unit_rate", 35)),
            deal_rate_bonus_per_unit=float(defaults.get("deal_rate_bonus_per_unit", 20)),
        )
    raise ValueError(f"unknown template: {template}")


def compute_for_role(role_name: str, inputs: Any) -> PerformanceResult:
    role = get_role(role_name)
    if role is None:
        raise KeyError(role_name)
    template = role["template"]
    if _is_xiwu_template(template):
        assert isinstance(inputs, InviteDccInput)
        return compute_wuhou_dcc(inputs)
    if _is_chaoshi_template(template):
        assert isinstance(inputs, InviteDccInput)
        return compute_chaoshi_dcc(inputs)
    if _is_chongzhou_template(template):
        assert isinstance(inputs, InviteDccInput)
        return compute_chongzhou_invite(inputs)
    raise ValueError(f"unknown template: {template}")


def inputs_to_dict(inputs: Any) -> dict[str, Any]:
    return asdict(inputs)
