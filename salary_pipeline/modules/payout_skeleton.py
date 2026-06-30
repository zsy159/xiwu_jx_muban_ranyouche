"""Read payout output sheet skeleton (row keys only)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import (
    _log_frame_shape,
    normalize_name,
)


def read_payout_skeleton(
    workbook_path: Path,
    sheet_name: str,
    *,
    data_start_row: int = 3,
) -> pd.DataFrame:
    letters = ["B", "C", "D"]
    usecols = ",".join(letters)
    raw = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        usecols=usecols,
        header=None,
        skiprows=data_start_row - 1,
        engine="openpyxl",
    )
    raw.columns = ["店别", "职务", "姓名"]
    raw["店别"] = raw["店别"].ffill().map(normalize_name)
    raw["职务"] = raw["职务"].map(normalize_name)
    raw["姓名"] = raw["姓名"].map(normalize_name)
    raw["_excel_row"] = range(data_start_row, data_start_row + len(raw))
    raw = raw[raw["姓名"].notna()]
    raw = raw[~raw["姓名"].isin(["小计", "合计", "总计", "空白", "0", 0])]
    return _log_frame_shape(raw.reset_index(drop=True), f"payout skeleton {sheet_name}")
