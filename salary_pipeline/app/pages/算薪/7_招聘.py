"""招聘岗位族算薪 — 团队分配公式。"""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import streamlit as st

from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.calculators.recruit import (
    compute_for_role,
    compute_person_commission,
    extract_role_inputs,
    extract_team_block,
    is_hub_linked,
    list_roles,
    lookup_golden_cells,
    lookup_golden_hub,
)
from salary_pipeline.calculators.recruit.registry import default_input_for_role
from salary_pipeline.calculators.recruit.types import RecruitTeamInput
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import resolve_project_path

st.set_page_config(page_title="招聘算薪", layout="wide")
month_id = render_sidebar()

st.title("招聘算薪")
st.caption(
    f"账期 **{month_id}** · 招聘子表团队分配："
    "**个人提成 = 到岗数 × 单人招聘提成 × 分配比例**。"
    "Hub 保险绩效仅覆盖行政人事部 3 人；李玲仅子表算薪。"
)

roles = list_roles()
role_by_name = {r["name"]: r for r in roles}
role_names = [r["name"] for r in roles]

col_pick, col_load = st.columns([2, 1])
with col_pick:
    selected = st.selectbox(
        "选择人员",
        role_names,
        format_func=lambda n: (
            f"{n}（{role_by_name[n].get('store', '')} · {role_by_name[n].get('title', '')}"
            f"{' · 仅子表' if not is_hub_linked(role_by_name[n]) else ''}）"
        ),
    )
role = role_by_name[selected]

cfg = load_month_config_for(month_id)
sales_path = resolve_project_path(cfg["workbooks"]["sales"])
loader: WorkbookLoader | None = None
if sales_path.exists():
    loader = WorkbookLoader(sales_path)

if col_load.button("从当月 Excel 预填", disabled=loader is None):
    if loader:
        st.session_state[f"recruit_inputs_{selected}"] = extract_role_inputs(
            loader, selected
        )
        st.success(f"已从「招聘」子表加载 {selected} 的数据")

team_block = extract_team_block(loader) if loader else {}
if team_block:
    anchor = next(iter(team_block.values()))
    t1, t2, t3 = st.columns(3)
    t1.metric("5月招聘到岗数", f"{anchor.onboard_count:,.0f}")
    t2.metric("单人招聘提成", f"{anchor.commission_per_hire:,.0f}")
    t3.metric("团队提成合计", f"{anchor.total_commission:,.2f}")

    alloc_rows = []
    for name in role_names:
        team = team_block.get(name)
        if team is None:
            continue
        calc = compute_person_commission(team)
        alloc_rows.append(
            {
                "姓名": name,
                "分配比例": team.allocation_ratio,
                "计算提成": calc,
                "子表 W": team.sheet_amount,
                "Hub": "是" if is_hub_linked(role_by_name[name]) else "否",
            }
        )
    if alloc_rows:
        st.markdown("**团队分配一览**")
        st.dataframe(pd.DataFrame(alloc_rows), hide_index=True, use_container_width=True)

st.divider()

session_key = f"recruit_inputs_{selected}"
if session_key not in st.session_state:
    if loader and selected in team_block:
        st.session_state[session_key] = team_block[selected]
    elif loader:
        try:
            st.session_state[session_key] = extract_role_inputs(loader, selected)
        except Exception:
            st.session_state[session_key] = default_input_for_role(role)
    else:
        st.session_state[session_key] = default_input_for_role(role)

team = st.session_state[session_key]
if team is None:
    team = RecruitTeamInput(
        name=selected,
        onboard_count=0.0,
        commission_per_hire=0.0,
        total_commission=0.0,
        allocation_ratio=0.0,
    )

result = compute_for_role(selected, team)
golden_hub = lookup_golden_hub(loader, selected) if loader else None
golden_cells = lookup_golden_cells(loader, selected) if loader else {}

st.subheader(f"{selected} · {role.get('title', '')}")

m1, m2, m3 = st.columns(3)
m1.metric("个人提成（计算）", f"{result.insurance_performance:,.2f}")
m2.metric("分配比例", f"{team.allocation_ratio:.2f}")
if golden_hub is not None:
    delta = result.insurance_performance - golden_hub
    m3.metric("金标准 Hub Z", f"{golden_hub:,.2f}", delta=f"{delta:+.2f}")
elif golden_cells.get("提成金额") is not None:
    gval = golden_cells["提成金额"]
    delta = result.insurance_performance - gval
    m3.metric("金标准子表 W", f"{gval:,.2f}", delta=f"{delta:+.2f}")
else:
    m3.metric("Hub 挂钩", "否" if not is_hub_linked(role) else "—")

st.markdown("**公式分项**")
st.dataframe(
    pd.DataFrame([result.breakdown]).T.rename(columns={0: "数值"}),
    use_container_width=True,
)

if not is_hub_linked(role):
    st.info("该人员 `hub_linked: false`，不在提成汇总 overlay，仅在招聘模块算薪。")

with st.expander("规则说明"):
    st.markdown(
        f"- 公式：`{team.onboard_count} × {team.commission_per_hire} × {team.allocation_ratio}`\n"
        f"- 子表行：**{team.source_row or '—'}**\n"
        f"- Hub 行：**{role.get('hub_excel_row', '—')}**\n"
        "- 规则文字见 `提成依据` → `销售提成标准`"
    )

with st.expander("输入 JSON"):
    st.json(asdict(team))
