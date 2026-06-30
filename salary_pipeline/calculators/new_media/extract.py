"""从主账套「新媒体」子表抽取计算器输入（供界面预填 / 对账）。"""

from __future__ import annotations

from typing import Any

from salary_pipeline.calculators.new_media.registry import get_role, load_role_registry
from salary_pipeline.calculators.new_media.types import (
    LiveAnchorInput,
    ManualPerformanceInput,
    MetricPair,
    OpsManagerInput,
    VideoOpsInput,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pair_from_rows(ws: Any, target_row: int, actual_row: int, col: int) -> MetricPair:
    return MetricPair(
        target=_num(ws.cell(target_row, col).value),
        actual=_num(ws.cell(actual_row, col).value),
    )


def extract_role_inputs(loader: WorkbookLoader, role_name: str) -> Any:
    role = get_role(role_name)
    if role is None:
        raise KeyError(role_name)
    block = role.get("excel_block")
    if not block:
        from salary_pipeline.calculators.new_media.registry import (
            default_input_for_role as registry_default,
        )

        return registry_default(role)

    ws = loader._workbook()["新媒体"]
    template = role["template"]

    if template == "manual":
        ab_row = int(block.get("ab_row", 11))
        return ManualPerformanceInput(performance_salary=_num(ws.cell(ab_row, 28).value))

    t_row = int(block["target_row"])
    a_row = int(block["actual_row"])

    if template == "live_anchor":
        return LiveAnchorInput(
            live_sessions=_pair_from_rows(ws, t_row, a_row, 4),
            leads=_pair_from_rows(ws, t_row, a_row, 5),
            fans=_pair_from_rows(ws, t_row, a_row, 6),
            videos=_pair_from_rows(ws, t_row, a_row, 7),
            kpi_base=_num(ws.cell(t_row, 8).value),
            terminal_unit_rate=_num(ws.cell(a_row, 10).value),
            terminal_count=_num(ws.cell(a_row, 11).value),
            lead_excess_unit_rate=_num(ws.cell(a_row, 12).value) or 10.0,
            session_excess_unit_rate=_num(ws.cell(a_row, 14).value) or 100.0,
            track_session_excess=bool(block.get("track_session_excess", False)),
        )
    if template == "video_ops":
        return VideoOpsInput(
            videos=_pair_from_rows(ws, t_row, a_row, 4),
            play_count=_pair_from_rows(ws, t_row, a_row, 5),
            short_video_fans=_pair_from_rows(ws, t_row, a_row, 6),
            xiaohongshu=_pair_from_rows(ws, t_row, a_row, 7),
            kpi_base=_num(ws.cell(t_row, 8).value),
            terminal_unit_rate=_num(ws.cell(a_row, 10).value),
            terminal_count=_num(ws.cell(a_row, 11).value),
            quality_video_unit_rate=_num(ws.cell(a_row, 12).value) or 50.0,
            quality_video_count=_num(ws.cell(a_row, 13).value),
            excess_video_unit_rate=_num(ws.cell(a_row, 14).value) or 50.0,
        )
    if template == "ops_manager":
        return OpsManagerInput(
            live_sessions=_pair_from_rows(ws, t_row, a_row, 4),
            video_creations=_pair_from_rows(ws, t_row, a_row, 5),
            leads=_pair_from_rows(ws, t_row, a_row, 6),
            store_visits=_pair_from_rows(ws, t_row, a_row, 7),
            kpi_base=_num(ws.cell(t_row, 8).value),
            terminal_count=_num(ws.cell(a_row, 11).value),
        )
    raise ValueError(template)




def lookup_golden_ab(loader: WorkbookLoader, role_name: str) -> float | None:
    role = get_role(role_name)
    if not role:
        return None
    block = role.get("excel_block", {})
    ab_row = block.get("ab_row")
    if not ab_row:
        return None
    ws = loader._workbook()["新媒体"]
    val = ws.cell(int(ab_row), 28).value
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def all_role_names() -> list[str]:
    return [r["name"] for r in load_role_registry().get("roles", [])]
