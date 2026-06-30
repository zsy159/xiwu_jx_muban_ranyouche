"""Export system-computed 绩效整理表 to Excel for inspection."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from salary_pipeline.utils.excel_format import format_writer_sheet

logger = logging.getLogger(__name__)

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
    "AU": "超期追加",
    "E": "库存天数",
    "AR": "二手车置换",
    "AS": "置换服务",
    "AT": "延保提成",
    "BC": "终端返利",
    "AB": "保险返利收入",
    "BH": "装饰成本",
    "AW": "出厂指导价/扣除降价补差",
    "AX": "提车现返",
    "AY": "合同履约",
    "AZ": "项目金额附加费",
    "BA": "广告返利",
    "BB": "提车奖励当月返",
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


def prepare_export_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Order columns and rename to Chinese headers for readability."""
    if frame.empty:
        return frame.copy()

    ordered = [c for c in EXPORT_COLUMN_ORDER if c in frame.columns]
    extras = [
        c
        for c in frame.columns
        if c not in ordered and not str(c).startswith("_")
    ]
    cols = ordered + extras
    out = frame[cols].copy()
    out.columns = [_label_column(c) for c in cols]
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
) -> Path:
    """Write computed_perf_frame to xlsx (row1 title, row2 headers, row3+ data)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    export_frame = prepare_export_frame(frame)
    header_title = title or f"系统生成-{sheet_name}"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        title_df = pd.DataFrame([[header_title]], columns=[header_title])
        title_df.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
            header=False,
            startrow=0,
        )
        export_frame.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
            startrow=1,
        )
        format_writer_sheet(
            writer, sheet_name, export_frame.columns, header_row=2
        )

    logger.info(
        "Exported computed performance sheet -> %s (rows=%s cols=%s)",
        output_path,
        len(export_frame),
        len(export_frame.columns),
    )
    return output_path
