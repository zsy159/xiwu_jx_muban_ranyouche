"""Load base-pay and deduction sheets for payout merge."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name


def load_basic_pay_frame(
    loader: WorkbookLoader,
    sheet_name: str = "西物基本",
    *,
    name_col: str = "C",
    value_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Load 西物基本 / 超市基本 columns used by payout SUMIF patterns."""
    cols = value_cols or ["P", "AB", "AC", "AG"]
    letters = [name_col, *cols]
    frame = loader.read_sheet_columns(
        sheet_name,
        {letter: letter for letter in letters},
        label=sheet_name,
    )
    frame[name_col] = frame[name_col].map(normalize_name)
    for letter in cols:
        frame[letter] = pd.to_numeric(frame[letter], errors="coerce")
    return frame
