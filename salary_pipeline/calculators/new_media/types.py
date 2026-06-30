"""新媒体算薪：输入/输出数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricPair:
    """目标 / 实际 成对指标（列 D–G）。"""

    target: float = 0.0
    actual: float = 0.0


@dataclass
class LiveAnchorInput:
    """直播运维专员 / 主播（曾子乂、何玉、王芝婕、蓝仁楷）。"""

    live_sessions: MetricPair = field(default_factory=MetricPair)
    leads: MetricPair = field(default_factory=MetricPair)
    fans: MetricPair = field(default_factory=MetricPair)
    videos: MetricPair = field(default_factory=MetricPair)
    kpi_base: float = 7000.0
    score_weights: tuple[float, float, float, float] = (40.0, 40.0, 10.0, 10.0)
    terminal_unit_rate: float = 50.0
    terminal_count: float = 0.0
    lead_excess_unit_rate: float = 10.0
    lead_excess_cap: float = 1000.0
    session_excess_unit_rate: float = 100.0
    session_excess_cap: float = 500.0
    session_excess_threshold: float = 5.0
    track_session_excess: bool = False


@dataclass
class VideoOpsInput:
    """短视频运维专员（黄凤）。"""

    videos: MetricPair = field(default_factory=MetricPair)
    play_count: MetricPair = field(default_factory=MetricPair)
    short_video_fans: MetricPair = field(default_factory=MetricPair)
    xiaohongshu: MetricPair = field(default_factory=MetricPair)
    kpi_base: float = 6000.0
    score_weights: tuple[float, float, float, float] = (40.0, 20.0, 20.0, 20.0)
    terminal_unit_rate: float = 20.0
    terminal_count: float = 0.0
    quality_video_unit_rate: float = 50.0
    quality_video_count: float = 0.0
    excess_video_unit_rate: float = 50.0
    excess_video_cap: float = 500.0


@dataclass
class OpsManagerInput:
    """运维主管（肖廷忠）。"""

    live_sessions: MetricPair = field(default_factory=MetricPair)
    video_creations: MetricPair = field(default_factory=MetricPair)
    leads: MetricPair = field(default_factory=MetricPair)
    store_visits: MetricPair = field(default_factory=MetricPair)
    kpi_base: float = 8000.0
    score_weights: tuple[float, float, float, float] = (25.0, 25.0, 25.0, 25.0)
    terminal_unit_rate: float = 40.0
    terminal_count: float = 0.0


@dataclass
class ManualPerformanceInput:
    """手工录入整车绩效（赵金秀等）。"""

    performance_salary: float = 0.0


@dataclass
class PerformanceBreakdown:
    position_kpi: float = 0.0
    terminal_commission: float = 0.0
    lead_excess_bonus: float = 0.0
    session_excess_bonus: float = 0.0
    quality_video_bonus: float = 0.0
    excess_video_bonus: float = 0.0
    total_score: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "岗位绩效": self.position_kpi,
            "终端量提成": self.terminal_commission,
            "线索超额奖励": self.lead_excess_bonus,
            "场次超额奖励": self.session_excess_bonus,
            "优质视频奖励": self.quality_video_bonus,
            "视频超额奖励": self.excess_video_bonus,
            "考核得分": self.total_score,
        }


@dataclass
class PerformanceResult:
    template: str
    performance_salary: float
    hub_vehicle_performance: float
    breakdown: PerformanceBreakdown
    metadata: dict[str, Any] = field(default_factory=dict)
