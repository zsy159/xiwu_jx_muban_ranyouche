"""招聘岗位族：团队分配公式。"""

from __future__ import annotations

from salary_pipeline.calculators.recruit.types import (
    RecruitPerformanceResult,
    RecruitTeamInput,
)


def compute_person_commission(team: RecruitTeamInput) -> float:
    """个人提成 = 到岗数 × 单人招聘提成 × 分配比例。"""
    return team.onboard_count * team.commission_per_hire * team.allocation_ratio


def compute_recruit_performance(
    name: str,
    team: RecruitTeamInput,
    *,
    template: str = "team_allocation",
) -> RecruitPerformanceResult:
    amount = compute_person_commission(team)
    return RecruitPerformanceResult(
        name=name,
        insurance_performance=amount,
        team=team,
        metadata={
            "template": template,
            "formula": "onboard_count * commission_per_hire * allocation_ratio",
        },
    )
