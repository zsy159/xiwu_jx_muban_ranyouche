"""直营店经理算薪 — 财务填写入口。"""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import streamlit as st

from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.calculators.direct_store_manager import (
    compute_for_role,
    extract_role_inputs,
    list_roles,
    lookup_golden_r,
)
from salary_pipeline.calculators.direct_store_manager.registry import (
    default_input_for_role,
)
from salary_pipeline.calculators.direct_store_manager.types import StoreBlockInput
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import resolve_project_path

st.set_page_config(page_title="直营店经理算薪", layout="wide")
month_id = render_sidebar()

st.title("直营店经理算薪")
st.caption(
    f"账期 **{month_id}** · 按「直营店经理提成 (财务)」门店块计算 **提成合计**，"
    "对应 Hub **整车完成考核（AK 列）**。钟涛含华阳 + 华阳领克双店块。"
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
            f"{n}（{role_by_name[n].get('store', '')} · {role_by_name[n].get('title', '')}）"
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
        st.session_state[f"dsm_inputs_{selected}"] = extract_role_inputs(
            loader, selected
        )
        st.success(f"已从「直营店经理提成 (财务)」加载 {selected} 的数据")

session_key = f"dsm_inputs_{selected}"
if session_key not in st.session_state:
    if loader:
        try:
            st.session_state[session_key] = extract_role_inputs(loader, selected)
        except Exception:
            st.session_state[session_key] = default_input_for_role(role)
    else:
        st.session_state[session_key] = default_input_for_role(role)

blocks: list[StoreBlockInput] = list(st.session_state[session_key])

st.subheader(f"{selected} · {role.get('store', '')}")

with st.form("dsm_calc", clear_on_submit=False, enter_to_submit=False):
    updated_blocks: list[StoreBlockInput] = []
    for idx, block in enumerate(blocks):
        label = block.store_label or f"门店块 {idx + 1}"
        st.markdown(f"**{label}**")
        c1, c2, c3 = st.columns(3)
        with c1:
            showroom_task = st.number_input(
                "展厅任务台次",
                value=float(block.showroom_task),
                min_value=0.0,
                step=1.0,
                key=f"{selected}_st_{idx}",
            )
            showroom_actual = st.number_input(
                "展厅实际台次",
                value=float(block.showroom_actual),
                min_value=0.0,
                step=1.0,
                key=f"{selected}_sa_{idx}",
            )
            showroom_ev = st.number_input(
                "新能源展厅台次",
                value=float(block.showroom_ev_actual),
                min_value=0.0,
                step=1.0,
                key=f"{selected}_sev_{idx}",
            )
            showroom_rate = st.number_input(
                "展厅单台标准",
                value=float(block.showroom_rate),
                min_value=0.0,
                step=10.0,
                key=f"{selected}_sr_{idx}",
            )
        with c2:
            channel_task = st.number_input(
                "渠道任务台次",
                value=float(block.channel_task),
                min_value=0.0,
                step=1.0,
                key=f"{selected}_ct_{idx}",
            )
            channel_actual = st.number_input(
                "渠道实际台次",
                value=float(block.channel_actual),
                min_value=0.0,
                step=1.0,
                key=f"{selected}_ca_{idx}",
            )
            channel_ev = st.number_input(
                "新能源渠道任务",
                value=float(block.channel_ev_task),
                min_value=0.0,
                step=1.0,
                key=f"{selected}_cev_{idx}",
            )
            channel_rate = st.number_input(
                "渠道单台标准",
                value=float(block.channel_rate),
                min_value=0.0,
                step=10.0,
                key=f"{selected}_cr_{idx}",
            )
        with c3:
            attach = st.number_input(
                "附加收入提成",
                value=float(block.attach_commission),
                step=100.0,
                key=f"{selected}_att_{idx}",
            )
            fixed = st.number_input(
                "固定绩效",
                value=float(block.fixed_performance),
                min_value=0.0,
                step=100.0,
                key=f"{selected}_fix_{idx}",
            )
            extra_v = st.number_input(
                "指定车型考核提成",
                value=float(block.extra_vehicle_commission),
                step=100.0,
                key=f"{selected}_ev_{idx}",
            )
        updated_blocks.append(
            StoreBlockInput(
                store_label=label,
                showroom_task=showroom_task,
                showroom_actual=showroom_actual,
                showroom_ev_actual=showroom_ev,
                showroom_rate=showroom_rate,
                channel_task=channel_task,
                channel_actual=channel_actual,
                channel_ev_task=channel_ev,
                channel_rate=channel_rate,
                attach_commission=attach,
                fixed_performance=fixed,
                extra_vehicle_commission=extra_v,
            )
        )
    submitted = st.form_submit_button("计算", type="primary")

if submitted:
    st.session_state[session_key] = updated_blocks
    blocks = updated_blocks

result = compute_for_role(selected, blocks)
golden = lookup_golden_r(loader, selected) if loader else None

m1, m2, m3 = st.columns(3)
m1.metric("提成合计（计算）", f"{result.performance_salary:,.2f}")
m2.metric("Hub 整车完成考核", f"{result.hub_vehicle_performance:,.2f}")
if golden is not None:
    delta = result.hub_vehicle_performance - golden
    m3.metric("金标准 R 列", f"{golden:,.2f}", delta=f"{delta:+.2f}")

st.markdown("**分项明细**")
bd = result.breakdown.to_dict()
if bd:
    st.dataframe(
        pd.DataFrame([{"项目": k, "金额": v} for k, v in bd.items()]),
        hide_index=True,
        use_container_width=True,
    )

if len(blocks) > 1:
    with st.expander("各门店块输入 JSON"):
        st.json([asdict(b) for b in blocks])
