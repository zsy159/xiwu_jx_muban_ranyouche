"""新媒体子表 Q 列（绩效薪资）纯函数计算，对齐 Excel 公式语义。"""

from __future__ import annotations

from salary_pipeline.calculators.new_media.types import (
    LiveAnchorInput,
    ManualPerformanceInput,
    MetricPair,
    OpsManagerInput,
    PerformanceBreakdown,
    PerformanceResult,
    VideoOpsInput,
)


def _achievement_rate(pair: MetricPair) -> float:
    if pair.target <= 0:
        return 0.0
    return pair.actual / pair.target


def _score_at_rate(weight: float, rate: float) -> float:
    if rate >= 1.0:
        return weight
    return weight * rate


def _assessment_total(
    pairs: tuple[MetricPair, MetricPair, MetricPair, MetricPair],
    weights: tuple[float, float, float, float],
) -> float:
    rates = tuple(_achievement_rate(p) for p in pairs)
    scores = tuple(_score_at_rate(w, r) for w, r in zip(weights, rates, strict=True))
    return sum(scores)


def _position_kpi(kpi_base: float, total_score: float) -> float:
    """等价于 Excel =H{n}*H{target}% ，即 KPI 基数 × 得分 / 100。"""
    return kpi_base * (total_score / 100.0)


def _capped_linear(
    amount: float,
    *,
    unit_rate: float,
    cap: float,
    cap_threshold: float | None = None,
) -> float:
    """IFS(amount>=threshold, cap, amount<=threshold, amount*unit_rate) 语义。"""
    if amount <= 0:
        return 0.0
    if cap_threshold is not None and amount >= cap_threshold:
        return cap
    return min(cap, amount * unit_rate)


def compute_live_anchor(inp: LiveAnchorInput) -> PerformanceResult:
    pairs = (inp.live_sessions, inp.leads, inp.fans, inp.videos)
    total_score = _assessment_total(pairs, inp.score_weights)
    position_kpi = _position_kpi(inp.kpi_base, total_score)
    terminal = inp.terminal_unit_rate * inp.terminal_count
    lead_excess = inp.leads.actual - inp.leads.target
    lead_bonus = _capped_linear(
        lead_excess,
        unit_rate=inp.lead_excess_unit_rate,
        cap=inp.lead_excess_cap,
        cap_threshold=100.0,
    )
    session_bonus = 0.0
    if inp.track_session_excess:
        session_excess = inp.live_sessions.actual - inp.live_sessions.target
        session_bonus = _capped_linear(
            session_excess,
            unit_rate=inp.session_excess_unit_rate,
            cap=inp.session_excess_cap,
            cap_threshold=inp.session_excess_threshold,
        )
    total = position_kpi + terminal + lead_bonus + session_bonus
    breakdown = PerformanceBreakdown(
        position_kpi=position_kpi,
        terminal_commission=terminal,
        lead_excess_bonus=lead_bonus,
        session_excess_bonus=session_bonus,
        total_score=total_score,
    )
    return PerformanceResult(
        template="live_anchor",
        performance_salary=total,
        hub_vehicle_performance=total,
        breakdown=breakdown,
    )


def compute_video_ops(inp: VideoOpsInput) -> PerformanceResult:
    pairs = (inp.videos, inp.play_count, inp.short_video_fans, inp.xiaohongshu)
    total_score = _assessment_total(pairs, inp.score_weights)
    position_kpi = _position_kpi(inp.kpi_base, total_score)
    terminal = inp.terminal_unit_rate * inp.terminal_count
    quality_bonus = inp.quality_video_unit_rate * inp.quality_video_count
    excess_videos = max(0.0, inp.videos.actual - inp.videos.target)
    excess_bonus = _capped_linear(
        excess_videos,
        unit_rate=inp.excess_video_unit_rate,
        cap=inp.excess_video_cap,
    )
    total = position_kpi + terminal + quality_bonus + excess_bonus
    breakdown = PerformanceBreakdown(
        position_kpi=position_kpi,
        terminal_commission=terminal,
        quality_video_bonus=quality_bonus,
        excess_video_bonus=excess_bonus,
        total_score=total_score,
    )
    return PerformanceResult(
        template="video_ops",
        performance_salary=total,
        hub_vehicle_performance=total,
        breakdown=breakdown,
    )


def compute_ops_manager(inp: OpsManagerInput) -> PerformanceResult:
    pairs = (inp.live_sessions, inp.video_creations, inp.leads, inp.store_visits)
    total_score = _assessment_total(pairs, inp.score_weights)
    position_kpi = _position_kpi(inp.kpi_base, total_score)
    terminal = inp.terminal_unit_rate * inp.terminal_count
    total = position_kpi + terminal
    breakdown = PerformanceBreakdown(
        position_kpi=position_kpi,
        terminal_commission=terminal,
        total_score=total_score,
    )
    return PerformanceResult(
        template="ops_manager",
        performance_salary=total,
        hub_vehicle_performance=total,
        breakdown=breakdown,
    )


def compute_manual(inp: ManualPerformanceInput) -> PerformanceResult:
    value = float(inp.performance_salary)
    return PerformanceResult(
        template="manual",
        performance_salary=value,
        hub_vehicle_performance=value,
        breakdown=PerformanceBreakdown(),
        metadata={"source": "manual_entry"},
    )
