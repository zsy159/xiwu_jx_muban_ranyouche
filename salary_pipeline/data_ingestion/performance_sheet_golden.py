"""Load 绩效整理表 order skeleton from golden workbook (Phase B transition)."""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name

PERF_SHEET = "绩效整理表"
DATA_START_ROW = 3  # Excel 1-based; row 2 = column headers


def load_performance_order_skeleton(
    loader: WorkbookLoader,
    *,
    key_cols: tuple[str, ...] = ("O", "P", "K", "G"),
) -> pd.DataFrame:
    """
    Order-level keys for 绩效整理表 rebuild.

    Slice 1–3: bootstrap O/P/K from golden sheet while detail columns are re-derived.
    Slice 4+: use ``build_performance_order_skeleton`` (系统销售毛利 + config).
    """
    columns = {c: c for c in key_cols}
    raw = loader.read_sheet_columns(PERF_SHEET, columns, label=f"{PERF_SHEET} skeleton")
    skip = DATA_START_ROW - 1
    frame = raw.iloc[skip:].copy()
    frame = frame.reset_index(drop=True)
    frame["_excel_row"] = range(DATA_START_ROW, DATA_START_ROW + len(frame))

    frame["O"] = frame["O"].map(_normalize_vin)
    if "P" in frame.columns:
        frame["P"] = frame["P"].map(normalize_name)
    if "K" in frame.columns:
        frame["K"] = pd.to_numeric(frame["K"], errors="coerce")

    frame = frame[frame["O"].notna()].reset_index(drop=True)
    return frame


def _normalize_vin(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text in ("VIN码", "nan"):
        return None
    return text
