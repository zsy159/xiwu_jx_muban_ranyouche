"""新媒体岗位族底层算薪计算器。"""

from salary_pipeline.calculators.new_media.extract import (
    all_role_names,
    extract_role_inputs,
    lookup_golden_ab,
)
from salary_pipeline.calculators.new_media.formulas import (
    compute_live_anchor,
    compute_manual,
    compute_ops_manager,
    compute_video_ops,
)
from salary_pipeline.calculators.new_media.registry import (
    compute_for_role,
    default_input_for_role,
    get_role,
    list_roles,
    load_role_registry,
)
from salary_pipeline.calculators.new_media.types import (
    LiveAnchorInput,
    ManualPerformanceInput,
    MetricPair,
    OpsManagerInput,
    PerformanceBreakdown,
    PerformanceResult,
    VideoOpsInput,
)

__all__ = [
    "LiveAnchorInput",
    "ManualPerformanceInput",
    "MetricPair",
    "OpsManagerInput",
    "PerformanceBreakdown",
    "PerformanceResult",
    "VideoOpsInput",
    "all_role_names",
    "compute_for_role",
    "compute_live_anchor",
    "compute_manual",
    "compute_ops_manager",
    "compute_video_ops",
    "default_input_for_role",
    "extract_role_inputs",
    "get_role",
    "list_roles",
    "load_role_registry",
    "lookup_golden_ab",
]
