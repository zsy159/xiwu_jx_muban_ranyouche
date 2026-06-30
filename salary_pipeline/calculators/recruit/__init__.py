"""招聘岗位族底层算薪计算器。"""

from salary_pipeline.calculators.recruit.extract import (
    extract_role_inputs,
    extract_team_block,
    lookup_golden_cells,
    lookup_golden_hub,
    lookup_golden_sumif,
    lookup_role_performance,
)
from salary_pipeline.calculators.recruit.formulas import (
    compute_person_commission,
    compute_recruit_performance,
)
from salary_pipeline.calculators.recruit.registry import (
    compute_for_role,
    get_role,
    get_team_block_config,
    hub_column_for_role,
    hub_linked_names,
    is_hub_linked,
    list_roles,
    load_role_registry,
)
from salary_pipeline.calculators.recruit.types import (
    RecruitPerformanceResult,
    RecruitTeamInput,
)

__all__ = [
    "RecruitPerformanceResult",
    "RecruitTeamInput",
    "compute_for_role",
    "compute_person_commission",
    "compute_recruit_performance",
    "extract_role_inputs",
    "extract_team_block",
    "get_role",
    "get_team_block_config",
    "hub_column_for_role",
    "hub_linked_names",
    "is_hub_linked",
    "list_roles",
    "load_role_registry",
    "lookup_golden_cells",
    "lookup_golden_hub",
    "lookup_golden_sumif",
    "lookup_role_performance",
]
