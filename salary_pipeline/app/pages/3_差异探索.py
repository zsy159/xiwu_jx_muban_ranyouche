"""差异探索 — golden vs computed 并排"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.observability.diff_data import (
    acceptance_columns,
    build_diff_table,
    load_comparison_frames,
    performance_columns,
)
from salary_pipeline.observability.loaders import load_observability_config, load_month_config_for

st.set_page_config(page_title="差异探索", layout="wide")
month_id = render_sidebar()

obs = load_observability_config()
anchor_ids = list(obs["anchors"].keys())
anchor_labels = {k: v["label"] for k, v in obs["anchors"].items()}
default_idx = anchor_ids.index(
    st.session_state.get("diff_anchor", st.session_state.get("selected_anchor", "hub"))
)
anchor_id = st.selectbox(
    "锚点表",
    anchor_ids,
    index=default_idx,
    format_func=lambda k: anchor_labels[k],
)

col_mode = st.radio(
    "列显示",
    ["验收列（财务默认）", "含绩效 W–AI（仅提成汇总）", "全部列"],
    horizontal=True,
)

try:
    golden, computed, join_keys = load_comparison_frames(month_id, anchor_id)
except FileNotFoundError as exc:
    st.error(f"无法加载数据：{exc}")
    st.stop()

if col_mode.startswith("验收列"):
    show_cols = acceptance_columns(month_id, anchor_id)
elif col_mode.startswith("含绩效"):
    show_cols = acceptance_columns(month_id, anchor_id) + performance_columns(anchor_id)
else:
    show_cols = [c for c in computed.columns if c not in ("_excel_row",)]

show_cols = list(dict.fromkeys(show_cols))
display_cols = join_keys + [c for c in show_cols if c not in join_keys and c in golden.columns]

role_col = "职务" if "职务" in golden.columns else ("店别" if "店别" in golden.columns else join_keys[0])
roles = sorted(golden[role_col].dropna().astype(str).unique().tolist())
role_filter = st.selectbox("筛选岗位（可选）", ["（全部）"] + roles)

g_view = golden.copy()
c_view = computed.copy()
if role_filter != "（全部）" and role_col in g_view.columns:
    g_view = g_view[g_view[role_col].astype(str) == role_filter]
    c_view = c_view[c_view[role_col].astype(str) == role_filter]

st.subheader("仅差异行")
cfg = load_month_config_for(month_id)
tol = float(cfg.get("parity", {}).get("numeric_tolerance", 1e-4))
diff_df = build_diff_table(g_view, c_view, join_keys, show_cols, tolerance=tol)
if diff_df.empty:
    st.success("当前筛选下无差异单元格。")
else:
    st.dataframe(diff_df, use_container_width=True, hide_index=True)

st.subheader("并排数据（选中列）")
merged = g_view[join_keys].merge(
    c_view[join_keys + [c for c in show_cols if c in c_view.columns]],
    on=join_keys,
    how="inner",
    suffixes=("_g", "_c"),
)
side_rows = []
for _, row in g_view.head(50).iterrows():
    key = {k: row[k] for k in join_keys}
    c_row = c_view
    for k, v in key.items():
        c_row = c_row[c_row[k] == v]
    if c_row.empty:
        continue
    c_row = c_row.iloc[0]
    for col in show_cols:
        if col not in row.index and col not in c_row.index:
            continue
        gv = row.get(col)
        cv = c_row.get(col)
        side_rows.append({**key, "列": col, "金标准": gv, "系统": cv})

if side_rows:
    st.dataframe(pd.DataFrame(side_rows), use_container_width=True, hide_index=True)
else:
    st.info("无匹配行可展示。")
