"""直营店经理岗位模板登记。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.calculators.direct_store_manager.formulas import (
    compute_store_blocks,
)
from salary_pipeline.calculators.direct_store_manager.types import (
    PerformanceResult,
    StoreBlockInput,
)
from salary_pipeline.paths import CONFIG_DIR

_REGISTRY_PATH = CONFIG_DIR / "direct_store_manager_roles.yaml"
HUB_COLUMN = "整车完成考核"


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


def hub_column_for_role(role: dict[str, Any]) -> str:
    return str(role.get("hub_column") or HUB_COLUMN)


def default_input_for_role(role: dict[str, Any]) -> list[StoreBlockInput]:
    blocks = role.get("excel_blocks") or [{"row": 3}]
    return [
        StoreBlockInput(store_label=str(role.get("store", "")))
        for _ in blocks
    ]


def compute_for_role(
    role_name: str, inputs: list[StoreBlockInput]
) -> PerformanceResult:
    role = get_role(role_name)
    if role is None:
        raise KeyError(role_name)
    return compute_store_blocks(inputs, template=str(role.get("template", "store_block")))
