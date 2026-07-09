"""综合表 / 重功超期+活动 — Hub 调整列 SUMIF 数据源（上传表 data_only 读值）。"""

from __future__ import annotations

import logging

import pandas as pd

from salary_pipeline.data_ingestion.closure_input_sheets import OVERDUE_CAMPAIGN_SHEET
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader, normalize_name

logger = logging.getLogger(__name__)

COMPOSITE_SUMMARY_SHEET = "综合表"
COMPOSITE_SUMMARY_HEADER_ROW = 4
OVERDUE_CAMPAIGN_HEADER_ROW = 3


def _slice_below_header(frame: pd.DataFrame, header_row: int) -> pd.DataFrame:
    """Excel header_row is 1-based; first data row is header_row + 1 → iloc[header_row:]."""
    if frame.empty or header_row < 1:
        return frame
    return frame.iloc[header_row:].copy().reset_index(drop=True)


def load_composite_summary_sumif_frame(
    loader: WorkbookLoader,
    *,
    header_row: int = COMPOSITE_SUMMARY_HEADER_ROW,
) -> pd.DataFrame | None:
    """综合表 B/J/L — Hub 综合项、（已发放奖励）SUMIF 键/值列。"""
    if not loader.has_sheet(COMPOSITE_SUMMARY_SHEET):
        logger.warning("composite_summary: sheet %s not found", COMPOSITE_SUMMARY_SHEET)
        return None
    try:
        frame = loader.read_sheet_columns(
            COMPOSITE_SUMMARY_SHEET,
            {"B": "B", "J": "J", "L": "L"},
            label=f"{COMPOSITE_SUMMARY_SHEET} hub-adjustment",
        )
        frame = _slice_below_header(frame, header_row)
        frame["B"] = frame["B"].map(normalize_name)
        frame["J"] = pd.to_numeric(frame["J"], errors="coerce")
        frame["L"] = pd.to_numeric(frame["L"], errors="coerce")
        return frame.dropna(subset=["B"])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("composite_summary: read %s failed: %s", COMPOSITE_SUMMARY_SHEET, exc)
        return None


def load_overdue_campaign_hub_frame(
    loader: WorkbookLoader,
    *,
    header_row: int = OVERDUE_CAMPAIGN_HEADER_ROW,
) -> pd.DataFrame | None:
    """重功超期+活动 Q/X — Hub 月度活动列 SUMIF 键/值列。"""
    if not loader.has_sheet(OVERDUE_CAMPAIGN_SHEET):
        logger.warning("composite_summary: sheet %s not found", OVERDUE_CAMPAIGN_SHEET)
        return None
    try:
        frame = loader.read_sheet_columns(
            OVERDUE_CAMPAIGN_SHEET,
            {"Q": "Q", "X": "X"},
            label=f"{OVERDUE_CAMPAIGN_SHEET} hub-adjustment",
        )
        frame = _slice_below_header(frame, header_row)
        frame["Q"] = frame["Q"].map(normalize_name)
        frame["X"] = pd.to_numeric(frame["X"], errors="coerce")
        return frame.dropna(subset=["Q"])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "composite_summary: read %s failed: %s", OVERDUE_CAMPAIGN_SHEET, exc
        )
        return None
