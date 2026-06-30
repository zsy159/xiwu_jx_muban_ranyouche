"""Stub modules — replace with real implementations per iteration."""

from __future__ import annotations

from typing import Any

import pandas as pd

from salary_pipeline.modules.base import BaseCommissionModule, ModuleResult


class SalesVehicleModule(BaseCommissionModule):
    """整车毛利 / 销量 — 待按拓扑实现。"""

    name = "sales_vehicle"
    roles = ["销售顾问", "销售主管", "内勤"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        # 迭代 1+ 接入 终端明细表 + 整车成本 + 销售任务及完成率
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=pd.DataFrame(columns=["店别", "职务", "姓名"]),
            metadata={"status": "not_implemented"},
        )


class SalesAddonModule(BaseCommissionModule):
    """加装 / 精品 — 待实现。"""

    name = "sales_addon"
    roles = ["销售顾问"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=pd.DataFrame(columns=["店别", "职务", "姓名"]),
            metadata={"status": "not_implemented"},
        )


class SalesFinanceModule(BaseCommissionModule):
    """按揭 / 保险 / 金融 — 待实现。"""

    name = "sales_finance"
    roles = ["销售顾问"]

    def run(self, context: dict[str, Any]) -> ModuleResult:
        return ModuleResult(
            module_name=self.name,
            roles=self.roles,
            metrics=pd.DataFrame(columns=["店别", "职务", "姓名"]),
            metadata={"status": "not_implemented"},
        )


def register_default_modules(registry) -> None:
    registry.register(SalesVehicleModule())
    registry.register(SalesAddonModule())
    registry.register(SalesFinanceModule())
