"""Export system-computed 绩效整理表 to Excel for inspection."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from salary_pipeline.data_ingestion.performance_sheet_golden_scan import (
    load_golden_column_headers,
)
from salary_pipeline.pipelines.performance_sheet_column_sources import (
    build_source_annotation_row_for_export,
    unimplemented_header_labels,
)
from salary_pipeline.utils.excel_format import format_writer_sheet

logger = logging.getLogger(__name__)

# Row 1 title, row 2 source annotations, row 3 headers, row 4+ data
SOURCE_ANNOTATION_ROW = 2
HEADER_ROW = 3
DATA_START_ROW = 4

# 与金标准 row 2 表头对齐（已实现列 + 常用键列）
PERF_COLUMN_LABELS: dict[str, str] = {
    "G": "订单号",
    "O": "VIN码",
    "P": "销售顾问",
    "K": "台数",
    "AG": "单台绩效",
    "AH": "整车超额",
    "AI": "加装绩效",
    "AJ": "保险提成",
    "AK": "按揭提成",
    "AL": "盈利产品",
    "AM": "爱车宝",
    "AN": "上户绩效",
    "AO": "座位险绩效",
    "AP": "玻璃险绩效",
    "AQ": "特殊车型追加绩效",
    "AT": "延保提成",
    "AU": "超期追加",
    "E": "库存天数",
    "A": "指标汇总部门",
    "B": "排放标准",
    "C": "指标汇总车型",
    "D": "渠道",
    "F": "购进公司",
    "H": "车种",
    "I": "销售渠道",
    "J": "车型",
    "L": "订单合计(含税)",
    "M": "结算日期",
    "N": "车主名称",
    "Q": "审核人",
    "R": "部门",
    "S": "精品最低价金额",
    "T": "车架号后8位",
    "U": "不提成精品",
    "V": "整车节约",
    "W": "整车最低售价",
    "Y": "整车实际节约",
    "Z": "盈利性产品按揭权限扣除",
    "AA": "实际整车节约权限",
    "AC": "按揭收入",
    "AD": "爱车宝收入",
    "AE": "上户收入",
    "AF": "延保收入",
    "AV": "合计",
    "BE": "代交车佣金",
    "BF": "整车采购净价",
    "BG": "裸车毛利",
    "BI": "装饰毛利",
    "BJ": "主营业务毛利",
    "BL": "综合毛利",
    "BM": "不含税毛利",
    "BN": "不含安心包提成",
    "AR": "二手车置换",
    "AS": "置换服务",
    "BC": "终端返利",
    "AB": "保险返利收入",
    "BH": "装饰成本",
    "AW": "出厂指导价/扣除降价补差",
    "AX": "提车现返",
    "AY": "合同履约",
    "AZ": "项目金额附加费",
    "BA": "广告返利",
    "BB": "提车奖励当月返",
    "X": "经理权限",
}

EXPORT_COLUMN_ORDER: tuple[str, ...] = (
    "G",
    "O",
    "P",
    "K",
    "AG",
    "AH",
    "AI",
    "AJ",
    "AK",
    "AL",
    "AM",
    "AN",
    "AS",
    "AT",
    "AQ",
    "AU",
    "AR",
    "AO",
    "AP",
    "AB",
    "BH",
    "BC",
    "AW",
    "AX",
    "AY",
    "AZ",
    "BA",
    "BB",
)


def resolve_export_column_spec(
    golden_path: Path | None = None,
) -> tuple[tuple[str, str], ...]:
    """Column order + Chinese headers; prefer golden row 2 when available."""
    if golden_path is not None and golden_path.exists():
        spec = load_golden_column_headers(golden_path)
        if spec:
            return spec
    return tuple((letter, PERF_COLUMN_LABELS[letter]) for letter in EXPORT_COLUMN_ORDER)


def prepare_export_frame(
    frame: pd.DataFrame,
    *,
    column_spec: tuple[tuple[str, str], ...] | None = None,
) -> pd.DataFrame:
    """Order columns and rename to Chinese headers matching golden layout."""
    if frame.empty:
        if column_spec:
            return pd.DataFrame(columns=[label for _, label in column_spec])
        return frame.copy()

    spec = column_spec or tuple(
        (letter, PERF_COLUMN_LABELS.get(letter, letter))
        for letter in EXPORT_COLUMN_ORDER
        if letter in frame.columns
    )
    n = len(frame)
    data: dict[str, pd.Series] = {}
    for letter, label in spec:
        if letter in frame.columns:
            data[label] = frame[letter].reset_index(drop=True)
        else:
            data[label] = pd.Series([pd.NA] * n)
    out = pd.DataFrame(data)
    extras = [
        c
        for c in frame.columns
        if c not in {letter for letter, _ in spec} and not str(c).startswith("_")
    ]
    for col in extras:
        out[_label_column(col)] = frame[col].reset_index(drop=True)
    return out


def _label_column(col: str) -> str:
    label = PERF_COLUMN_LABELS.get(str(col))
    if label:
        return label
    return str(col)


def export_computed_performance_sheet(
    frame: pd.DataFrame,
    output_path: Path,
    *,
    sheet_name: str = "绩效整理表",
    title: str | None = None,
    golden_path: Path | None = None,
) -> Path:
    """Write computed_perf_frame to xlsx (row1 title, row2 sources, row3 headers)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    column_spec = resolve_export_column_spec(golden_path)
    export_frame = prepare_export_frame(frame, column_spec=column_spec)
    header_title = title or f"系统生成-{sheet_name}"
    source_labels = build_source_annotation_row_for_export(
        list(export_frame.columns), column_spec
    )

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        title_df = pd.DataFrame([[header_title]], columns=[header_title])
        title_df.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
            header=False,
            startrow=0,
        )
        source_df = pd.DataFrame([source_labels], columns=list(export_frame.columns))
        source_df.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
            header=False,
            startrow=SOURCE_ANNOTATION_ROW - 1,
        )
        export_frame.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
            startrow=HEADER_ROW - 1,
        )
        format_writer_sheet(
            writer, sheet_name, export_frame.columns, header_row=HEADER_ROW
        )

    logger.info(
        "Exported computed performance sheet -> %s (rows=%s cols=%s, golden_aligned=%s)",
        output_path,
        len(export_frame),
        len(export_frame.columns),
        golden_path is not None and golden_path.exists(),
    )
    return output_path


def unimplemented_column_headers(
    column_spec: tuple[tuple[str, str], ...],
) -> frozenset[str]:
    """Chinese headers for columns the builder does not compute yet."""
    return unimplemented_header_labels(column_spec)
