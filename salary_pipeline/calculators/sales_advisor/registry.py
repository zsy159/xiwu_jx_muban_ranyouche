"""销售顾问岗位族登记与 hub_linked 策略。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.paths import CONFIG_DIR

_REGISTRY_PATH = CONFIG_DIR / "sales_advisor_roles.yaml"
DEFAULT_TITLE = "销售顾问"
HUB_COLUMNS = (
    "整车绩效",
    "权限结余绩效",
    "加装绩效",
    "保险绩效",
    "金融绩效",
    "爱车宝绩效",
    "上户绩效",
    "盈利产品绩效",
    "延保提成",
    "特殊车型+指定车型",
    "座位险提成",
    "二手车提成",
    "玻碎险提成",
)


def load_role_registry(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or _REGISTRY_PATH
    if not cfg_path.exists():
        return {"roles": [], "hub_linked_policy": {}}
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def list_roles(registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return list((registry or load_role_registry()).get("roles", []))


def get_role(name: str, registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    for role in list_roles(registry):
        if role["name"] == name:
            return role
    return None


def is_hub_linked(role: dict[str, Any] | None) -> bool:
    if role is None:
        return False
    if role.get("hub_linked") is False:
        return False
    return bool(role.get("hub_linked", True))


def hub_linked_names(registry: dict[str, Any] | None = None) -> list[str]:
    return [r["name"] for r in list_roles(registry) if is_hub_linked(r)]


def subsheet_only_names(registry: dict[str, Any] | None = None) -> list[str]:
    return [r["name"] for r in list_roles(registry) if not is_hub_linked(r)]


def hub_columns_for_gate(registry: dict[str, Any] | None = None) -> tuple[str, ...]:
    reg = registry or load_role_registry()
    cols = reg.get("hub_columns")
    if cols:
        return tuple(cols)
    return HUB_COLUMNS[:6]


def wa_parity_deferred_cells(
    registry: dict[str, Any] | None = None,
) -> dict[str, frozenset[str]]:
    """销售顾问 W–A 五列对账：{(姓名, 列名)} 手工暂缓集合。"""
    reg = registry or load_role_registry()
    out: dict[str, set[str]] = {}
    for entry in reg.get("wa_parity_deferred") or []:
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        cols = entry.get("columns") or {}
        out.setdefault(name, set()).update(str(c) for c in cols)
    return {name: frozenset(cols) for name, cols in out.items()}


def is_wa_parity_deferred(
    name: str,
    column: str,
    registry: dict[str, Any] | None = None,
) -> bool:
    deferred = wa_parity_deferred_cells(registry)
    return column in deferred.get(str(name).strip(), frozenset())


def is_parity_deferred_cell(
    name: str,
    column: str,
    deferred_cells: dict[str, frozenset[str]],
) -> bool:
    return column in deferred_cells.get(str(name).strip(), frozenset())


def merge_sales_advisor_deferred_cells(
    *,
    wa_deferred: dict[str, frozenset[str]] | None = None,
    erwang_deferred: dict[str, frozenset[str]] | None = None,
    manual_formula_cells: dict[tuple[str, str], frozenset[str]] | None = None,
    role_title: str = DEFAULT_TITLE,
) -> dict[str, frozenset[str]]:
    """Merge YAML / 二网 / topology manual-formula cells for reconcile highlight."""
    merged: dict[str, set[str]] = {
        name: set(cols) for name, cols in (wa_deferred or {}).items()
    }
    for name, cols in (erwang_deferred or {}).items():
        merged.setdefault(name, set()).update(cols)
    for (name, role), cols in (manual_formula_cells or {}).items():
        if role == role_title:
            merged.setdefault(name, set()).update(cols)
    return {name: frozenset(cols) for name, cols in merged.items()}


def build_reconcile_deferred_cells(
    golden_workbook: Path,
    *,
    perf_path: Path | None = None,
    header_row: int = 2,
    data_start_row: int = 3,
    role_title: str = DEFAULT_TITLE,
) -> dict[str, frozenset[str]]:
    """Merged deferred map: YAML + 二网 AH + topology manual-formula cells."""
    from salary_pipeline.calculators.sales_advisor.topology_specs import (
        collect_topology_manual_formula_cells,
    )
    from salary_pipeline.validation.golden_perf_skips import (
        erwang_blank_ah_adjustments_for_paths,
        erwang_blank_ah_deferred_cells,
    )

    manual = collect_topology_manual_formula_cells(
        golden_workbook_path=golden_workbook,
        header_row=header_row,
        data_start_row=data_start_row,
    )
    erwang_deferred: dict[str, frozenset[str]] = {}
    if perf_path is not None and perf_path.exists():
        erwang_deferred = erwang_blank_ah_deferred_cells(
            erwang_blank_ah_adjustments_for_paths(golden_workbook, perf_path)
        )
    return merge_sales_advisor_deferred_cells(
        wa_deferred=wa_parity_deferred_cells(),
        erwang_deferred=erwang_deferred,
        manual_formula_cells=manual,
        role_title=role_title,
    )
