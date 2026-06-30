"""直营店经理子表门店块公式。"""

from __future__ import annotations

from salary_pipeline.calculators.direct_store_manager.types import (
    PerformanceBreakdown,
    PerformanceResult,
    StoreBlockInput,
)

_COMPLETION_CAP = 1.1


def completion_rate(task: float, actual: float) -> float:
    if task == 0:
        return 0.0
    ratio = actual / task
    return min(ratio, _COMPLETION_CAP)


def compute_store_block(block: StoreBlockInput) -> tuple[float, PerformanceBreakdown]:
    showroom_completion = completion_rate(block.showroom_task, block.showroom_actual)
    showroom_commission = (
        block.showroom_actual * showroom_completion * block.showroom_rate
        + block.showroom_ev_actual * block.showroom_rate
    )
    channel_completion = completion_rate(block.channel_task, block.channel_actual)
    channel_commission = (
        channel_completion * block.channel_rate * block.channel_actual
        + block.channel_ev_task * block.channel_rate
    )
    unit_total = showroom_commission + channel_commission
    total = (
        unit_total
        + block.attach_commission
        + block.fixed_performance
        + block.extra_vehicle_commission
    )
    breakdown = PerformanceBreakdown(
        showroom_commission=showroom_commission,
        channel_commission=channel_commission,
        unit_commission_total=unit_total,
        attach_commission=block.attach_commission,
        fixed_performance=block.fixed_performance,
        extra_vehicle_commission=block.extra_vehicle_commission,
    )
    return total, breakdown


def compute_store_blocks(
    blocks: list[StoreBlockInput], *, template: str = "store_block"
) -> PerformanceResult:
    total = 0.0
    merged = PerformanceBreakdown()
    for block in blocks:
        part, bd = compute_store_block(block)
        total += part
        merged.showroom_commission += bd.showroom_commission
        merged.channel_commission += bd.channel_commission
        merged.unit_commission_total += bd.unit_commission_total
        merged.attach_commission += bd.attach_commission
        merged.fixed_performance += bd.fixed_performance
        merged.extra_vehicle_commission += bd.extra_vehicle_commission
    return PerformanceResult(
        template=template,
        performance_salary=total,
        hub_vehicle_performance=total,
        breakdown=merged,
        blocks=blocks,
    )
