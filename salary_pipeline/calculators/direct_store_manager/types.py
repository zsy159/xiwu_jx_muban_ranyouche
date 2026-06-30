"""直营店经理算薪：输入/输出数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StoreBlockInput:
    """子表门店块（行 3–8）输入。"""

    store_label: str = ""
    showroom_task: float = 0.0
    showroom_actual: float = 0.0
    showroom_ev_actual: float = 0.0
    showroom_rate: float = 100.0
    channel_task: float = 0.0
    channel_actual: float = 0.0
    channel_ev_task: float = 0.0
    channel_rate: float = 50.0
    attach_commission: float = 0.0
    fixed_performance: float = 2500.0
    extra_vehicle_commission: float = 0.0


@dataclass
class PerformanceBreakdown:
    showroom_commission: float = 0.0
    channel_commission: float = 0.0
    unit_commission_total: float = 0.0
    attach_commission: float = 0.0
    fixed_performance: float = 0.0
    extra_vehicle_commission: float = 0.0

    def to_dict(self) -> dict[str, float]:
        labels = {
            "showroom_commission": "展厅单台提成",
            "channel_commission": "渠道单台提成",
            "unit_commission_total": "台次提成合计",
            "attach_commission": "附加收入提成",
            "fixed_performance": "固定绩效",
            "extra_vehicle_commission": "指定车型考核提成",
        }
        return {labels[k]: v for k, v in self.__dict__.items() if v}


@dataclass
class PerformanceResult:
    template: str
    performance_salary: float
    hub_vehicle_performance: float
    breakdown: PerformanceBreakdown
    blocks: list[StoreBlockInput] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
