"""Load 客户部提成子表 — 按岗位读取 hub 对应单元格。"""

from __future__ import annotations

from typing import Any

from salary_pipeline.calculators.customer_specialist.registry import (
    get_role,
    list_roles,
    lookup_role_hub_metrics,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name

SHEET = "客户部提成"
STORE_MATCH = "客户关系部"


def lookup_hub_metrics(loader: WorkbookLoader, name: str) -> dict[str, float]:
    role = get_role(name)
    if role is None:
        return {}
    return lookup_role_hub_metrics(loader, name)


def hub_linked_names() -> list[str]:
    return [
        r["name"]
        for r in list_roles()
        if r.get("hub_mapping") and r.get("hub_linked", True)
    ]


def match_customer_row(row: Any) -> bool:
    store = normalize_name(str(row.get("店别", "")))
    return store == normalize_name(STORE_MATCH)
