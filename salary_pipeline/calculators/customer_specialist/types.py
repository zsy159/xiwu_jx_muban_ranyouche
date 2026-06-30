"""客户专员算薪：输入/输出数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LineItem:
    """左侧共用行项（A–H）。"""

    category: str = ""
    item_name: str = ""
    achievement_rate: float | None = None
    coefficient: float = 0.0
    qty_dengfang: float = 0.0
    qty_zhangbaozhen: float = 0.0


@dataclass
class LeftLineItemsInput:
    """邓芳 / 张保珍 — 左侧行项矩阵。"""

    person: str  # dengfang | zhangbaozhen
    line_items: list[LineItem] = field(default_factory=list)
    fixed_vehicle_performance: float = 0.0  # 张保珍 hub W 固定额


@dataclass
class ActivityRowInput:
    """周舟 — K–AB 活动合计行。"""

    prospect_callbacks: float = 0.0
    five_day_callbacks: float = 0.0
    thirty_day_callbacks: float = 0.0
    defeat_callbacks: float = 0.0
    visit_count: float = 0.0
    group_chat_count: float = 0.0
    birthday_count: float = 0.0
    reputation_posts: float = 0.0
    complaint_handling: float = 0.0
    satisfaction_score: float = 0.0
    satisfaction_bonus: float = 0.0
    baoke_marketing_flat: float = 0.0


@dataclass
class BaokeMetricRow:
    """保客营销单行（AN–AT）。"""

    metric_type: str  # phone_callback | referral | mining | all_staff
    label: str = ""
    baseline_rate: float | None = None
    actual_rate: float | None = None
    improvement_pct: float | None = None
    delivery_count: float = 0.0
    flat_amount: float = 0.0


@dataclass
class BaokeStoreInput:
    """保客营销店面块。"""

    store_label: str = ""
    metrics: list[BaokeMetricRow] = field(default_factory=list)


@dataclass
class CustomerSpecialistInput:
    """统一容器（按岗位组装）。"""

    template: str
    left: LeftLineItemsInput | None = None
    activity: ActivityRowInput | None = None
    baoke: BaokeStoreInput | None = None


@dataclass
class PerformanceBreakdown:
    left_total_dengfang: float = 0.0
    left_total_zhangbaozhen: float = 0.0
    activity_total: float = 0.0
    baoke_total: float = 0.0

    def to_dict(self) -> dict[str, float]:
        out: dict[str, float] = {}
        if self.left_total_dengfang:
            out["左侧行项（邓芳）"] = self.left_total_dengfang
        if self.left_total_zhangbaozhen:
            out["左侧行项（张保珍）"] = self.left_total_zhangbaozhen
        if self.activity_total:
            out["活动行合计"] = self.activity_total
        if self.baoke_total:
            out["保客营销合计"] = self.baoke_total
        return out


@dataclass
class PerformanceResult:
    template: str
    performance_salary: float
    hub_metrics: dict[str, float]
    breakdown: PerformanceBreakdown
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def hub_vehicle_performance(self) -> float:
        """主展示值：优先加装绩效，否则第一个 hub 列。"""
        if "加装绩效" in self.hub_metrics:
            return float(self.hub_metrics["加装绩效"])
        if self.hub_metrics:
            return float(next(iter(self.hub_metrics.values())))
        return self.performance_salary
