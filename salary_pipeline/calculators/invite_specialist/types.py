"""邀约专员算薪：输入/输出数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InviteDccInput:
    """西物 / 超市共用细化输入（子表列语义按版式在 UI 中区分展示）。"""

    # DMS 七项：每项达成 100 元，七项均达成追加 100 元（提成依据 §2）
    dms_achieved_count: float = 6.0
    dms_per_item_reward: float = 100.0
    dms_all_seven_achieved: bool = False
    dms_all_seven_bonus: float = 100.0
    # 邀约到店基础：组数 K × 单价 J（60 元/组）
    invite_groups: float = 0.0
    invite_unit_rate: float = 60.0
    # 邀约到店率≥15% 追加：元/组 × 组数（西物 S×K；超市同规则可选填）
    invite_rate_bonus_per_group: float = 0.0
    # 成交基础：台次 N × 单价 M（40 元/台）
    deal_count: float = 0.0
    deal_unit_rate: float = 40.0
    # 成交率阶梯追加：台次 × 单台追加（20/30 元）
    deal_rate_bonus_per_unit: float = 0.0
    # 超市：达成邀约量 P × 单组到店追加 Q
    achieved_invite_volume: float = 0.0
    per_group_store_bonus: float = 100.0
    # 西物：重攻车型 基数 × 系数
    heavy_attack_bonus: float = 0.0
    heavy_attack_multiplier: float = 0.0
    # 西物：任务考核调整 AC（可负）
    task_adjustment: float = 0.0
    # 超市：任务考核扣减 X
    task_penalty: float = 0.0
    # 崇州：400 接起率考核 F（未接起扣 500 等）
    call_answer_penalty: float = 0.0


WuhouDccInput = InviteDccInput
ChaoshiDccInput = InviteDccInput
AirportDccInput = InviteDccInput


@dataclass
class PerformanceBreakdown:
    six_dimension: float = 0.0
    invite_groups: float = 0.0
    deal_commission: float = 0.0
    invite_rate_bonus: float = 0.0
    deal_rate_bonus: float = 0.0
    heavy_attack: float = 0.0
    process_kpi: float = 0.0
    task_adjustment: float = 0.0
    six_dimension_bonus: float = 0.0
    task_penalty: float = 0.0
    call_answer_penalty: float = 0.0

    def to_dict(self) -> dict[str, float]:
        labels = {
            "six_dimension": "DMS指标得分",
            "six_dimension_bonus": "七项均达成追加",
            "invite_groups": "邀约到店绩效",
            "invite_rate_bonus": "邀约到店率追加",
            "deal_commission": "成交台次绩效",
            "deal_rate_bonus": "成交率追加",
            "process_kpi": "达成邀约奖励",
            "heavy_attack": "重攻车型奖励",
            "task_adjustment": "任务考核调整",
            "task_penalty": "任务考核扣减",
            "call_answer_penalty": "400接起率考核",
        }
        return {labels[k]: v for k, v in self.__dict__.items() if v}


@dataclass
class PerformanceResult:
    template: str
    performance_salary: float
    hub_vehicle_performance: float
    breakdown: PerformanceBreakdown
    metadata: dict[str, Any] = field(default_factory=dict)
