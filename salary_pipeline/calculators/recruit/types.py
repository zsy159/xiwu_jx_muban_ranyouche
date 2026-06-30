"""招聘岗位族算薪：输入/输出数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecruitTeamInput:
    """招聘子表团队分配块中某一负责人的输入。"""

    name: str
    onboard_count: float
    commission_per_hire: float
    total_commission: float
    allocation_ratio: float
    sheet_amount: float | None = None
    source_row: int | None = None


@dataclass
class RecruitPerformanceResult:
    name: str
    insurance_performance: float
    team: RecruitTeamInput
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def hub_insurance_performance(self) -> float:
        return self.insurance_performance

    @property
    def hub_vehicle_performance(self) -> float:
        """字段拉通页与其它岗位族共用预览属性名。"""
        return self.insurance_performance

    @property
    def performance_salary(self) -> float:
        return self.insurance_performance

    @property
    def breakdown(self) -> dict[str, float]:
        t = self.team
        base = t.onboard_count * t.commission_per_hire
        return {
            "到岗数": t.onboard_count,
            "单人招聘提成": t.commission_per_hire,
            "团队提成合计": t.total_commission,
            "分配比例": t.allocation_ratio,
            "基础池(到岗×提成)": base,
            "个人提成": self.insurance_performance,
        }
