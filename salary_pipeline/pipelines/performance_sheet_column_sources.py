"""绩效整理表列级数据源标注 — 导出表头溯源行。"""

from __future__ import annotations

from salary_pipeline.calculators.performance_sheet.from_decoration import (
    DECORATION_PERF_MAP,
)
from salary_pipeline.calculators.performance_sheet.from_insurance import (
    INSURANCE_PERF_MAP,
)
from salary_pipeline.calculators.performance_sheet.from_mortgage import (
    MORTGAGE_PERF_MAP,
)
from salary_pipeline.calculators.performance_sheet.from_vehicle_cost import (
    VEHICLE_COST_INDEX_MAP,
)
from salary_pipeline.pipelines.performance_sheet_builder import IMPLEMENTED_COLUMNS

# 绩效整理表列字母 → 导出溯源标注（源表!列 或 派生/手工说明）
PERF_COLUMN_SOURCE: dict[str, str] = {
    # 骨架键列
    "G": "系统销售毛利!B",
    "O": "系统销售毛利!BD",
    "P": "系统销售毛利!BJ",
    "K": "派生: 默认1; supplement_rows可空",
    # 保险明细 SUMIF(O)
    "AB": "保险明细!BP",
    "AJ": "保险明细!BS",
    "AO": "保险明细!BU",
    "AP": "保险明细!BV",
    # 按揭
    "AK": "按揭明细!BO",
    "AL": "按揭原表!AF+按揭明细!BR",
    # 装饰台账
    "BH": "装饰台账!AK",
    # 整车成本 INDEX/MATCH(O)
    "AW": "整车成本!R",
    "AX": "整车成本!S",
    "AY": "整车成本!T",
    "AZ": "整车成本!U",
    "BA": "整车成本!V",
    "BB": "整车成本!W",
    # 闭包绩效列
    "AG": "派生: 提成标准!F×K",
    "AH": "派生: AA×比例分支",
    "AI": "派生: K=0→L×12%; else (S-U)×12%",
    "AM": "爱车保!BA",
    "AN": "上户提成!H",
    "AS": "置换服务!BB",
    "AQ": "重功超期+活动!N+提成标准!H×K",
    "AR": "二手置换!AE+大客户!R",
    # 延保 / 终端 / 超期
    "AT": "派生: AF分段(-200/0/200)",
    "BC": "终端明细表!P",
    "E": "派生: 系统销售毛利!BA−整车成本!B",
    "AU": "派生: 超期政策×库存天数E",
    # 订单上下文（VIN 关联）
    "H": "系统销售毛利!D",
    "I": "系统销售毛利!E",
    "R": "系统销售毛利!BL",
    "J": "系统销售毛利!F",
    "L": "系统销售毛利!AO",
    "M": "系统销售毛利!BA",
    "N": "系统销售毛利!BC",
    "Q": "系统销售毛利!BK",
    "S": "系统销售毛利!BQ",
    "A": "比对表!A→B",
    "C": "比对表!D→E",
    "D": "派生: A+I渠道规则",
    "F": "工厂购进!CA",
    "B": "常量: 整车订单",
    "T": "派生: O后8位",
    "U": "装饰台账!AR(按G汇总)",
    "V": "系统超额!P",
    "X": "配置: manager_permission_by_vin",
    "Z": "按揭原表!AN",
    "Y": "派生: V+X",
    "W": "派生: (L−S)−Y",
    "AA": "派生: Z≠0→0 else Y−Z",
    # 收入列
    "AC": "按揭明细!Z",
    "AD": "爱车保!K",
    "AE": "上户提成!C",
    "AF": "延保提成!BE",
    # 派生毛利链
    "BE": "系统二手车降价!BE",
    "BF": "派生: SUM(AW:BE)",
    "BG": "派生: L−BF",
    "BI": "派生: S−BH",
    "BJ": "派生: BG+BI",
    "BL": "派生: BJ+SUM(AB:AF)",
    "BM": "派生: BJ/1.13+收入/1.06",
    "BN": "派生: SUM(AG:AT)",
    "AV": "派生: SUM(AG:AU)",
}

# 与 from_* 模块映射表对齐（防漂移）
for _perf, _src in INSURANCE_PERF_MAP.items():
    PERF_COLUMN_SOURCE.setdefault(_perf, f"保险明细!{_src}")
for _perf, _src in MORTGAGE_PERF_MAP.items():
    if _perf == "AL":
        continue
    PERF_COLUMN_SOURCE.setdefault(_perf, f"按揭明细!{_src}")
for _perf, (_key, _src) in DECORATION_PERF_MAP.items():
    PERF_COLUMN_SOURCE.setdefault(_perf, f"装饰台账!{_src}")
for _perf, _src in VEHICLE_COST_INDEX_MAP.items():
    PERF_COLUMN_SOURCE.setdefault(_perf, f"整车成本!{_src}")

_UNIMPLEMENTED_SOURCE = "需手工填入"


def _label_to_letter() -> dict[str, str]:
    from salary_pipeline.pipelines.performance_sheet_export import PERF_COLUMN_LABELS

    return {label: letter for letter, label in PERF_COLUMN_LABELS.items()}


def canonical_perf_letter(letter: str, header: str = "") -> str:
    """Map export (letter, header) to canonical perf column letter."""
    text = str(header).strip()
    canonical = _label_to_letter().get(text)
    if canonical:
        return canonical
    return letter


def is_implemented_perf_column(letter: str, header: str = "") -> bool:
    """True when the column is system-computed (Slice 8), not 需手工填入."""
    return canonical_perf_letter(letter, header) in IMPLEMENTED_COLUMNS


def unimplemented_header_labels(
    column_spec: tuple[tuple[str, str], ...],
) -> frozenset[str]:
    """Chinese headers for columns the builder does not compute yet."""
    return frozenset(
        label
        for letter, label in column_spec
        if not is_implemented_perf_column(letter, label)
    )


def source_annotation_for_column(letter: str, header: str = "") -> str:
    """Return source label for one export column (prefer header semantics over letter)."""
    canonical = canonical_perf_letter(letter, header)
    if canonical in PERF_COLUMN_SOURCE:
        return PERF_COLUMN_SOURCE[canonical]
    if canonical in IMPLEMENTED_COLUMNS:
        return "系统计算"
    return _UNIMPLEMENTED_SOURCE


def source_annotation_for_letter(letter: str) -> str:
    """Return source label for one Excel letter column."""
    return source_annotation_for_column(letter)


def build_source_annotation_row(
    column_spec: tuple[tuple[str, str], ...],
) -> list[str]:
    """One source label per export column, aligned with ``column_spec`` order."""
    labels = [source_annotation_for_column(letter, header) for letter, header in column_spec]
    for label in labels:
        if "金标准" in label:
            raise ValueError(f"source annotation must not reference 金标准: {label!r}")
    return labels


def build_source_annotation_row_for_export(
    export_columns: list[str],
    column_spec: tuple[tuple[str, str], ...],
) -> list[str]:
    """Source labels aligned with ``export_frame.columns`` (includes spec extras)."""
    from salary_pipeline.pipelines.performance_sheet_export import PERF_COLUMN_LABELS

    spec_by_label = {label: (letter, label) for letter, label in column_spec}
    label_to_letter = {label: letter for letter, label in PERF_COLUMN_LABELS.items()}
    labels: list[str] = []
    for col in export_columns:
        col_str = str(col)
        if col_str in spec_by_label:
            letter, header = spec_by_label[col_str]
            labels.append(source_annotation_for_column(letter, header))
        else:
            letter = label_to_letter.get(col_str, col_str)
            labels.append(source_annotation_for_column(letter, col_str))
    for label in labels:
        if "金标准" in label:
            raise ValueError(f"source annotation must not reference 金标准: {label!r}")
    return labels
