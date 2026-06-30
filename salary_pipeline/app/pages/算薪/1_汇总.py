"""算薪汇总 — 新媒体 / 邀约专员 / 客户专员 统一对账一览。"""

from __future__ import annotations

import streamlit as st

from salary_pipeline.app._nav import (
    P_SALARY_ALIGN,
    P_SALARY_CUSTOMER,
    P_SALARY_INVITE,
    P_SALARY_NEW_MEDIA,
)

from salary_pipeline.app._salary_summary import (
    FAMILIES,
    build_salary_summary,
    family_pass_counts,
)
from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import resolve_project_path

st.set_page_config(page_title="算薪汇总", layout="wide")
month_id = render_sidebar()

st.title("算薪汇总")
st.caption(
    f"账期 **{month_id}** · 已接入岗位族 **{sum(len(s.list_roles()) for s in FAMILIES)}** 人"
    "从当月 Excel 抽取输入、计算器回放，并与金标准子表核对。"
)

cfg = load_month_config_for(month_id)
sales_path = resolve_project_path(cfg["workbooks"]["sales"])

if not sales_path.exists():
    st.error(f"未找到当月账套：{sales_path}")
    st.stop()

loader = WorkbookLoader(sales_path)

with st.spinner("正在汇总全员算薪…"):
    summary = build_salary_summary(loader)
    stats = family_pass_counts(summary)

total_ok = int((summary["一致"] == "✓").sum())
total_bad = int((summary["一致"] == "✗").sum())
total_na = int(summary["一致"].isin(["—"]).sum())

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("核对行数", len(summary))
with m2:
    st.metric("一致", total_ok)
with m3:
    st.metric("不一致", total_bad)
with m4:
    st.metric("未对账", total_na)

if total_bad == 0 and total_na == 0:
    st.success("全员算薪与金标准一致。")
elif total_bad > 0:
    st.warning(f"有 {total_bad} 行与金标准不一致，见下表。")

st.markdown("### 按岗位族")
st.dataframe(stats, use_container_width=True, hide_index=True)

filter_family = st.multiselect(
    "筛选岗位族",
    options=summary["岗位族"].unique().tolist(),
    default=summary["岗位族"].unique().tolist(),
)
show_only_diff = st.checkbox("仅看不一致", value=False)

view = summary[summary["岗位族"].isin(filter_family)].copy()
if show_only_diff:
    view = view[view["一致"] == "✗"]

st.markdown("### 明细")
st.dataframe(
    view.style.format(
        {
            "计算值": "{:,.2f}",
            "金标准": "{:,.2f}",
            "差异": "{:+,.2f}",
        },
        na_rep="—",
    ),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.markdown("### 分岗位族填写入口")
cols = st.columns(3)
pages = [
    ("新媒体算薪", P_SALARY_NEW_MEDIA),
    ("邀约专员算薪", P_SALARY_INVITE),
    ("客户专员算薪", P_SALARY_CUSTOMER),
    ("字段拉通", P_SALARY_ALIGN),
]
for col, (label, page) in zip(cols, pages):
    with col:
        if st.button(label, use_container_width=True, key=f"go_{label}"):
            st.switch_page(page)

st.caption("侧栏 **算薪** 分组下可进入各岗位族填写页与字段拉通。")
