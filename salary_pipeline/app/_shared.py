"""Shared Streamlit UI helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "_bootstrap",
    Path(__file__).resolve().parent / "_bootstrap.py",
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

import streamlit as st

from salary_pipeline.observability.loaders import discover_months, load_months_registry


def render_scrollable_dataframe(df) -> None:
    """宽表横向滚动：扁平行列 + st.dataframe(width=content)。"""
    import pandas as pd

    if isinstance(df.columns, pd.MultiIndex) or (
        df.index.name and not isinstance(df.index, pd.RangeIndex)
    ):
        field_headers = (
            [f"{grp}\n{fld}" for grp, fld in df.columns]
            if isinstance(df.columns, pd.MultiIndex)
            else list(df.columns)
        )
        display = pd.DataFrame(
            [[df.index[i], *df.iloc[i].tolist()] for i in range(len(df))],
            columns=["版式", *field_headers],
        )
    else:
        display = df.copy()

    col_config = {
        col: st.column_config.TextColumn(
            col,
            width=90 if col == "版式" else 132,
            disabled=True,
        )
        for col in display.columns
    }

    st.dataframe(
        display,
        width="content",
        hide_index=True,
        column_config=col_config,
    )


def init_session_state() -> None:
    registry = load_months_registry()
    default = registry.get("default_month", "2026-05")
    if "month_id" not in st.session_state:
        st.session_state.month_id = default
    if "dev_mode" not in st.session_state:
        st.session_state.dev_mode = False
    if "selected_anchor" not in st.session_state:
        st.session_state.selected_anchor = "hub"
    if "selected_role" not in st.session_state:
        st.session_state.selected_role = None


def render_sidebar() -> str:
    init_session_state()
    months = discover_months()
    month_ids = [m.month_id for m in months]
    if st.session_state.month_id not in month_ids and month_ids:
        st.session_state.month_id = month_ids[0]

    st.sidebar.title("薪酬流水线观察台")
    choice = st.sidebar.selectbox(
        "账期",
        month_ids,
        index=month_ids.index(st.session_state.month_id),
        format_func=lambda mid: next(
            (m.label for m in months if m.month_id == mid), mid
        ),
    )
    st.session_state.month_id = choice

    current = next((m for m in months if m.month_id == choice), None)
    if current:
        flags = []
        if current.has_raw:
            flags.append("有金标准")
        if current.has_output:
            flags.append("已跑批")
        else:
            flags.append("未跑批")
        st.sidebar.caption(" · ".join(flags))

    st.session_state.dev_mode = st.sidebar.checkbox(
        "开发者模式",
        value=st.session_state.dev_mode,
        help="显示公式告警、金标准引导技术说明等",
    )
    return choice
