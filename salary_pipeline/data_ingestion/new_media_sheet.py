"""Load 新媒体当月算薪子表（形态 B：姓名 → 绩效薪资）。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import (
    WorkbookLoader,
    _log_frame_shape,
    normalize_name,
)
from salary_pipeline.ops.basic import sumif_by_key

NEW_MEDIA_SHEET = "新媒体"
NAME_COL = "Y"
PERF_COL = "AB"  # 子表「绩效薪资」→ hub 整车绩效 W


def load_new_media_performance_frame(loader: WorkbookLoader) -> pd.DataFrame:
    if not loader.has_sheet(NEW_MEDIA_SHEET):
        return pd.DataFrame(columns=[NAME_COL, PERF_COL])
    frame = loader.read_sheet_columns(
        NEW_MEDIA_SHEET,
        {NAME_COL: NAME_COL, PERF_COL: PERF_COL},
        label=f"{NEW_MEDIA_SHEET}!{NAME_COL}:{PERF_COL}",
    )
    frame[NAME_COL] = frame[NAME_COL].map(normalize_name)
    frame[PERF_COL] = pd.to_numeric(frame[PERF_COL], errors="coerce")
    return frame


def lookup_vehicle_performance(
    frame: pd.DataFrame, name: str, *, name_col: str = NAME_COL, perf_col: str = PERF_COL
) -> float:
    """Same semantics as =SUMIF(新媒体!Y:Y, 姓名, 新媒体!AB:AB)."""
    if frame.empty or not name:
        return 0.0
    result = sumif_by_key(frame, name_col, perf_col, normalize_name(name))
    return float(result) if result is not None else 0.0
