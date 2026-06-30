"""薪酬流水线观察台 — 总览 Dashboard"""

from __future__ import annotations

import streamlit as st

from salary_pipeline.app._nav import (
    P_EXPLORE,
    P_RECONCILE,
    P_ACCEPTANCE,
    P_DEV,
    P_SALARY_SUMMARY,
)
from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.observability.loaders import get_anchor_snapshots

st.set_page_config(page_title="总览", layout="wide")

month_id = render_sidebar()

st.title("总览")
st.caption(f"账期：**{month_id}** · 金标准 vs 系统计算对账一览")

snapshots = get_anchor_snapshots(month_id)
cols = st.columns(len(snapshots))

for col, snap in zip(cols, snapshots):
    with col:
        st.subheader(f"{snap.status_icon} {snap.label}")
        if not snap.has_output:
            st.warning("尚未跑批")
            st.caption("仅有金标准或尚无 output 文件")
        elif snap.overall_passed:
            if snap.gated_performance_passed is True:
                st.success("验收通过 · 算薪族 W–AI 已过")
            elif snap.gated_performance_passed is False:
                st.warning("F–P 已过 · 算薪族 W–AI 未全")
                st.metric("算薪族绩效不一致", snap.gated_performance_mismatch_cells)
            elif snap.performance_passed is False:
                st.warning("F–P 已过 · 绩效层未全")
                st.metric("绩效不一致", snap.performance_mismatch_cells)
            else:
                st.success("验收通过")
            st.metric("F–P 不一致", snap.mismatch_cells)
        else:
            st.error("验收未通过")
            st.metric("未通过岗位", snap.failed_roles)
            st.metric("不一致单元格", snap.mismatch_cells)
        if snap.report_time:
            st.caption(f"报告：{snap.report_time[:19]}")
        if st.button("查看对账", key=f"go_{snap.anchor_id}"):
            st.session_state.selected_anchor = snap.anchor_id
            st.switch_page(P_RECONCILE)

st.divider()
st.markdown("### 算薪")
if st.button("算薪汇总（各岗位族）", use_container_width=True, type="primary"):
    st.switch_page(P_SALARY_SUMMARY)

st.markdown("### 其他")
c1, c2, c3 = st.columns(3)
with c1:
    if st.button("对账中心", use_container_width=True):
        st.switch_page(P_RECONCILE)
with c2:
    if st.button("差异探索", use_container_width=True):
        st.switch_page(P_EXPLORE)
with c3:
    if st.button("验收摘要", use_container_width=True):
        st.switch_page(P_ACCEPTANCE)

if st.session_state.get("dev_mode"):
    st.divider()
    if st.button("开发者工具", use_container_width=True):
        st.switch_page(P_DEV)
