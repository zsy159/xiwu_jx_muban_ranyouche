"""User overrides for generated 提成汇总 / 绩效整理表 (JSON persistence)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from salary_pipeline.modules.base import SUMMARY_KEY_COLUMNS

DEFAULT_SHEETS = ("提成汇总", "绩效整理表")


def overrides_path(staging_or_output_dir: Path) -> Path:
    return staging_or_output_dir / "overrides.json"


def load_overrides(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "sheets": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_overrides(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        record: dict[str, Any] = {}
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                record[str(col)] = None
            elif hasattr(val, "item"):
                try:
                    record[str(col)] = val.item()
                except (ValueError, AttributeError):
                    record[str(col)] = val
            else:
                record[str(col)] = val
        out.append(record)
    return out


def records_to_dataframe(
    records: list[dict[str, Any]],
    columns: list[str] | None = None,
) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=columns or [])
    df = pd.DataFrame(records)
    if columns:
        for col in columns:
            if col not in df.columns:
                df[col] = None
        df = df[columns]
    return df


def store_sheet_override(
    path: Path,
    sheet_name: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    data = load_overrides(path)
    sheets = data.setdefault("sheets", {})
    sheets[sheet_name] = {
        "columns": [str(c) for c in df.columns],
        "records": dataframe_to_records(df),
    }
    save_overrides(path, data)
    return data


def apply_overrides(
    df: pd.DataFrame,
    sheet_name: str,
    overrides: dict[str, Any],
    *,
    join_keys: list[str] | None = None,
) -> pd.DataFrame:
    """Apply saved overrides by join keys (default SUMMARY_KEY_COLUMNS)."""
    sheet_data = overrides.get("sheets", {}).get(sheet_name)
    if not sheet_data:
        return df

    override_df = records_to_dataframe(
        sheet_data.get("records", []),
        sheet_data.get("columns"),
    )
    if override_df.empty:
        return df

    keys = join_keys or [k for k in SUMMARY_KEY_COLUMNS if k in df.columns]
    if not keys or not all(k in override_df.columns for k in keys):
        return override_df if len(override_df) == len(df) else df

    merged = df.set_index(keys)
    patch = override_df.set_index(keys)
    for col in patch.columns:
        if col in keys:
            continue
        if col in merged.columns:
            merged[col] = patch[col].combine_first(merged[col])
        else:
            merged[col] = patch[col]
    return merged.reset_index()
