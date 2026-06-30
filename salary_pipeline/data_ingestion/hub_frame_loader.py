"""Build 提成汇总 column frames for payout SUMIF (computed + golden merge)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from salary_pipeline.data_ingestion.data_loader import (
    _column_sort_key,
    _log_frame_shape,
    normalize_name,
)

# Columns XW提成-发 pulls from 提成汇总 via SUMIF
PAYOUT_HUB_LETTERS = [
    "D",
    "F",
    "G",
    "W",
    "X",
    "Y",
    "Z",
    "AA",
    "AB",
    "AC",
    "AD",
    "AE",
    "AF",
    "AG",
    "AH",
    "AI",
    "AK",
    "AL",
    "AM",
    "AN",
    "AO",
    "AP",
    "AQ",
    "AR",
    "AT",
    "AX",
    "AY",
]

# Only F–P are pipeline-computed at hub parity; W–AR stay golden until W–AI engine closes.
COMPUTED_HUB_OVERRIDE_LETTERS = [
    "F",
    "G",
    "H",
    "I",
    "J",
    "K",
    "L",
    "M",
    "N",
    "O",
    "P",
]


def _col_to_index(letter: str) -> int:
    n = 0
    for ch in letter.upper():
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _sheet_max_column(workbook_path: Path, sheet_name: str) -> int:
    wb = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        return int(wb[sheet_name].max_column or 0)
    finally:
        wb.close()


def _letters_within_bounds(
    workbook_path: Path, sheet_name: str, letters: list[str]
) -> list[str]:
    max_col = _sheet_max_column(workbook_path, sheet_name)
    return [letter for letter in letters if _col_to_index(letter) + 1 <= max_col]


def read_hub_columns_by_letter(
    workbook_path: Path,
    sheet_name: str = "提成汇总",
    letters: list[str] | None = None,
    *,
    data_start_row: int = 3,
) -> pd.DataFrame:
    """Load hub metrics by Excel column letter (values, not formulas)."""
    letters = letters or PAYOUT_HUB_LETTERS
    available = _letters_within_bounds(workbook_path, sheet_name, letters)
    if not available:
        return pd.DataFrame()

    usecols = ",".join(sorted(set(available), key=_column_sort_key))
    raw = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        usecols=usecols,
        header=None,
        skiprows=data_start_row - 1,
        engine="openpyxl",
    )
    letter_order = sorted(set(available), key=_column_sort_key)
    letter_to_pos = {letter.upper(): idx for idx, letter in enumerate(letter_order)}
    out = pd.DataFrame()
    for letter in letter_order:
        out[letter] = raw.iloc[:, letter_to_pos[letter.upper()]]
    if "D" in out.columns:
        out["D"] = out["D"].map(normalize_name)
    for letter in letter_order:
        if letter != "D":
            out[letter] = pd.to_numeric(out[letter], errors="coerce")
    return _log_frame_shape(out, f"hub columns {workbook_path.name}!{sheet_name}")


def _merge_hub_by_name_key(base: pd.DataFrame, override: pd.DataFrame) -> pd.DataFrame:
    """Override hub metric columns by 姓名 (column D), not row index."""
    if override.empty or "D" not in override.columns:
        return base
    out = base.copy()
    keyed = override.copy()
    keyed["_dkey"] = keyed["D"].map(normalize_name)
    lookup = keyed.drop_duplicates("_dkey", keep="last").set_index("_dkey")
    dkeys = out["D"].map(normalize_name)
    for col in override.columns:
        if col == "D" or col not in lookup.columns:
            continue
        mapped = dkeys.map(lookup[col])
        mask = mapped.notna()
        if mask.any():
            out.loc[mask, col] = mapped[mask]
    return out


def build_hub_sumif_frame(
    golden_workbook: Path,
    *,
    computed_workbook: Path | None = None,
    sheet_name: str = "提成汇总",
    letters: list[str] | None = None,
    data_start_row: int = 3,
) -> pd.DataFrame:
    """
    Merge hub columns for payout SUMIF.

    - Base layer: golden workbook (full W–AR block)
    - Override: computed 提成汇总.xlsx where columns exist (typically F–P)
    """
    letters = letters or PAYOUT_HUB_LETTERS
    frame = read_hub_columns_by_letter(
        golden_workbook,
        sheet_name,
        letters,
        data_start_row=data_start_row,
    )
    if computed_workbook is None or not computed_workbook.exists():
        return frame

    computed = read_hub_columns_by_letter(
        computed_workbook,
        sheet_name,
        ["D", *COMPUTED_HUB_OVERRIDE_LETTERS],
        data_start_row=data_start_row,
    )
    return _merge_hub_by_name_key(frame, computed)
