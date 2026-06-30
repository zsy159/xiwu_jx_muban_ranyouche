from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from salary_pipeline.modules.base import SUMMARY_KEY_COLUMNS
from salary_pipeline.paths import CONFIG_DIR, resolve_project_path

logger = logging.getLogger(__name__)

EXCEL_COL_RE = re.compile(r"^([A-Z]{1,3})(\d+)$", re.IGNORECASE)


def normalize_name(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def normalize_header(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\n", "").strip()
    return text or None


def read_golden_summary_sheet(
    workbook_path: Path,
    sheet_name: str,
    *,
    header_row: int = 2,
    data_start_row: int | None = None,
) -> pd.DataFrame:
    """Read the reference 提成汇总 sheet (computed values, not formulas)."""
    df = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        header=header_row - 1,
        engine="openpyxl",
    )
    df.columns = [normalize_header(c) for c in df.columns]
    if data_start_row and data_start_row > header_row + 1:
        skip = data_start_row - header_row - 2
        if skip > 0:
            df = df.iloc[skip:].reset_index(drop=True)
    df = _clean_summary_frame(df)
    logger.info(
        "Loaded golden summary %s!%s shape=%s",
        workbook_path.name,
        sheet_name,
        df.shape,
    )
    return df


def read_aftersales_metric_frame(
    workbook_path: Path,
    sheet_name: str,
    column_map: dict[str, str],
    *,
    data_start_row: int = 5,
) -> pd.DataFrame:
    """Read aftersales anchor metrics by Excel column letters (avoids merged-header ambiguity)."""
    key_letters = {"B": "店别", "C": "姓名"}
    all_letters = {**key_letters, **{letter: name for letter, name in column_map.items()}}
    letters = sorted(all_letters.keys(), key=_column_sort_key)
    usecols = ",".join(letters)
    raw = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        usecols=usecols,
        header=None,
        skiprows=data_start_row - 1,
        engine="openpyxl",
    )
    letter_to_pos = {letter.upper(): idx for idx, letter in enumerate(letters)}
    out = pd.DataFrame()
    for letter, name in all_letters.items():
        out[name] = raw.iloc[:, letter_to_pos[letter.upper()]]
    out["店别"] = out["店别"].ffill().map(normalize_name)
    out["姓名"] = out["姓名"].map(normalize_name)
    out = out[out["姓名"].notna()]
    out = out[~out["姓名"].isin(["小计", "空白", "0", 0])]
    return _log_frame_shape(out.reset_index(drop=True), f"aftersales metrics {sheet_name}")


def read_computed_aftersales_excel(
    workbook_path: Path,
    sheet_name: str,
    column_map: dict[str, str],
) -> pd.DataFrame:
    """Read pipeline-exported aftersales xlsx (header at row 4 / startrow=3)."""
    df = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        header=3,
        engine="openpyxl",
    )
    df.columns = [normalize_header(c) for c in df.columns]
    if "姓名" not in df.columns and "姓 名" in df.columns:
        df = df.rename(columns={"姓 名": "姓名"})
    if "店别" not in df.columns and "部门" in df.columns:
        df["店别"] = df["部门"].ffill().map(normalize_name)
    df["姓名"] = df["姓名"].map(normalize_name)
    return filter_comparable_rows(_clean_summary_frame(df))


def read_payout_metric_frame(
    workbook_path: Path,
    sheet_name: str,
    column_map: dict[str, str],
    *,
    data_start_row: int = 3,
) -> pd.DataFrame:
    """Read payout output metrics by Excel column letters."""
    key_letters = {"B": "店别", "C": "职务", "D": "姓名"}
    all_letters = {**key_letters, **{letter: name for letter, name in column_map.items()}}
    letters = sorted(all_letters.keys(), key=_column_sort_key)
    usecols = ",".join(letters)
    raw = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        usecols=usecols,
        header=None,
        skiprows=data_start_row - 1,
        engine="openpyxl",
    )
    letter_to_pos = {letter.upper(): idx for idx, letter in enumerate(letters)}
    out = pd.DataFrame()
    for letter, name in all_letters.items():
        out[name] = raw.iloc[:, letter_to_pos[letter.upper()]]
    out["店别"] = out["店别"].ffill().map(normalize_name)
    out["职务"] = out["职务"].map(normalize_name)
    out["姓名"] = out["姓名"].map(normalize_name)
    out = out[out["姓名"].notna()]
    out = out[~out["姓名"].isin(["小计", "空白", "0", 0])]
    return _log_frame_shape(out.reset_index(drop=True), f"payout metrics {sheet_name}")


def read_computed_payout_excel(
    workbook_path: Path,
    sheet_name: str,
) -> pd.DataFrame:
    """Read pipeline-exported payout xlsx (header at row 3 / startrow=2)."""
    df = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        header=2,
        engine="openpyxl",
    )
    df.columns = [normalize_header(c) for c in df.columns]
    return filter_comparable_rows(_clean_summary_frame(df))


def read_computed_summary_excel(
    workbook_path: Path,
    sheet_name: str = "提成汇总",
    *,
    header_row: int = 2,
    data_start_row: int = 3,
) -> pd.DataFrame:
    """Read pipeline-exported 提成汇总.xlsx (default header at row 2)."""
    return read_golden_summary_sheet(
        workbook_path,
        sheet_name,
        header_row=header_row,
        data_start_row=data_start_row,
    )


def filter_comparable_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Exclude subtotal / placeholder rows from parity comparison."""
    if df.empty:
        return df
    out = df.copy()
    if "姓名" in out.columns:
        out = out[out["姓名"].notna()]
        out = out[~out["姓名"].isin(["空白", "0", "小计", 0])]
    if "职务" in out.columns:
        out = out[out["职务"].notna()]
        out = out[~out["职务"].astype(str).isin(["小计", "0"])]
    if "序号" in out.columns:
        out = out[out["序号"].notna()]
    return out.reset_index(drop=True)


def filter_skeleton_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows needed for hub formula evaluation (SUM ranges, SUMIF keys).

    Unlike ``filter_comparable_rows``, keeps rows with blank 序号 such as
    duplicate 区域顾问 entries (余才万2 / 余才万5) that still participate in
    store-block ``SUM(G*:G*)`` subtotals.
    """
    if df.empty:
        return df
    out = df.copy()
    if "姓名" in out.columns:
        out = out[out["姓名"].notna()]
        out = out[~out["姓名"].isin(["空白", "0", "小计", 0])]
    if "职务" in out.columns:
        out = out[out["职务"].notna()]
        out = out[~out["职务"].astype(str).isin(["小计", "0"])]
    return out.reset_index(drop=True)


def _clean_summary_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "店别" in out.columns:
        out["店别"] = out["店别"].ffill()
    if "姓名" in out.columns:
        out["姓名"] = out["姓名"].map(normalize_name)
    for col in ("店别", "职务"):
        if col in out.columns:
            out[col] = out[col].map(normalize_name)
    return out


def summary_frame_from_builder(df: pd.DataFrame) -> pd.DataFrame:
    return _clean_summary_frame(df)


def load_month_config(config_dir: Path | None = None) -> dict[str, Any]:
    path = (config_dir or CONFIG_DIR) / "month.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class WorkbookLoader:
    """Read registered sheets from the monthly sales workbook."""

    def __init__(self, workbook_path: Path) -> None:
        self.workbook_path = Path(workbook_path)
        self._wb = None
        self._cell_cache: dict[tuple[str, str], Any] = {}
        self._raw_sheet_cache: dict[str, pd.DataFrame] = {}

    def _workbook(self):
        if self._wb is None:
            self._wb = load_workbook(
                self.workbook_path, read_only=True, data_only=True
            )
        return self._wb

    def read_cell_value(self, sheet_name: str, address: str) -> Any:
        address = address.strip().upper()
        cache_key = (sheet_name, address)
        if cache_key in self._cell_cache:
            return self._cell_cache[cache_key]
        match = EXCEL_COL_RE.match(address)
        if not match:
            raise ValueError(f"Invalid cell address: {address}")
        col_letter, row = match.group(1).upper(), int(match.group(2))
        ws = self._workbook()[sheet_name]
        value = ws.cell(
            row=row, column=column_index_from_string(col_letter)
        ).value
        self._cell_cache[cache_key] = value
        return value

    def _read_raw_sheet(self, sheet_name: str) -> pd.DataFrame:
        """Load a full sheet once per loader instance (shared across column slices)."""
        if sheet_name not in self._raw_sheet_cache:
            logger.debug("Caching raw sheet %s from %s", sheet_name, self.workbook_path.name)
            self._raw_sheet_cache[sheet_name] = pd.read_excel(
                self.workbook_path,
                sheet_name=sheet_name,
                header=None,
                engine="openpyxl",
            )
        return self._raw_sheet_cache[sheet_name]

    def read_sheet_columns(
        self,
        sheet_name: str,
        columns: dict[str, str],
        *,
        label: str | None = None,
    ) -> pd.DataFrame:
        """
        Load selected columns by Excel letter.

        columns: logical_name -> column letter (e.g. {"姓名": "C", "考核量": "Y"})
        """
        raw = self._read_raw_sheet(sheet_name)
        out = pd.DataFrame()
        for logical_name, letter in columns.items():
            col_idx = column_index_from_string(letter.upper()) - 1
            out[logical_name] = raw.iloc[:, col_idx]
        out = _log_frame_shape(out, label or f"{self.workbook_path.name}!{sheet_name}")
        return out

    def read_sales_task_sheet(self) -> pd.DataFrame:
        frame = self.read_sheet_columns(
            "销售任务及完成率",
            {"姓名": "C", "考核量": "Y", "实际销量": "Z"},
            label="销售任务及完成率",
        )
        frame["姓名"] = frame["姓名"].map(normalize_name)
        frame["考核量"] = pd.to_numeric(frame["考核量"], errors="coerce")
        frame["实际销量"] = pd.to_numeric(frame["实际销量"], errors="coerce")
        return frame


def build_workbook_loader(context: dict[str, Any]) -> WorkbookLoader:
    config = context["month_config"]
    sales_path = resolve_project_path(config["workbooks"]["sales"])
    return WorkbookLoader(sales_path)


def read_summary_skeleton_keys(
    workbook_path: Path,
    sheet_name: str = "提成汇总",
    *,
    header_row: int = 2,
    data_start_row: int = 3,
) -> pd.DataFrame:
    """Iteration-1 bootstrap: row keys and Excel row numbers only (no metric columns)."""
    golden = read_golden_summary_sheet(
        workbook_path,
        sheet_name,
        header_row=header_row,
        data_start_row=data_start_row,
    )
    golden = summary_frame_from_builder(golden)
    golden["_excel_row"] = range(data_start_row, data_start_row + len(golden))
    golden = filter_skeleton_rows(golden)
    skeleton = golden[[*SUMMARY_KEY_COLUMNS, "_excel_row"]].copy()
    return _log_frame_shape(skeleton, f"skeleton keys {sheet_name}")


def _log_frame_shape(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    logger.info("Loaded %s shape=%s", label, frame.shape)
    return frame


def _column_sort_key(letter: str) -> int:
    letter = letter.upper()
    value = 0
    for char in letter:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value
