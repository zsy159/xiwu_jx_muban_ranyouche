"""从主账套「招聘」子表抽取团队分配输入。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from salary_pipeline.calculators.recruit.registry import (
    get_role,
    get_team_block_config,
    list_roles,
)
from salary_pipeline.calculators.recruit.types import RecruitTeamInput
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name
from salary_pipeline.data_ingestion.recruit_sheet import (
    AMOUNT_COL,
    NAME_COL,
    load_recruit_frame,
    load_team_allocation_frame,
    lookup_insurance_performance,
)

HUB_SHEET = "提成汇总"
HUB_INSURANCE_COL = 26  # Z = 保险绩效


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _anchor_team_params(frame: pd.DataFrame) -> tuple[float, float, float]:
    """首行含到岗数/单人提成的记录为团队锚点。"""
    for _, row in frame.iterrows():
        onboard = row.get("onboard_count")
        rate = row.get("commission_per_hire")
        if onboard is not None and not pd.isna(onboard) and rate is not None and not pd.isna(rate):
            total = row.get("total_commission")
            total_val = _num(total) if total is not None and not pd.isna(total) else _num(onboard) * _num(rate)
            return _num(onboard), _num(rate), total_val
    return 0.0, 0.0, 0.0


def extract_team_block(loader: WorkbookLoader) -> dict[str, RecruitTeamInput]:
    """提取招聘子表团队分配块，按登记姓名返回输入。"""
    frame = load_team_allocation_frame(loader)
    if frame.empty:
        return {}

    onboard_count, commission_per_hire, total_commission = _anchor_team_params(frame)
    out: dict[str, RecruitTeamInput] = {}
    for _, row in frame.iterrows():
        name = row.get("name")
        if not name:
            continue
        ratio = row.get("allocation_ratio")
        amount = row.get("amount")
        out[str(name)] = RecruitTeamInput(
            name=str(name),
            onboard_count=onboard_count,
            commission_per_hire=commission_per_hire,
            total_commission=total_commission,
            allocation_ratio=_num(ratio) if ratio is not None and not pd.isna(ratio) else 0.0,
            sheet_amount=_num(amount) if amount is not None and not pd.isna(amount) else None,
            source_row=int(row["excel_row"]) if "excel_row" in row else None,
        )
    return out


def extract_role_inputs(loader: WorkbookLoader, role_name: str) -> RecruitTeamInput:
    role = get_role(role_name)
    if role is None:
        raise KeyError(role_name)
    block = extract_team_block(loader)
    if role_name in block:
        return block[role_name]
    return RecruitTeamInput(
        name=role_name,
        onboard_count=0.0,
        commission_per_hire=0.0,
        total_commission=0.0,
        allocation_ratio=0.0,
    )


def lookup_golden_cells(loader: WorkbookLoader, role_name: str) -> dict[str, float]:
    """从登记 golden_cells 读取子表金标准。"""
    role = get_role(role_name)
    if not role:
        return {}
    cells = role.get("golden_cells") or {}
    cfg = get_team_block_config()
    sheet = str(cfg.get("sheet", "招聘"))
    out: dict[str, float] = {}
    for label, address in cells.items():
        val = loader.read_cell_value(sheet, str(address))
        if val is not None:
            out[str(label)] = _num(val)
    return out


def lookup_golden_hub(loader: WorkbookLoader, role_name: str) -> float | None:
    """从金标准提成汇总读取该人保险绩效（Hub Z 列）。"""
    role = get_role(role_name)
    if not role:
        return None
    hub_row = role.get("hub_excel_row")
    if not hub_row:
        return None
    ws = loader.worksheet(HUB_SHEET)
    val = ws.cell(int(hub_row), HUB_INSURANCE_COL).value
    if val is None:
        return None
    return _num(val)


def lookup_role_performance(loader: WorkbookLoader, role_name: str) -> float:
    from salary_pipeline.calculators.recruit.formulas import compute_person_commission

    team = extract_role_inputs(loader, role_name)
    if team.allocation_ratio > 0 or team.onboard_count > 0:
        return compute_person_commission(team)
    frame = load_recruit_frame(loader)
    return lookup_insurance_performance(frame, role_name)


def lookup_golden_sumif(loader: WorkbookLoader, role_name: str) -> float | None:
    """子表 W 列金标准（=SUMIF），供对账。"""
    frame = load_recruit_frame(loader)
    val = lookup_insurance_performance(frame, role_name)
    return val if val else lookup_golden_cells(loader, role_name).get("提成金额")
