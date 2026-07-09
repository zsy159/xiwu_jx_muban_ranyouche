"""从主账套「邀约专员提成」抽取计算器输入。"""

from __future__ import annotations

from typing import Any

from salary_pipeline.calculators.invite_specialist.registry import get_role
from salary_pipeline.calculators.invite_specialist.types import InviteDccInput
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dms_from_row(ws: Any, row: int) -> dict[str, Any]:
    g = ws.cell(row, 7).value
    achieved = _num(ws.cell(row, 8).value)
    all_seven = isinstance(g, str) and "均达成" in g and achieved >= 7
    return {
        "dms_achieved_count": achieved,
        "dms_all_seven_achieved": all_seven,
    }


def extract_role_inputs(loader: WorkbookLoader, role_name: str) -> InviteDccInput:
    role = get_role(role_name)
    if role is None:
        raise KeyError(role_name)
    block = role.get("excel_block")
    if not block:
        from salary_pipeline.calculators.invite_specialist.registry import (
            default_input_for_role,
        )

        return default_input_for_role(role)

    ws = loader.worksheet("邀约专员提成")
    row = int(block["row"])
    template = role["template"]
    dms = _dms_from_row(ws, row)

    if template in ("xiwu_dcc", "wuhou_dcc"):
        return InviteDccInput(
            **dms,
            invite_groups=_num(ws.cell(row, 11).value),
            invite_unit_rate=_num(ws.cell(row, 10).value),
            invite_rate_bonus_per_group=_num(ws.cell(row, 19).value),
            deal_count=_num(ws.cell(row, 14).value),
            deal_unit_rate=_num(ws.cell(row, 13).value),
            deal_rate_bonus_per_unit=_num(ws.cell(row, 22).value),
            heavy_attack_bonus=_num(ws.cell(row, 24).value),
            heavy_attack_multiplier=_num(ws.cell(row, 25).value),
            task_adjustment=_num(ws.cell(row, 29).value),
        )

    if template in ("chaoshi_dcc", "airport_dcc"):
        return InviteDccInput(
            **dms,
            invite_groups=_num(ws.cell(row, 11).value),
            invite_unit_rate=_num(ws.cell(row, 10).value),
            invite_rate_bonus_per_group=0.0,
            deal_count=_num(ws.cell(row, 14).value),
            deal_unit_rate=_num(ws.cell(row, 13).value),
            deal_rate_bonus_per_unit=_num(ws.cell(row, 20).value),
            achieved_invite_volume=_num(ws.cell(row, 16).value),
            per_group_store_bonus=_num(ws.cell(row, 17).value),
            task_penalty=_num(ws.cell(row, 24).value),
        )

    if template == "chongzhou_invite":
        return InviteDccInput(
            **dms,
            invite_groups=_num(ws.cell(row, 11).value),
            invite_unit_rate=_num(ws.cell(row, 10).value),
            invite_rate_bonus_per_group=_num(ws.cell(row, 19).value),
            deal_count=_num(ws.cell(row, 14).value),
            deal_unit_rate=_num(ws.cell(row, 13).value),
            deal_rate_bonus_per_unit=_num(ws.cell(row, 22).value),
            heavy_attack_bonus=_num(ws.cell(row, 24).value),
            heavy_attack_multiplier=_num(ws.cell(row, 25).value),
            task_penalty=_num(ws.cell(row, 29).value),
            call_answer_penalty=_num(ws.cell(row, 6).value),
        )

    raise ValueError(template)


def lookup_golden_af(loader: WorkbookLoader, role_name: str) -> float | None:
    role = get_role(role_name)
    if not role:
        return None
    row = role.get("excel_block", {}).get("row")
    if not row:
        return None
    ws = loader.worksheet("邀约专员提成")
    template = role.get("template", "")
    # 崇州个人 AF 为空，金标准在 AD 列（AF15=AD17）
    col = 30 if template == "chongzhou_invite" else 32
    val = ws.cell(int(row), col).value
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def lookup_role_performance(loader: WorkbookLoader, role_name: str) -> float:
    """子表发放金额：DCC 读 AF，崇州读 AD。"""
    golden = lookup_golden_af(loader, role_name)
    return golden if golden is not None else 0.0


def all_role_names() -> list[str]:
    from salary_pipeline.calculators.invite_specialist.registry import load_role_registry

    return [r["name"] for r in load_role_registry().get("roles", [])]
