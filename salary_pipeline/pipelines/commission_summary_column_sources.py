"""提成汇总列级数据源标注 — 导出表头溯源行。"""

from __future__ import annotations

from salary_pipeline.pipelines.commission_summary import SUMMARY_TEMPLATE_COLUMNS

# Hub W–AI 列 → 绩效整理表源列（顾问级 SUMIF/SUMIFS 按 P 匹配姓名 D）
HUB_PERF_SUMIF_MAP: dict[str, str] = {
    "整车绩效": "AG",
    "权限结余绩效": "AH",
    "加装绩效": "AI",
    "保险绩效": "AJ",
    "金融绩效": "AK",
    "爱车宝绩效": "AM",
    "上户绩效": "AN+AS",
    "盈利产品绩效": "AL",
    "延保提成": "AT",
    "特殊车型+指定车型": "AQ",
    "座位险提成": "AO",
    "二手车提成": "AR",
    "玻碎险提成": "AP",
}

# F–P / Q–R 毛利列 → 绩效整理表 SUMIF 值列（键列 P，匹配提成汇总 D）
HUB_MARGIN_SUMIF_MAP: dict[str, str] = {
    "加装额": "S",
    "整车毛利": "BG",
    "加装毛利": "BI",
    "保险毛利": "AB",
    "按揭毛利": "AC",
    "爱车宝毛利": "AD",
    "上户毛利": "AE",
}

# 乘完成率的绩效列（销售顾问：整车/加装/保险；整车门店块用合并完成率 BA）
_HUB_PERF_WITH_COMPLETION = frozenset({"加装绩效", "保险绩效"})
_HUB_VEHICLE_PERF_COMPLETION = "整车绩效"

_UNIMPLEMENTED_SOURCE = "需手工填入"

# 非一线管理（销售管理部/事业部/总经办）行的 W/X/Y/Z 语义列——2026-05 金标准
# 只读验证确认为人工填入固定数值或引用另一张人工维护子表（非绩效整理表 SUMIF
# 公式），登记为 manual 以便导出时对空单元格加灰色手工填入标注（见
# hub_column_rules.yaml 非一线管理 delegate: manual_semantic 注释）。
_NON_FRONTLINE_MANUAL_HEADERS = frozenset(
    {"岗位绩效", "业绩绩效", "业绩绩效1", "业绩绩效2", "新能源专项"}
)


def _perf_sumif_label(header: str, perf_col: str) -> str:
    if "+" in perf_col:
        return f"绩效整理表!{perf_col} SUMIF(P,D)"
    if header == _HUB_VEHICLE_PERF_COMPLETION:
        return (
            "绩效整理表!AG SUMIF(P,D)"
            "×完成率(门店块×BA合并完成率/个人块×H销量完成率，见拓扑)"
        )
    suffix = "×H" if header in _HUB_PERF_WITH_COMPLETION else ""
    return f"绩效整理表!{perf_col} SUMIF(P,D){suffix}"


def _margin_sumif_label(perf_col: str) -> str:
    return f"绩效整理表!{perf_col} SUMIF(P,D)"


# 提成汇总表头 → 导出溯源标注
HUB_COLUMN_SOURCE: dict[str, str] = {
    # 行键 / 骨架
    "序号": "派生: 行号",
    "店别": "SummarySkeleton（行键）",
    "职务": "SummarySkeleton（行键）",
    "姓名": "SummarySkeleton（行键）",
    "人数": "常量: 1",
    # F–P 任务与毛利
    "考核量": "销售任务及完成率!Y SUMIF(C,D)",
    "实际销量": "销售任务及完成率!Z SUMIF(C,D)",
    "销量完成率": "派生: G/F（封顶）",
    "集客达成率": "销售任务及完成率!F INDEX-MATCH(C,D)",
    "加装销量完成率": "派生: J/(G×1500)",
    "保险渗透率": "绩效整理表!K SUMIFS(AB>0,P)/SUMIF(K,P)",
    "整车+加装（毛利）": "派生: M+N",
    "综合毛利": "派生: SUM(M:R)",
    "主营单台毛利": "派生: S/G",
    "综合单台毛利": "派生: T/G",
    # 非一线语义列（physical → semantic 映射）
    "售后总产值": "非一线语义列",
    "配件外销": "非一线语义列",
    "售后产值": "非一线语义列",
    "出库": "非一线语义列",
    "入库": "非一线语义列",
    "台次": "非一线语义列",
    "提成系数": "非一线语义列",
    "提成系数2": "非一线语义列",
    "岗位绩效": "非一线语义列（人工填报，无系统公式）",
    "业绩绩效": "非一线语义列（人工填报，无系统公式）",
    "新能源专项": "非一线语义列（人工填报，无系统公式）",
    "业绩绩效1": "非一线语义列（人工填报，无系统公式）",
    "业绩绩效2": "非一线语义列（人工填报，无系统公式）",
    # 汇总 / 调整
    "提成合计": "派生: SUM(W:AI)+调整",
    "整车完成考核": "邀约专员提成/直营店经理提成(财务)/派生",
    "加装完成考核": "派生: SUM(子行)/手填常量",
    "综合项": "综合表!L SUMIF(B,D)",
    "04月活动": "'重功超期+活动'!X SUMIF(Q,D)",
    "超期": "绩效整理表!AU SUMIF(P,D)",
    "保客考核": "保客考核明细!J SUMIF(E,D)",
    "（已发放奖励）": "综合表!J SUMIF(B,D)",
    "交车支出": _UNIMPLEMENTED_SOURCE,
    "考核小计": "派生: SUM(考核列)",
    "单台提成": _UNIMPLEMENTED_SOURCE,
    "提成毛利占比": _UNIMPLEMENTED_SOURCE,
    "预算单台": _UNIMPLEMENTED_SOURCE,
    "计提单台": _UNIMPLEMENTED_SOURCE,
    "计提金额": _UNIMPLEMENTED_SOURCE,
}

# F–P / Q–R：绩效整理表毛利 SUMIF
for _header, _perf in HUB_MARGIN_SUMIF_MAP.items():
    HUB_COLUMN_SOURCE[_header] = _margin_sumif_label(_perf)

# W–AI：绩效整理表绩效 SUMIF
for _header, _perf in HUB_PERF_SUMIF_MAP.items():
    HUB_COLUMN_SOURCE[_header] = _perf_sumif_label(_header, _perf)


def source_annotation_for_header(header: str) -> str:
    """Return source label for one 提成汇总 column header."""
    text = str(header).strip()
    if text in HUB_COLUMN_SOURCE:
        return HUB_COLUMN_SOURCE[text]
    return _UNIMPLEMENTED_SOURCE


def build_source_annotation_row(headers: list[str] | tuple[str, ...]) -> list[str]:
    """One source label per export column, aligned with header order."""
    labels = [source_annotation_for_header(h) for h in headers]
    for label in labels:
        if "金标准" in label:
            raise ValueError(f"source annotation must not reference 金标准: {label!r}")
    return labels


def manual_column_headers(headers: list[str] | tuple[str, ...]) -> frozenset[str]:
    """Chinese headers for columns that are not system-computed."""
    return frozenset(
        h
        for h in headers
        if source_annotation_for_header(h) == _UNIMPLEMENTED_SOURCE
        or h in _NON_FRONTLINE_MANUAL_HEADERS
    )


def default_export_headers() -> tuple[str, ...]:
    """Column order used by CommissionSummaryBuilder export."""
    return tuple(SUMMARY_TEMPLATE_COLUMNS)
