"""财务调账页 helper — load / save 绩效整理表-财务确认版."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from salary_pipeline.pipelines.performance_sheet_export import (
    PERF_COLUMN_LABELS,
    export_computed_performance_sheet,
)
from salary_pipeline.pipelines.performance_sheet_paths import (
    CONFIRMED_PERF_FILENAME,
    SYSTEM_PERF_FILENAME,
    dataframe_to_letter_columns,
    load_performance_sheet_frame,
    resolve_confirmed_performance_sheet_path,
    resolve_performance_sheet_path,
    resolve_system_performance_sheet_path,
)


def _display_labels_for_editor(letter_frame: pd.DataFrame) -> pd.DataFrame:
    """Map letter keys to Chinese headers for Streamlit data_editor."""
    if letter_frame.empty:
        return letter_frame.copy()
    rename = {
        col: PERF_COLUMN_LABELS.get(str(col).upper(), str(col))
        for col in letter_frame.columns
    }
    return letter_frame.rename(columns=rename)


def load_performance_sheet_for_edit(
    month_config: dict[str, Any],
) -> tuple[pd.DataFrame | None, Path | None, str]:
    """
    Load performance sheet for Streamlit data_editor.

    Returns (dataframe, path_loaded, source_label).
  ``source_label`` is ``confirmed`` | ``system`` | ``missing``.
    """
    system_path = resolve_system_performance_sheet_path(month_config)
    confirmed_path = resolve_confirmed_performance_sheet_path(month_config)

    if confirmed_path.exists():
        letter_frame = load_performance_sheet_frame(confirmed_path)
        if not letter_frame.empty:
            return (
                _display_labels_for_editor(letter_frame),
                confirmed_path,
                "confirmed",
            )

    if system_path.exists():
        letter_frame = load_performance_sheet_frame(system_path)
        if not letter_frame.empty:
            return (
                _display_labels_for_editor(letter_frame),
                system_path,
                "system",
            )

    if confirmed_path.exists() or system_path.exists():
        return pd.DataFrame(), confirmed_path if confirmed_path.exists() else system_path, "missing"

    return None, None, "missing"


def save_confirmed_performance_sheet(
    month_config: dict[str, Any],
    edited_df: pd.DataFrame,
) -> Path:
    """Write finance edits to 绩效整理表-财务确认版.xlsx only."""
    dest = resolve_confirmed_performance_sheet_path(month_config)
    month = month_config.get("month", "")
    title = f"{month} 销售绩效整理表（财务确认版）" if month else "财务确认版-绩效整理表"
    letter_frame = dataframe_to_letter_columns(edited_df)
    export_computed_performance_sheet(letter_frame, dest, title=title)
    return dest


def describe_loaded_source(source_label: str, path: Path | None) -> str:
    if source_label == "confirmed":
        return f"财务确认版 · `{path.name if path else CONFIRMED_PERF_FILENAME}`"
    if source_label == "system":
        return f"系统生成（只读底稿）· `{path.name if path else SYSTEM_PERF_FILENAME}`"
    return "未找到绩效整理表"


def resolved_path_for_display(month_config: dict[str, Any]) -> Path:
    """Path that downstream computation would read (for UI caption)."""
    return resolve_performance_sheet_path(month_config)


def frame_from_resolved_path(path: Path) -> pd.DataFrame:
    """Test helper: letter-column frame from a resolved perf xlsx."""
    return load_performance_sheet_frame(path)


_PERF_EDITOR_COL_WIDTH = 132


def build_perf_editor_column_config(df: pd.DataFrame) -> dict[str, Any]:
    """Wide perf sheet column widths for st.data_editor horizontal scroll."""
    config: dict[str, Any] = {}
    for col in df.columns:
        label = str(col)
        if pd.api.types.is_numeric_dtype(df[col]):
            config[col] = st.column_config.NumberColumn(label, width=_PERF_EDITOR_COL_WIDTH)
        else:
            config[col] = st.column_config.TextColumn(label, width=_PERF_EDITOR_COL_WIDTH)
    return config
