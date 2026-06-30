"""Shared openpyxl number formats for pipeline Excel exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Protocol

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from salary_pipeline.data_ingestion.data_loader import normalize_header, normalize_name

TWO_DECIMAL_FORMAT = "#,##0.00"

# Light amber — visible against white, keeps black text readable.
PARITY_MISMATCH_FILL = PatternFill(
    start_color="FFFFEB9C",
    end_color="FFFFEB9C",
    fill_type="solid",
)
PARITY_MISMATCH_FILL_RGB = "FFFFEB9C"
PARITY_MISMATCH_FILL_COMMENT = "金标准与系统数值不一致"

# Light blue — formula cells with manual inputs / parity-deferred (wa_parity_deferred).
MANUAL_DEFERRED_FILL = PatternFill(
    start_color="FFBDD7EE",
    end_color="FFBDD7EE",
    fill_type="solid",
)
MANUAL_DEFERRED_FILL_RGB = "FFBDD7EE"
MANUAL_DEFERRED_FILL_COMMENT = "公式含手工录入，对账暂缓"

# Light gray — golden 提成汇总 cells with no formula (direct static value).
GOLDEN_STATIC_FILL = PatternFill(
    start_color="FFD9D9D9",
    end_color="FFD9D9D9",
    fill_type="solid",
)
GOLDEN_STATIC_FILL_RGB = "FFD9D9D9"

STATIC_FILL_COMMENT = "金标准直接填数，无公式"

_HIGHLIGHT_FILL_RGBS = frozenset(
    {MANUAL_DEFERRED_FILL_RGB, GOLDEN_STATIC_FILL_RGB}
)

# Light orange — formula anomaly / 公式形态异常（区别于琥珀 mismatch、蓝色 deferred）
FORMULA_ANOMALY_FILL = PatternFill(
    start_color="FFFCE4D6",
    end_color="FFFCE4D6",
    fill_type="solid",
)
FORMULA_ANOMALY_FILL_RGB = "FFFCE4D6"

_COMMISSION_SUMMARY_LEGEND_ITEMS: tuple[tuple[PatternFill, str], ...] = (
    (GOLDEN_STATIC_FILL, "浅灰 #D9D9D9：金标准直接填数"),
    (MANUAL_DEFERRED_FILL, "浅蓝 #BDD7EE：公式含手工"),
    (PARITY_MISMATCH_FILL, "琥珀 #FFEB9C：数值不一致"),
    (FORMULA_ANOMALY_FILL, "浅橙 #FCE4D6：公式形态异常"),
)


class ParityMismatchCell(Protocol):
    join_values: tuple[tuple[str, Any], ...]
    column: str
    golden_value: float | None
    computed_value: float | None


class CommissionSummaryAnnotation(Protocol):
    name: str
    column: str

    def comment_text(self) -> str: ...

# Count / ID columns — leave default display (not forced to two decimals).
INTEGER_DISPLAY_HEADERS: frozenset[str] = frozenset(
    {
        "序号",
        "人数",
        "考核量",
        "实际销量",
        "台数",
        "订单号",
    }
)


def apply_two_decimal_format(
    worksheet: Worksheet,
    columns: Iterable[str],
    *,
    header_row: int,
    integer_columns: frozenset[str] | None = None,
) -> None:
    """Apply ``#,##0.00`` to numeric data cells in listed columns."""
    skip = integer_columns if integer_columns is not None else INTEGER_DISPLAY_HEADERS
    col_names = list(columns)
    first_data_row = header_row + 1

    for col_idx, name in enumerate(col_names, start=1):
        if name in skip:
            continue
        for row_idx in range(first_data_row, worksheet.max_row + 1):
            cell = worksheet.cell(row=row_idx, column=col_idx)
            value = cell.value
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                cell.number_format = TWO_DECIMAL_FORMAT


def format_writer_sheet(
    writer,
    sheet_name: str,
    columns: Iterable[str],
    *,
    header_row: int,
    integer_columns: frozenset[str] | None = None,
) -> None:
    """Format numeric cells on a sheet written via ``pd.ExcelWriter``."""
    apply_two_decimal_format(
        writer.sheets[sheet_name],
        columns,
        header_row=header_row,
        integer_columns=integer_columns,
    )


def _header_column_map(
    worksheet: Worksheet, header_row: int
) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for col_idx in range(1, worksheet.max_column + 1):
        header = normalize_header(worksheet.cell(row=header_row, column=col_idx).value)
        if header:
            mapping[header] = col_idx
    return mapping


def _join_key_tuple(
    worksheet: Worksheet,
    row_idx: int,
    join_keys: list[str],
    col_map: dict[str, int],
) -> tuple[tuple[str, Any], ...]:
    values: list[tuple[str, Any]] = []
    for key in join_keys:
        col_idx = col_map.get(key)
        if col_idx is None:
            values.append((key, None))
            continue
        raw = worksheet.cell(row=row_idx, column=col_idx).value
        values.append((key, normalize_name(raw)))
    return tuple(values)


def _build_excel_row_index(
    worksheet: Worksheet,
    join_keys: list[str],
    *,
    header_row: int,
    data_start_row: int,
) -> dict[tuple[tuple[str, Any], ...], int]:
    col_map = _header_column_map(worksheet, header_row)
    index: dict[tuple[tuple[str, Any], ...], int] = {}
    for row_idx in range(data_start_row, worksheet.max_row + 1):
        key = _join_key_tuple(worksheet, row_idx, join_keys, col_map)
        if any(value is None for _, value in key):
            continue
        index[key] = row_idx
    return index


def _mismatch_comment(mismatch: ParityMismatchCell) -> str:
    lines = [PARITY_MISMATCH_FILL_COMMENT]
    golden = mismatch.golden_value
    computed = mismatch.computed_value
    if golden is not None and computed is not None:
        diff = computed - golden
        lines.append(f"金标准={golden:g}  系统={computed:g}  差={diff:+g}")
    return "\n".join(lines)


def add_commission_summary_color_legend(
    workbook_path: Path,
    sheet_name: str,
    *,
    insert_at_row: int = 2,
) -> None:
    """Insert a row of color swatches and Chinese labels for reconcile highlighting."""
    wb = load_workbook(workbook_path)
    if sheet_name not in wb.sheetnames:
        raise KeyError(f"sheet {sheet_name!r} not found in {workbook_path}")
    ws = wb[sheet_name]
    ws.insert_rows(insert_at_row)
    col = 1
    for fill, label in _COMMISSION_SUMMARY_LEGEND_ITEMS:
        swatch = ws.cell(row=insert_at_row, column=col, value="")
        swatch.fill = fill
        ws.cell(row=insert_at_row, column=col + 1, value=label)
        col += 2
    wb.save(workbook_path)


def highlight_commission_summary_mismatches(
    workbook_path: Path,
    sheet_name: str,
    mismatches: Iterable[ParityMismatchCell],
    join_keys: list[str],
    compare_columns: Iterable[str],
    *,
    header_row: int = 2,
    data_start_row: int = 3,
) -> int:
    """Highlight parity mismatch cells in an exported 提成汇总 workbook."""
    mismatch_list = list(mismatches)
    compare_col_set = set(compare_columns)

    wb = load_workbook(workbook_path)
    if sheet_name not in wb.sheetnames:
        raise KeyError(f"sheet {sheet_name!r} not found in {workbook_path}")
    ws = wb[sheet_name]
    col_map = _header_column_map(ws, header_row)
    row_index = _build_excel_row_index(
        ws, join_keys, header_row=header_row, data_start_row=data_start_row
    )

    for row_idx in range(data_start_row, ws.max_row + 1):
        for col_name in compare_col_set:
            col_idx = col_map.get(col_name)
            if col_idx is None:
                continue
            cell = ws.cell(row=row_idx, column=col_idx)
            if (
                cell.fill
                and cell.fill.fill_type == "solid"
                and getattr(cell.fill.start_color, "rgb", None) == PARITY_MISMATCH_FILL_RGB
            ):
                cell.fill = PatternFill()

    highlighted = 0
    for mismatch in mismatch_list:
        row_idx = row_index.get(mismatch.join_values)
        col_idx = col_map.get(mismatch.column)
        if row_idx is None or col_idx is None:
            continue
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.fill = PARITY_MISMATCH_FILL
        cell.comment = Comment(_mismatch_comment(mismatch), "对账")
        highlighted += 1

    wb.save(workbook_path)
    return highlighted


def highlight_commission_summary_deferred_cells(
    workbook_path: Path,
    sheet_name: str,
    deferred_cells: dict[str, frozenset[str]],
    *,
    static_cells: dict[tuple[str, str], frozenset[str]] | None = None,
    role_title: str = "销售顾问",
    header_row: int = 2,
    data_start_row: int = 3,
    static_comment: str = STATIC_FILL_COMMENT,
    deferred_comment: str = MANUAL_DEFERRED_FILL_COMMENT,
) -> int:
    """Highlight parity-deferred and golden static (直接填数) cells in 提成汇总.

    Rows are matched by 姓名 + 职务 (not 店别). ``deferred_cells`` is keyed by 姓名
    and filtered to ``role_title``; ``static_cells`` is keyed by (姓名, 职务).

    Fill colors: gray = 金标准直填（无公式）；blue = 公式含手工（wa_parity_deferred、二网 AH、topology 尾项常数）。
    Deferred wins when a cell appears in both maps.
    """
    static_cells = static_cells or {}
    if not deferred_cells and not static_cells:
        return 0

    wb = load_workbook(workbook_path)
    if sheet_name not in wb.sheetnames:
        raise KeyError(f"sheet {sheet_name!r} not found in {workbook_path}")
    ws = wb[sheet_name]
    col_map = _header_column_map(ws, header_row)

    name_col = col_map.get("姓名")
    role_col = col_map.get("职务")
    if name_col is None or role_col is None:
        wb.save(workbook_path)
        return 0

    deferred_columns = {col for cols in deferred_cells.values() for col in cols}
    static_columns = {col for cols in static_cells.values() for col in cols}
    highlight_columns = deferred_columns | static_columns

    for row_idx in range(data_start_row, ws.max_row + 1):
        for col_name in highlight_columns:
            col_idx = col_map.get(col_name)
            if col_idx is None:
                continue
            cell = ws.cell(row=row_idx, column=col_idx)
            if (
                cell.fill
                and cell.fill.fill_type == "solid"
                and getattr(cell.fill.start_color, "rgb", None) in _HIGHLIGHT_FILL_RGBS
            ):
                cell.fill = PatternFill()

    highlighted = 0
    for row_idx in range(data_start_row, ws.max_row + 1):
        name = normalize_name(ws.cell(row=row_idx, column=name_col).value)
        role = normalize_name(ws.cell(row=row_idx, column=role_col).value) or ""
        if name is None:
            continue

        deferred_cols: set[str] = set()
        if role == role_title:
            deferred_cols.update(deferred_cells.get(name, frozenset()))
        static_cols = set(static_cells.get((name, role), frozenset()))
        static_only = static_cols - deferred_cols

        for col_name in static_only:
            col_idx = col_map.get(col_name)
            if col_idx is None:
                continue
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = GOLDEN_STATIC_FILL
            cell.comment = Comment(static_comment, "对账")
            highlighted += 1

        for col_name in deferred_cols:
            col_idx = col_map.get(col_name)
            if col_idx is None:
                continue
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = MANUAL_DEFERRED_FILL
            cell.comment = Comment(deferred_comment, "对账")
            highlighted += 1

    wb.save(workbook_path)
    return highlighted


def add_commission_summary_annotations(
    workbook_path: Path,
    sheet_name: str,
    annotations: Iterable[CommissionSummaryAnnotation],
    *,
    role_title: str = "销售顾问",
    header_row: int = 2,
    data_start_row: int = 3,
) -> int:
    """Highlight formula-anomaly cells and attach Excel comments (批注) in 提成汇总."""
    ann_list = list(annotations)
    if not ann_list:
        return 0

    wb = load_workbook(workbook_path)
    if sheet_name not in wb.sheetnames:
        raise KeyError(f"sheet {sheet_name!r} not found in {workbook_path}")
    ws = wb[sheet_name]
    col_map = _header_column_map(ws, header_row)

    name_col = col_map.get("姓名")
    role_col = col_map.get("职务")
    if name_col is None or role_col is None:
        wb.save(workbook_path)
        return 0

    annotated_columns = {ann.column for ann in ann_list}

    for row_idx in range(data_start_row, ws.max_row + 1):
        for col_name in annotated_columns:
            col_idx = col_map.get(col_name)
            if col_idx is None:
                continue
            cell = ws.cell(row=row_idx, column=col_idx)
            if (
                cell.fill
                and cell.fill.fill_type == "solid"
                and getattr(cell.fill.start_color, "rgb", None) == FORMULA_ANOMALY_FILL_RGB
            ):
                cell.fill = PatternFill()
            if cell.comment is not None:
                cell.comment = None

    by_name: dict[str, list[CommissionSummaryAnnotation]] = {}
    for ann in ann_list:
        by_name.setdefault(ann.name, []).append(ann)

    applied = 0
    for row_idx in range(data_start_row, ws.max_row + 1):
        name = normalize_name(ws.cell(row=row_idx, column=name_col).value)
        role = normalize_name(ws.cell(row=row_idx, column=role_col).value)
        if name is None or role != role_title:
            continue
        for ann in by_name.get(name, []):
            col_idx = col_map.get(ann.column)
            if col_idx is None:
                continue
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = FORMULA_ANOMALY_FILL
            cell.comment = Comment(ann.comment_text(), "对账")
            applied += 1

    wb.save(workbook_path)
    return applied
