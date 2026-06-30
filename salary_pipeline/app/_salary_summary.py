"""跨岗位族算薪汇总 — 从 Excel 抽取并对比金标准。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from salary_pipeline.calculators.customer_specialist import (
    compute_for_role as cs_compute,
    extract_role_inputs as cs_extract,
    list_roles as cs_list_roles,
    lookup_golden_cells as cs_lookup_golden,
)
from salary_pipeline.calculators.direct_store_manager import (
    compute_for_role as dsm_compute,
    extract_role_inputs as dsm_extract,
    list_roles as dsm_list_roles,
    lookup_golden_r as dsm_lookup_golden,
)
from salary_pipeline.calculators.invite_specialist import (
    compute_for_role as invite_compute,
    extract_role_inputs as invite_extract,
    list_roles as invite_list_roles,
    lookup_golden_af as invite_lookup_golden,
)
from salary_pipeline.calculators.invite_specialist.registry import hub_column_for_role
from salary_pipeline.calculators.recruit import (
    compute_for_role as recruit_compute,
    extract_role_inputs as recruit_extract,
    list_roles as recruit_list_roles,
    lookup_golden_hub as recruit_lookup_golden,
)
from salary_pipeline.calculators.sales_advisor import (
    compute_for_advisor as advisor_compute,
    hub_columns_for_gate,
    list_roles as advisor_list_roles,
    lookup_golden_hub as advisor_lookup_golden,
)
from salary_pipeline.calculators.new_media import (
    compute_for_role as nm_compute,
    extract_role_inputs as nm_extract,
    list_roles as nm_list_roles,
    lookup_golden_ab as nm_lookup_golden,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader

SUMMARY_COLUMNS = [
    "岗位族",
    "姓名",
    "职务",
    "版式",
    "Hub列",
    "计算值",
    "金标准",
    "差异",
    "一致",
]


@dataclass(frozen=True)
class SalaryFamilySpec:
    family_label: str
    list_roles: Callable[[], list[dict[str, Any]]]
    extract: Callable[[WorkbookLoader, str], Any]
    compute: Callable[[str, Any], Any]
    role_subtitle: Callable[[dict[str, Any]], str]
    hub_rows: Callable[[dict[str, Any], Any, WorkbookLoader], list[dict[str, Any]]]


def _nm_subtitle(role: dict[str, Any]) -> str:
    return str(role.get("title", ""))


def _nm_hub_rows(
    role: dict[str, Any], result: Any, loader: WorkbookLoader
) -> list[dict[str, Any]]:
    name = role["name"]
    golden = nm_lookup_golden(loader, name)
    calc = float(result.hub_vehicle_performance)
    g = float(golden) if golden is not None else None
    return [
        {
            "Hub列": "整车绩效",
            "计算值": calc,
            "金标准": g,
        }
    ]


def _invite_subtitle(role: dict[str, Any]) -> str:
    company = role.get("company", "")
    title = role.get("title", role.get("template", ""))
    return f"{company} · {title}".strip(" ·")


def _invite_hub_rows(
    role: dict[str, Any], result: Any, loader: WorkbookLoader
) -> list[dict[str, Any]]:
    name = role["name"]
    hub_col = hub_column_for_role(role)
    golden = invite_lookup_golden(loader, name)
    calc = float(result.hub_vehicle_performance)
    g = float(golden) if golden is not None else None
    return [{"Hub列": hub_col, "计算值": calc, "金标准": g}]


def _cs_subtitle(role: dict[str, Any]) -> str:
    return str(role.get("title", ""))


def _cs_hub_rows(
    role: dict[str, Any], result: Any, loader: WorkbookLoader
) -> list[dict[str, Any]]:
    name = role["name"]
    golden = cs_lookup_golden(loader, name)
    rows: list[dict[str, Any]] = []
    if result.hub_metrics:
        for hub_col, calc in result.hub_metrics.items():
            g = golden.get(hub_col) if golden else None
            rows.append(
                {
                    "Hub列": hub_col,
                    "计算值": float(calc),
                    "金标准": float(g) if g is not None else None,
                }
            )
    elif golden:
        for hub_col, g in golden.items():
            calc = float(result.performance_salary) if hub_col == "保客合计" else None
            rows.append(
                {
                    "Hub列": hub_col,
                    "计算值": calc,
                    "金标准": float(g),
                }
            )
    else:
        calc = float(result.performance_salary)
        rows.append({"Hub列": "子表合计", "计算值": calc, "金标准": None})
    return rows


def _dsm_subtitle(role: dict[str, Any]) -> str:
    return f"{role.get('store', '')} · {role.get('title', '')}".strip(" ·")


def _dsm_hub_rows(
    role: dict[str, Any], result: Any, loader: WorkbookLoader
) -> list[dict[str, Any]]:
    name = role["name"]
    golden = dsm_lookup_golden(loader, name)
    calc = float(result.hub_vehicle_performance)
    g = float(golden) if golden is not None else None
    return [{"Hub列": "整车完成考核", "计算值": calc, "金标准": g}]


def _recruit_subtitle(role: dict[str, Any]) -> str:
    return f"{role.get('store', '')} · {role.get('title', '')}".strip(" ·")


def _recruit_hub_rows(
    role: dict[str, Any], result: Any, loader: WorkbookLoader
) -> list[dict[str, Any]]:
    name = role["name"]
    golden = recruit_lookup_golden(loader, name)
    calc = float(result.hub_insurance_performance)
    g = float(golden) if golden is not None else None
    return [{"Hub列": "保险绩效", "计算值": calc, "金标准": g}]


def _advisor_subtitle(role: dict[str, Any]) -> str:
    store = role.get("store", "")
    return f"{store} · 销售顾问".strip(" ·")


def _advisor_hub_rows(
    role: dict[str, Any], result: Any, loader: WorkbookLoader
) -> list[dict[str, Any]]:
    name = role["name"]
    rows: list[dict[str, Any]] = []
    for hub_col in hub_columns_for_gate():
        calc = result.hub_metrics.get(hub_col)
        if calc is None:
            continue
        golden = advisor_lookup_golden(loader, name, hub_col)
        rows.append(
            {
                "Hub列": hub_col,
                "计算值": float(calc),
                "金标准": float(golden) if golden is not None else None,
            }
        )
    return rows


def _advisor_extract(loader: WorkbookLoader, name: str) -> Any:
    from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
    from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
    from salary_pipeline.paths import CONFIG_DIR
    from salary_pipeline.pipelines.commission_summary import load_month_config

    config = load_month_config(CONFIG_DIR)
    ctx = {"month_config": config}
    PerformanceSheetModule().run(ctx)
    skeleton = SummarySkeletonModule().run(ctx).metrics
    row = skeleton[skeleton["姓名"] == name]
    if row.empty:
        raise KeyError(name)
    return (row.iloc[0], ctx.get("computed_perf_frame"), loader)


def _advisor_compute(name: str, bundle: Any) -> Any:
    person, perf, loader = bundle
    return advisor_compute(
        person,
        perf,
        loader,
        topology_path=resolve_project_path(config["topology"]["sales"]),
    )


FAMILIES: tuple[SalaryFamilySpec, ...] = (
    SalaryFamilySpec(
        family_label="新媒体",
        list_roles=nm_list_roles,
        extract=nm_extract,
        compute=nm_compute,
        role_subtitle=_nm_subtitle,
        hub_rows=_nm_hub_rows,
    ),
    SalaryFamilySpec(
        family_label="邀约专员",
        list_roles=invite_list_roles,
        extract=invite_extract,
        compute=invite_compute,
        role_subtitle=_invite_subtitle,
        hub_rows=_invite_hub_rows,
    ),
    SalaryFamilySpec(
        family_label="客户专员",
        list_roles=cs_list_roles,
        extract=cs_extract,
        compute=cs_compute,
        role_subtitle=_cs_subtitle,
        hub_rows=_cs_hub_rows,
    ),
    SalaryFamilySpec(
        family_label="直营店经理",
        list_roles=dsm_list_roles,
        extract=dsm_extract,
        compute=dsm_compute,
        role_subtitle=_dsm_subtitle,
        hub_rows=_dsm_hub_rows,
    ),
    SalaryFamilySpec(
        family_label="招聘",
        list_roles=recruit_list_roles,
        extract=recruit_extract,
        compute=recruit_compute,
        role_subtitle=_recruit_subtitle,
        hub_rows=_recruit_hub_rows,
    ),
    SalaryFamilySpec(
        family_label="销售顾问",
        list_roles=advisor_list_roles,
        extract=_advisor_extract,
        compute=_advisor_compute,
        role_subtitle=_advisor_subtitle,
        hub_rows=_advisor_hub_rows,
    ),
)


def _row_diff(calc: float | None, golden: float | None) -> tuple[float | None, bool | None]:
    if calc is None or golden is None:
        return None, None
    delta = calc - golden
    return delta, abs(delta) < 0.02


def build_salary_summary(loader: WorkbookLoader) -> pd.DataFrame:
    """汇总各岗位族全员算薪结果与金标准对比。"""
    records: list[dict[str, Any]] = []
    for spec in FAMILIES:
        for role in spec.list_roles():
            name = role["name"]
            try:
                inputs = spec.extract(loader, name)
                result = spec.compute(name, inputs)
                hub_entries = spec.hub_rows(role, result, loader)
            except Exception as exc:
                records.append(
                    {
                        "岗位族": spec.family_label,
                        "姓名": name,
                        "职务": spec.role_subtitle(role),
                        "版式": role.get("template", ""),
                        "Hub列": "—",
                        "计算值": None,
                        "金标准": None,
                        "差异": None,
                        "一致": f"错误: {exc}",
                    }
                )
                continue

            if not hub_entries:
                hub_entries = [{"Hub列": "—", "计算值": None, "金标准": None}]

            for entry in hub_entries:
                calc = entry.get("计算值")
                golden = entry.get("金标准")
                delta, ok = _row_diff(
                    float(calc) if calc is not None else None,
                    float(golden) if golden is not None else None,
                )
                records.append(
                    {
                        "岗位族": spec.family_label,
                        "姓名": name,
                        "职务": spec.role_subtitle(role),
                        "版式": role.get("template", ""),
                        "Hub列": entry.get("Hub列", "—"),
                        "计算值": calc,
                        "金标准": golden,
                        "差异": delta,
                        "一致": "✓" if ok else ("—" if ok is None else "✗"),
                    }
                )

    return pd.DataFrame(records, columns=SUMMARY_COLUMNS)


def family_pass_counts(frame: pd.DataFrame) -> pd.DataFrame:
    """按岗位族统计一致 / 不一致 / 未对账行数。"""
    if frame.empty:
        return pd.DataFrame(columns=["岗位族", "一致", "不一致", "未对账", "合计"])

    def _count(group: pd.DataFrame, flag: str) -> int:
        return int((group["一致"] == flag).sum())

    rows = []
    for family, grp in frame.groupby("岗位族", sort=False):
        rows.append(
            {
                "岗位族": family,
                "一致": _count(grp, "✓"),
                "不一致": _count(grp, "✗"),
                "未对账": int(grp["一致"].isin(["—", None]).sum()),
                "合计": len(grp),
            }
        )
    return pd.DataFrame(rows)
