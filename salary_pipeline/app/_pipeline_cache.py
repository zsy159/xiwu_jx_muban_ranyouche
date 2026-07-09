"""Streamlit 算薪页共享缓存 — 工作簿、提成汇总骨架、绩效整理表。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from salary_pipeline.calculators.sales_advisor.extract import build_eval_perf_frame
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.modules.performance_sheet_module import PerformanceSheetModule
from salary_pipeline.modules.summary_skeleton import SummarySkeletonModule
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import resolve_project_path
from salary_pipeline.pipelines.performance_sheet_paths import (
    load_resolved_performance_frame,
    resolve_performance_sheet_path,
)


def _sales_workbook_path(month_id: str) -> Path:
    cfg = load_month_config_for(month_id)
    return resolve_project_path(cfg["workbooks"]["sales"])


def _topology_path(month_id: str) -> Path:
    cfg = load_month_config_for(month_id)
    return resolve_project_path(cfg["topology"]["sales"])


def _mtime_ns(path: Path) -> int:
    return path.stat().st_mtime_ns if path.exists() else 0


@st.cache_resource(show_spinner=False)
def _cached_loader(workbook_path_str: str, mtime_ns: int) -> WorkbookLoader:
    del mtime_ns
    return WorkbookLoader(Path(workbook_path_str))


@st.cache_data(show_spinner=False)
def _cached_skeleton(month_id: str) -> pd.DataFrame:
    cfg = load_month_config_for(month_id)
    return SummarySkeletonModule().run({"month_config": cfg}).metrics.copy()


@st.cache_data(show_spinner="正在构建绩效整理表（仅首次较慢）…")
def _cached_perf_frame(
    month_id: str, sales_mtime_ns: int, perf_mtime_ns: int
) -> pd.DataFrame:
    del sales_mtime_ns, perf_mtime_ns
    cfg = load_month_config_for(month_id)
    loaded = load_resolved_performance_frame(cfg)
    if loaded is not None and not loaded.empty:
        return loaded.copy()
    ctx: dict = {"month_config": cfg}
    PerformanceSheetModule().run(ctx)
    frame = ctx.get("computed_perf_frame")
    return frame.copy() if frame is not None else pd.DataFrame()


@st.cache_data(show_spinner=False)
def _cached_eval_perf(
    month_id: str, sales_mtime_ns: int, perf_mtime_ns: int
) -> pd.DataFrame:
    sales_path = _sales_workbook_path(month_id)
    loader = _cached_loader(str(sales_path), sales_mtime_ns)
    perf = _cached_perf_frame(month_id, sales_mtime_ns, perf_mtime_ns)
    topo = _topology_path(month_id)
    return build_eval_perf_frame(loader, perf, topo)


def get_workbook_loader(month_id: str) -> WorkbookLoader | None:
    path = _sales_workbook_path(month_id)
    if not path.exists():
        return None
    return _cached_loader(str(path), _mtime_ns(path))


def get_summary_skeleton(month_id: str) -> pd.DataFrame:
    return _cached_skeleton(month_id)


def get_advisor_person_row(month_id: str, name: str) -> pd.Series | None:
    skeleton = get_summary_skeleton(month_id)
    advisors = skeleton[skeleton["职务"] == "销售顾问"]
    rows = advisors[advisors["姓名"] == name]
    if rows.empty:
        return None
    return rows.iloc[0]


def get_eval_perf_frame(month_id: str) -> pd.DataFrame | None:
    path = _sales_workbook_path(month_id)
    if not path.exists():
        return None
    cfg = load_month_config_for(month_id)
    perf_path = resolve_performance_sheet_path(cfg)
    return _cached_eval_perf(
        month_id, _mtime_ns(path), _mtime_ns(perf_path)
    )


def get_computed_perf_frame(month_id: str) -> pd.DataFrame | None:
    path = _sales_workbook_path(month_id)
    if not path.exists():
        return None
    cfg = load_month_config_for(month_id)
    perf_path = resolve_performance_sheet_path(cfg)
    return _cached_perf_frame(month_id, _mtime_ns(path), _mtime_ns(perf_path))


def get_topology_path(month_id: str) -> Path:
    return _topology_path(month_id)
