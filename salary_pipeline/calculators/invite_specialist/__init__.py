"""邀约专员岗位族底层算薪计算器。"""

# 先加载无依赖子模块，避免 Streamlit 热重载时循环导入导致符号未绑定
from salary_pipeline.calculators.invite_specialist.types import (
    AirportDccInput,
    ChaoshiDccInput,
    InviteDccInput,
    PerformanceBreakdown,
    PerformanceResult,
    WuhouDccInput,
)
from salary_pipeline.calculators.invite_specialist.formulas import (
    compute_airport_dcc,
    compute_chaoshi_dcc,
    compute_chongzhou_invite,
    compute_wuhou_dcc,
)
from salary_pipeline.calculators.invite_specialist.registry import (
    compute_for_role,
    default_input_for_role,
    get_role,
    list_roles,
    load_role_registry,
)
from salary_pipeline.calculators.invite_specialist.extract import (
    all_role_names,
    extract_role_inputs,
    lookup_golden_af,
)

__all__ = [
    "InviteDccInput",
    "AirportDccInput",
    "ChaoshiDccInput",
    "PerformanceBreakdown",
    "PerformanceResult",
    "WuhouDccInput",
    "all_role_names",
    "compute_airport_dcc",
    "compute_chaoshi_dcc",
    "compute_chongzhou_invite",
    "compute_for_role",
    "compute_wuhou_dcc",
    "default_input_for_role",
    "extract_role_inputs",
    "get_role",
    "list_roles",
    "load_role_registry",
    "lookup_golden_af",
]
