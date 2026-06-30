"""邀约专员提成子表总绩效计算。"""

from __future__ import annotations

from salary_pipeline.calculators.invite_specialist.types import (
    InviteDccInput,
    PerformanceBreakdown,
    PerformanceResult,
)


def compute_dms(inp: InviteDccInput) -> tuple[float, float]:
    """每项达成计 dms_per_item_reward；七项均达成再追加 dms_all_seven_bonus。"""
    score = inp.dms_achieved_count * inp.dms_per_item_reward
    bonus = inp.dms_all_seven_bonus if inp.dms_all_seven_achieved else 0.0
    return score, bonus


def compute_wuhou_dcc(inp: InviteDccInput) -> PerformanceResult:
    dms_score, dms_bonus = compute_dms(inp)
    invite_perf = inp.invite_groups * inp.invite_unit_rate
    invite_rate = inp.invite_rate_bonus_per_group * inp.invite_groups
    deal_perf = inp.deal_count * inp.deal_unit_rate
    deal_rate = inp.deal_count * inp.deal_rate_bonus_per_unit
    heavy_attack = inp.heavy_attack_bonus * inp.heavy_attack_multiplier
    total = (
        dms_score
        + dms_bonus
        + invite_perf
        + invite_rate
        + deal_perf
        + deal_rate
        + heavy_attack
        + inp.task_adjustment
    )
    breakdown = PerformanceBreakdown(
        six_dimension=dms_score,
        six_dimension_bonus=dms_bonus,
        invite_groups=invite_perf,
        invite_rate_bonus=invite_rate,
        deal_commission=deal_perf,
        deal_rate_bonus=deal_rate,
        heavy_attack=heavy_attack,
        task_adjustment=inp.task_adjustment,
    )
    return PerformanceResult(
        template="xiwu_dcc",
        performance_salary=total,
        hub_vehicle_performance=total,
        breakdown=breakdown,
    )


def compute_chaoshi_dcc(inp: InviteDccInput) -> PerformanceResult:
    dms_score, dms_bonus = compute_dms(inp)
    invite_perf = inp.invite_groups * inp.invite_unit_rate
    invite_rate = inp.invite_rate_bonus_per_group * inp.invite_groups
    deal_perf = inp.deal_count * inp.deal_unit_rate
    deal_rate = inp.deal_count * inp.deal_rate_bonus_per_unit
    achieved_bonus = inp.achieved_invite_volume * inp.per_group_store_bonus
    total = (
        dms_score
        + dms_bonus
        + invite_perf
        + invite_rate
        + deal_perf
        + deal_rate
        + achieved_bonus
        - inp.task_penalty
    )
    breakdown = PerformanceBreakdown(
        six_dimension=dms_score,
        six_dimension_bonus=dms_bonus,
        invite_groups=invite_perf,
        invite_rate_bonus=invite_rate,
        deal_commission=deal_perf,
        deal_rate_bonus=deal_rate,
        process_kpi=achieved_bonus,
        task_penalty=inp.task_penalty,
    )
    return PerformanceResult(
        template="chaoshi_dcc",
        performance_salary=total,
        hub_vehicle_performance=total,
        breakdown=breakdown,
    )


compute_airport_dcc = compute_chaoshi_dcc


def compute_chongzhou_invite(inp: InviteDccInput) -> PerformanceResult:
    """崇州直营店邀约专员：AD = I+L+O+T+W+Z−AC−F（子表 R17 版式）。"""
    dms_score, dms_bonus = compute_dms(inp)
    dms_total = dms_score + dms_bonus
    invite_perf = inp.invite_groups * inp.invite_unit_rate
    process_kpi = inp.invite_rate_bonus_per_group * inp.invite_groups
    deal_perf = inp.deal_count * inp.deal_unit_rate
    deal_rate = inp.deal_count * inp.deal_rate_bonus_per_unit
    heavy_attack = inp.heavy_attack_bonus * inp.heavy_attack_multiplier
    total = (
        dms_total
        + invite_perf
        + deal_perf
        + process_kpi
        + deal_rate
        + heavy_attack
        - inp.task_penalty
        - inp.call_answer_penalty
    )
    breakdown = PerformanceBreakdown(
        six_dimension=dms_total,
        invite_groups=invite_perf,
        process_kpi=process_kpi,
        deal_commission=deal_perf,
        deal_rate_bonus=deal_rate,
        heavy_attack=heavy_attack,
        task_penalty=inp.task_penalty,
        call_answer_penalty=inp.call_answer_penalty,
    )
    return PerformanceResult(
        template="chongzhou_invite",
        performance_salary=total,
        hub_vehicle_performance=total,
        breakdown=breakdown,
    )
