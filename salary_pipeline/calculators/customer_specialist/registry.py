"""客户专员岗位模板登记与统一计算入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from salary_pipeline.calculators.customer_specialist.formulas import compute_for_input
from salary_pipeline.calculators.customer_specialist.types import (
    ActivityRowInput,
    BaokeMetricRow,
    BaokeStoreInput,
    CustomerSpecialistInput,
    LeftLineItemsInput,
    LineItem,
    PerformanceResult,
)
from salary_pipeline.paths import CONFIG_DIR

_REGISTRY_PATH = CONFIG_DIR / "customer_specialist_roles.yaml"


def load_role_registry(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or _REGISTRY_PATH
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def list_roles(registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    reg = registry or load_role_registry()
    return list(reg.get("roles", []))


def get_role(name: str, registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    for role in list_roles(registry):
        if role["name"] == name:
            return role
    return None


def hub_mapping_for_role(role: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return dict(role.get("hub_mapping", {}))


def default_input_for_role(role: dict[str, Any]) -> CustomerSpecialistInput:
    template = role["template"]
    if template == "left_line_items":
        return CustomerSpecialistInput(
            template=template,
            left=LeftLineItemsInput(
                person=role.get("person_column", "zhangbaozhen"),
                fixed_vehicle_performance=float(
                    role.get("defaults", {}).get("fixed_vehicle_performance", 2000)
                ),
            ),
        )
    if template == "left_and_baoke":
        return CustomerSpecialistInput(
            template=template,
            left=LeftLineItemsInput(person="dengfang"),
            baoke=BaokeStoreInput(metrics=_default_baoke_metrics()),
        )
    if template == "activity_summary":
        return CustomerSpecialistInput(
            template=template,
            activity=ActivityRowInput(),
            baoke=BaokeStoreInput(metrics=_default_baoke_metrics()),
        )
    if template == "baoke_store":
        return CustomerSpecialistInput(
            template=template,
            baoke=BaokeStoreInput(metrics=_default_baoke_metrics()),
        )
    raise ValueError(f"unknown template: {template}")


def _default_baoke_metrics() -> list[BaokeMetricRow]:
    return [
        BaokeMetricRow(metric_type="phone_callback", label="电话回访"),
        BaokeMetricRow(metric_type="referral", label="基盘客户转介绍"),
        BaokeMetricRow(metric_type="mining", label="保客挖掘置换/增购"),
        BaokeMetricRow(metric_type="all_staff", label="全员营销"),
    ]


def compute_for_role(role_name: str, inputs: CustomerSpecialistInput) -> PerformanceResult:
    role = get_role(role_name)
    if role is None:
        raise KeyError(f"role not found: {role_name}")
    result = compute_for_input(inputs)
    # 张保珍固定整车绩效写入 hub
    if role.get("person_column") == "zhangbaozhen":
        fixed = float(role.get("defaults", {}).get("fixed_vehicle_performance", 0))
        if fixed:
            result.hub_metrics["整车绩效"] = fixed
    return result


def lookup_role_hub_metrics(loader: Any, role_name: str) -> dict[str, float]:
    """从金标准子表读取各 hub 列应对值。"""
    from salary_pipeline.calculators.customer_specialist.extract import lookup_golden_cells

    return lookup_golden_cells(loader, role_name)
