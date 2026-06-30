"""客户专员岗位族底层算薪计算器。"""

from salary_pipeline.calculators.customer_specialist.extract import (
    extract_role_inputs,
    lookup_golden_cells,
)
from salary_pipeline.calculators.customer_specialist.formulas import compute_for_input
from salary_pipeline.calculators.customer_specialist.registry import (
    compute_for_role,
    default_input_for_role,
    get_role,
    hub_mapping_for_role,
    list_roles,
    load_role_registry,
    lookup_role_hub_metrics,
)
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

__all__ = [
    "ActivityRowInput",
    "BaokeMetricRow",
    "BaokeStoreInput",
    "CustomerSpecialistInput",
    "LeftLineItemsInput",
    "LineItem",
    "PerformanceBreakdown",
    "PerformanceResult",
    "compute_for_input",
    "compute_for_role",
    "default_input_for_role",
    "extract_role_inputs",
    "get_role",
    "hub_mapping_for_role",
    "list_roles",
    "load_role_registry",
    "lookup_golden_cells",
    "lookup_role_hub_metrics",
]
