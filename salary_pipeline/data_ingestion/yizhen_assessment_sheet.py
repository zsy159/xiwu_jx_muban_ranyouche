"""翼真考核子表 — 新媒体（蒋利）整车完成考核 SUMIF 源。"""

from __future__ import annotations

import pandas as pd

from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name

SHEET = "翼真考核"
NAME_COL = "C"
VALUE_COL = "AC"


def load_yizhen_assessment_frame(loader: WorkbookLoader) -> pd.DataFrame:
    if not loader.has_sheet(SHEET):
        return pd.DataFrame(columns=["name", "value"])
    frame = loader.read_sheet_columns(
        SHEET,
        {NAME_COL: NAME_COL, VALUE_COL: VALUE_COL},
        label=f"{SHEET}!{NAME_COL}:{VALUE_COL}",
    )
    if frame.empty:
        return pd.DataFrame(columns=["name", "value"])
    out = pd.DataFrame(
        {
            "name": frame[NAME_COL].astype(str).map(normalize_name),
            "value": pd.to_numeric(frame[VALUE_COL], errors="coerce"),
        }
    )
    return out.dropna(subset=["name"]).loc[out["name"].astype(str).str.len() > 0]


def lookup_yizhen_completion(frame: pd.DataFrame, name: str) -> float:
    if frame.empty:
        return 0.0
    key = normalize_name(name)
    mask = frame["name"] == key
    if not mask.any():
        return 0.0
    return float(frame.loc[mask, "value"].fillna(0).sum())
