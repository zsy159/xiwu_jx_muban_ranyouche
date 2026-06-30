"""Read aftersales anchor sheet skeleton (keys only)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import (
    _log_frame_shape,
    normalize_name,
)


def read_aftersales_skeleton(
    workbook_path: Path,
    sheet_name: str,
    *,
    data_start_row: int = 5,
) -> pd.DataFrame:
    """Load 店别/姓名 keys with exact Excel row numbers for formula evaluation."""
    letters = ["A", "B", "C"]
    usecols = ",".join(letters)
    raw = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        usecols=usecols,
        header=None,
        skiprows=data_start_row - 1,
        engine="openpyxl",
    )
    raw.columns = ["序号", "店别", "姓名"]
    raw["店别"] = raw["店别"].ffill().map(normalize_name)
    raw["姓名"] = raw["姓名"].map(normalize_name)
    raw["_excel_row"] = range(data_start_row, data_start_row + len(raw))
    raw = raw[raw["姓名"].notna()]
    raw = raw[~raw["姓名"].isin(["小计", "合计", "总计", "空白", "0", 0])]
    return _log_frame_shape(raw.reset_index(drop=True), f"skeleton {sheet_name}")
