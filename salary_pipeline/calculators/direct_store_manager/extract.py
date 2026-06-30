"""从主账套「直营店经理提成 (财务)」抽取计算器输入。"""

from __future__ import annotations

from typing import Any

from salary_pipeline.calculators.direct_store_manager.registry import get_role
from salary_pipeline.calculators.direct_store_manager.types import StoreBlockInput
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader

SHEET = "直营店经理提成 (财务)"


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_num(value: Any) -> float:
    if value is None:
        return 0.0
    return _num(value)


def extract_block(loader: WorkbookLoader, row: int) -> StoreBlockInput:
    ws = loader._workbook()[SHEET]
    return StoreBlockInput(
        store_label=str(ws.cell(row, 2).value or ""),
        showroom_task=_num(ws.cell(row, 3).value),
        showroom_actual=_num(ws.cell(row, 4).value),
        showroom_ev_actual=_num(ws.cell(row, 5).value),
        showroom_rate=_num(ws.cell(row, 7).value) or 100.0,
        channel_task=_num(ws.cell(row, 9).value),
        channel_actual=_num(ws.cell(row, 10).value),
        channel_ev_task=_num(ws.cell(row, 11).value),
        channel_rate=_num(ws.cell(row, 13).value) or 50.0,
        attach_commission=_num(ws.cell(row, 16).value),
        fixed_performance=_optional_num(ws.cell(row, 17).value),
        extra_vehicle_commission=_num(ws.cell(row, 22).value),
    )


def extract_role_inputs(
    loader: WorkbookLoader, role_name: str
) -> list[StoreBlockInput]:
    role = get_role(role_name)
    if role is None:
        raise KeyError(role_name)
    blocks = role.get("excel_blocks") or []
    if not blocks:
        return [StoreBlockInput(store_label=str(role.get("store", "")))]
    return [extract_block(loader, int(b["row"])) for b in blocks]


def lookup_golden_r(loader: WorkbookLoader, role_name: str) -> float | None:
    role = get_role(role_name)
    if not role:
        return None
    ws = loader._workbook()[SHEET]
    total = 0.0
    found = False
    for block in role.get("excel_blocks", []):
        row = int(block["row"])
        val = ws.cell(row, 18).value
        if val is None:
            continue
        found = True
        total += _num(val)
    return total if found else None


def lookup_role_performance(loader: WorkbookLoader, role_name: str) -> float:
    golden = lookup_golden_r(loader, role_name)
    return golden if golden is not None else 0.0
