"""销售顾问岗位族底层算薪计算器。"""

from salary_pipeline.calculators.sales_advisor.extract import (
    build_eval_perf_frame,
    compute_for_advisor,
    enrich_perf_frame,
    extract_advisor_input,
    lookup_golden_hub,
    lookup_golden_hub_all,
    match_advisor_row,
)
from salary_pipeline.calculators.sales_advisor.formulas import (
    compute_advisor_performance,
    eval_hub_column,
)
from salary_pipeline.calculators.sales_advisor.registry import (
    get_role,
    hub_columns_for_gate,
    hub_linked_names,
    is_hub_linked,
    list_roles,
    load_role_registry,
    subsheet_only_names,
)
from salary_pipeline.calculators.sales_advisor.topology_specs import (
    load_row_specs,
    parse_hub_formula,
)
from salary_pipeline.calculators.sales_advisor.types import (
    AdvisorPerformanceInput,
    AdvisorPerformanceResult,
    HubColumnFormula,
)

__all__ = [
    "AdvisorPerformanceInput",
    "AdvisorPerformanceResult",
    "HubColumnFormula",
    "compute_advisor_performance",
    "build_eval_perf_frame",
    "compute_for_advisor",
    "enrich_perf_frame",
    "eval_hub_column",
    "extract_advisor_input",
    "get_role",
    "hub_columns_for_gate",
    "hub_linked_names",
    "is_hub_linked",
    "list_roles",
    "load_role_registry",
    "load_row_specs",
    "lookup_golden_hub",
    "lookup_golden_hub_all",
    "match_advisor_row",
    "parse_hub_formula",
    "subsheet_only_names",
]
