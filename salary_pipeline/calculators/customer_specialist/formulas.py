"""客户部提成子表计算，对齐 Excel 公式语义。"""

from __future__ import annotations

from salary_pipeline.calculators.customer_specialist.types import (
    ActivityRowInput,
    BaokeMetricRow,
    BaokeStoreInput,
    CustomerSpecialistInput,
    LeftLineItemsInput,
    LineItem,
    PerformanceBreakdown,
    PerformanceResult,
)


def _line_subtotal_dengfang(item: LineItem) -> float:
    return item.coefficient * item.qty_dengfang


def _line_subtotal_zhangbaozhen(item: LineItem) -> float:
    return item.coefficient * item.qty_zhangbaozhen


def compute_left_line_items(inp: LeftLineItemsInput) -> tuple[float, float]:
    total_f = sum(_line_subtotal_dengfang(i) for i in inp.line_items)
    total_h = sum(_line_subtotal_zhangbaozhen(i) for i in inp.line_items)
    return total_f, total_h


def _improvement(row: BaokeMetricRow) -> float:
    if row.improvement_pct is not None:
        return float(row.improvement_pct)
    baseline = row.baseline_rate
    actual = row.actual_rate
    if baseline is None or actual is None:
        return 0.0
    if isinstance(baseline, str) or isinstance(actual, str):
        return float(row.improvement_pct or 0.0)
    return float(actual) - float(baseline)


def _tier_referral_unit(improvement: float) -> float:
    if improvement < 0.01:
        return 20.0
    if improvement < 0.03:
        return 30.0
    return 40.0


def _tier_mining_unit(improvement: float) -> float:
    if improvement >= 0.03:
        return 50.0
    if improvement >= 0.01:
        return 40.0
    return 30.0


def _tier_all_staff_unit(improvement: float) -> float:
    if improvement < 0.01:
        return 10.0
    if improvement < 0.03:
        return 20.0
    return 30.0


def compute_baoke_row(row: BaokeMetricRow) -> float:
    if row.metric_type == "phone_callback":
        return float(row.flat_amount)
    improvement = _improvement(row)
    if row.metric_type == "referral":
        unit = _tier_referral_unit(improvement)
    elif row.metric_type == "mining":
        unit = _tier_mining_unit(improvement)
    else:
        unit = _tier_all_staff_unit(improvement)
    return row.delivery_count * unit


def compute_baoke_store(inp: BaokeStoreInput) -> float:
    return sum(compute_baoke_row(row) for row in inp.metrics)


def compute_activity_row(inp: ActivityRowInput) -> float:
    callback_total = (
        inp.prospect_callbacks
        + inp.five_day_callbacks
        + inp.thirty_day_callbacks
        + inp.defeat_callbacks
    )
    callback_perf = callback_total * 2.0
    visit_perf = inp.visit_count * 6.0
    group_perf = inp.group_chat_count * 5.0
    birthday_perf = inp.birthday_count * 2.0
    reputation_perf = inp.reputation_posts * 50.0
    return (
        callback_perf
        + visit_perf
        + group_perf
        + birthday_perf
        + reputation_perf
        + inp.complaint_handling
        + inp.satisfaction_bonus
        + inp.baoke_marketing_flat
    )


def compute_for_input(data: CustomerSpecialistInput) -> PerformanceResult:
    breakdown = PerformanceBreakdown()
    hub_metrics: dict[str, float] = {}
    primary = 0.0

    if data.left is not None:
        total_f, total_h = compute_left_line_items(data.left)
        breakdown.left_total_dengfang = total_f
        breakdown.left_total_zhangbaozhen = total_h
        if data.left.person == "dengfang":
            hub_metrics["加装绩效"] = total_f
            primary = total_f
        else:
            hub_metrics["整车绩效"] = data.left.fixed_vehicle_performance
            hub_metrics["加装绩效"] = total_h
            primary = total_h

    if data.activity is not None:
        activity_total = compute_activity_row(data.activity)
        breakdown.activity_total = activity_total
        hub_metrics["加装绩效"] = activity_total
        primary = activity_total

    if data.baoke is not None:
        baoke_total = compute_baoke_store(data.baoke)
        breakdown.baoke_total = baoke_total
        if data.template == "left_and_baoke":
            hub_metrics["权限结余绩效"] = baoke_total
        elif data.template == "baoke_store":
            primary = baoke_total
        else:
            primary = max(primary, baoke_total)

    return PerformanceResult(
        template=data.template,
        performance_salary=primary,
        hub_metrics=hub_metrics,
        breakdown=breakdown,
    )
