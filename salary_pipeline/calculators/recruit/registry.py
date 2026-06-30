"""招聘岗位族模板登记。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.calculators.recruit.formulas import compute_recruit_performance
from salary_pipeline.calculators.recruit.types import (
    RecruitPerformanceResult,
    RecruitTeamInput,
)
from salary_pipeline.paths import CONFIG_DIR

_REGISTRY_PATH = CONFIG_DIR / "recruit_roles.yaml"
HUB_COLUMN = "保险绩效"

_DEFAULT_TEAM_COLS = {
    "name": "Q",
    "onboard_count": "S",
    "commission_per_hire": "T",
    "total_commission": "U",
    "allocation_ratio": "V",
    "amount": "W",
}


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


def get_team_block_config(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    reg = registry or load_role_registry()
    block = dict(reg.get("team_block", {}))
    cols = dict(_DEFAULT_TEAM_COLS)
    for logical in _DEFAULT_TEAM_COLS:
        yaml_key = f"{logical}_col"
        if yaml_key in block:
            cols[logical] = str(block[yaml_key])
    return {
        "sheet": str(block.get("sheet", "招聘")),
        "cols": cols,
    }


def hub_column_for_role(role: dict[str, Any]) -> str:
    return str(role.get("hub_column") or HUB_COLUMN)


def is_hub_linked(role: dict[str, Any]) -> bool:
    if role.get("hub_linked") is False:
        return False
    return bool(role.get("hub_excel_row") or role.get("hub_mapping"))


def hub_linked_names(registry: dict[str, Any] | None = None) -> list[str]:
    return [r["name"] for r in list_roles(registry) if is_hub_linked(r)]


def default_input_for_role(role: dict[str, Any]) -> RecruitTeamInput:
    return RecruitTeamInput(
        name=str(role.get("name", "")),
        onboard_count=0.0,
        commission_per_hire=0.0,
        total_commission=0.0,
        allocation_ratio=0.0,
    )


def compute_for_role(
    name: str, team: RecruitTeamInput
) -> RecruitPerformanceResult:
    role = get_role(name)
    if role is None:
        raise KeyError(name)
    return compute_recruit_performance(
        name, team, template=str(role.get("template", "team_allocation"))
    )
