"""对账中心 — 分岗位对账与列级下钻"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from salary_pipeline.app._nav import P_EXPLORE
from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.observability.loaders import (
    get_anchor_snapshots,
    load_observability_config,
    load_parity_report,
)

st.set_page_config(page_title="对账中心", layout="wide")
month_id = render_sidebar()

obs = load_observability_config()
anchor_ids = list(obs["anchors"].keys())
anchor_labels = {k: v["label"] for k, v in obs["anchors"].items()}

default_idx = anchor_ids.index(st.session_state.get("selected_anchor", "hub"))
anchor_id = st.selectbox(
    "锚点表",
    anchor_ids,
    index=default_idx,
    format_func=lambda k: anchor_labels[k],
)
st.session_state.selected_anchor = anchor_id

snapshots = {s.anchor_id: s for s in get_anchor_snapshots(month_id)}
snap = snapshots[anchor_id]

st.title(f"对账中心 · {snap.label}")

if not snap.report_path:
    st.warning("暂无对账报告。请先运行：`python main.py compute --reconcile`（或对应账套命令）")
    st.stop()

report = load_parity_report(Path(snap.report_path))

c1, c2, c3, c4 = st.columns(4)
c1.metric("金标准行数", report.total_rows_golden)
c2.metric("系统行数", report.total_rows_computed)
c3.metric("金标准有/系统无", report.missing_in_computed)
c4.metric("系统有/金标准无", report.missing_in_golden)

verdict = "✅ 通过" if report.overall_passed else "❌ 未通过"
st.markdown(f"**整体结论：{verdict}**")
st.caption(f"金标准：`{report.golden_source}`")
st.caption(f"系统：`{report.computed_source}`")

only_failed = st.checkbox("仅显示未通过岗位", value=not report.overall_passed)

rows = []
for role in report.roles:
    if only_failed and role.passed:
        continue
    rows.append(
        {
            "岗位": role.role,
            "人数": role.row_count,
            "缺失行": role.missing_rows,
            "不一致单元格": role.mismatch_cells,
            "结论": "✅" if role.passed else "❌",
        }
    )

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader("岗位下钻")
roles_failed = [r.role for r in report.roles if not r.passed]
roles_all = [r.role for r in report.roles]
role_pick = st.selectbox(
    "选择岗位",
    roles_failed if only_failed and roles_failed else roles_all,
    index=0,
)

role_result = next(r for r in report.roles if r.role == role_pick)
if not role_result.column_diffs:
    st.info("该岗位无列级差异。")
else:
    for cd in role_result.column_diffs:
        with st.expander(f"{cd.column} — {cd.mismatch_count} 处不一致"):
            if cd.sample_rows:
                st.dataframe(pd.DataFrame(cd.sample_rows), hide_index=True)
            if st.button("在差异探索中查看", key=f"diff_{role_pick}_{cd.column}"):
                st.session_state.selected_role = role_pick
                st.session_state.diff_anchor = anchor_id
                st.switch_page(P_EXPLORE)
