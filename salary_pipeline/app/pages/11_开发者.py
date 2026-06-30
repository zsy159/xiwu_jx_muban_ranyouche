"""开发者 — 告警、金标准引导、注册账期"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.observability.golden_map import get_golden_bootstrap_view
from salary_pipeline.observability.loaders import (
    discover_months,
    get_anchor_snapshots,
    load_month_config_for,
    load_observability_config,
    load_warnings,
    register_month,
)
from salary_pipeline.paths import resolve_project_path

st.set_page_config(page_title="开发者", layout="wide")
month_id = render_sidebar()

if not st.session_state.get("dev_mode"):
    st.warning("请先在侧边栏开启「开发者模式」。")
    st.stop()

st.title("开发者工具")

# --- Warnings ---
st.header("公式告警")
cfg = load_month_config_for(month_id)
report_dir = resolve_project_path(cfg["outputs"]["report_dir"])
obs = load_observability_config()

for anchor_id, anchor in obs["anchors"].items():
    warnings = load_warnings(report_dir, anchor.get("warnings_file", ""))
    with st.expander(f"{anchor['label']} — {len(warnings)} 条"):
        if warnings:
            st.code("\n".join(warnings[:100]))
            if len(warnings) > 100:
                st.caption(f"… 另有 {len(warnings) - 100} 条")
        else:
            st.caption("无告警文件")

# --- Golden map ---
st.header("金标准引导")
gb = get_golden_bootstrap_view()
st.markdown(gb["intro"])
for section in gb["sections"]:
    st.subheader(section["table"])
    rows = []
    for item in section.get("items", []):
        status = item.get("status", "")
        icon = {"golden": "🔴", "partial": "🟡", "computed": "🟢"}.get(status, "⚪")
        rows.append(
            {
                "范围": item.get("range", ""),
                "状态": f"{icon} {status}",
                "说明": item.get("finance_note", ""),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True)

# --- Register month ---
st.header("注册其他账期")
st.caption("将新月份 raw 目录登记到 months_registry.yaml（Phase 2 将支持 zip 上传）。")
with st.form("register_month"):
    new_id = st.text_input("账期 ID", placeholder="2026-06")
    new_label = st.text_input("显示名称", placeholder="2026年06月")
    raw_dir = st.text_input("raw 目录", placeholder="data/raw/2026-06")
    submitted = st.form_submit_button("注册")
    if submitted and new_id and raw_dir:
        try:
            register_month(new_id, new_label or new_id, raw_dir)
            st.success(f"已注册 {new_id}，请重新选择账期。")
        except ValueError as exc:
            st.error(str(exc))

st.subheader("已发现账期")
st.dataframe(
    pd.DataFrame([m.__dict__ for m in discover_months()]),
    hide_index=True,
)
