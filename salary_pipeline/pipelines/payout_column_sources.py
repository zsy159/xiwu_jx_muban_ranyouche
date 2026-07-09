"""发薪表列级数据源标注 — SUMIF 自提成汇总。"""

from __future__ import annotations

from salary_pipeline.pipelines.hub_formula_engine import HUB_COLUMN_MAP
from salary_pipeline.pipelines.xw_payout_formula_engine import (
    PAYOUT_CHANNEL_COLUMN_MAPS,
)

_UNIMPLEMENTED_SOURCE = "需手工填入"

PAYOUT_SOURCE_ROW = 2
PAYOUT_HEADER_ROW = 3
PAYOUT_DATA_START_ROW = 4

# 发薪指标列 → 提成汇总源列（SUMIF 按姓名）
_HUB_SUMIF_BY_PAYOUT: dict[str, str] = {
    "考核量": "F",
    "销售数量": "G",
    "整车绩效": "W",
    "权限结余绩效": "X",
    "附加1绩效": "Y",
    "附加2绩效": "Z",
    "附加3绩效": "AA",
    "附加4绩效": "AB",
    "上户绩效": "AC",
    "专项提成": "AE",
    "其他": "AF",
    "超期绩效": "AO",
    "大客户": "AH",
    "附加": "AG",
    "特殊车型已发扣除": "AF",
    "整车完成考核": "AK",
    "附加1考核": "AM",
    "综合": "AN",
    "活动": "AO",
    "集客考核": "I",
    "提成合计": "AT",
}


def _hub_header_for_letter(letter: str) -> str:
    return HUB_COLUMN_MAP.get(letter.upper(), letter)


def source_annotation_for_payout_column(
    column_name: str,
    *,
    channel: str = "xw",
) -> str:
    """Return source label for one payout metric column."""
    text = str(column_name).strip()
    if text in {"店别", "职务", "姓名"}:
        return "发薪骨架（行键）"

    hub_letter = _HUB_SUMIF_BY_PAYOUT.get(text)
    if hub_letter:
        hub_header = _hub_header_for_letter(hub_letter)
        return f"提成汇总!{hub_letter} {hub_header} SUMIF(D)"

    column_map = PAYOUT_CHANNEL_COLUMN_MAPS.get(channel, {})
    if text in column_map.values():
        return "XwPayoutFormulaEngine"

    return _UNIMPLEMENTED_SOURCE


def build_payout_source_annotation_row(
    headers: list[str] | tuple[str, ...],
    *,
    channel: str = "xw",
) -> list[str]:
    labels = [
        source_annotation_for_payout_column(h, channel=channel) for h in headers
    ]
    for label in labels:
        if "金标准" in label:
            raise ValueError(f"source annotation must not reference 金标准: {label!r}")
    return labels
