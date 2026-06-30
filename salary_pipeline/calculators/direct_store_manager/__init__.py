"""直营店经理岗位族底层算薪计算器。"""

from salary_pipeline.calculators.direct_store_manager.extract import (
    extract_role_inputs,
    lookup_golden_r,
    lookup_role_performance,
)
from salary_pipeline.calculators.direct_store_manager.formulas import (
    compute_store_block,
    compute_store_blocks,
)
from salary_pipeline.calculators.direct_store_manager.registry import (
    compute_for_role,
    default_input_for_role,
    get_role,
    hub_column_for_role,
    list_roles,
    load_role_registry,
)
from salary_pipeline.calculators.direct_store_manager.types import (
    PerformanceBreakdown,
    PerformanceResult,
    StoreBlockInput,
)

__all__ = [
    "PerformanceBreakdown",
    "PerformanceResult",
    "StoreBlockInput",
    "compute_for_role",
    "compute_store_block",
    "compute_store_blocks",
    "default_input_for_role",
    "extract_role_inputs",
    "get_role",
    "hub_column_for_role",
    "list_roles",
    "load_role_registry",
    "lookup_golden_r",
    "lookup_role_performance",
]
