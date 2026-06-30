"""邀约专员算薪 — 财务填写入口（DCC邀约专员）。"""

from __future__ import annotations

import json
from dataclasses import asdict

import pandas as pd
import streamlit as st

from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.calculators.invite_specialist import (
    compute_for_role,
    extract_role_inputs,
    list_roles,
    lookup_golden_af,
)
from salary_pipeline.calculators.invite_specialist.migrate import coerce_invite_inputs
from salary_pipeline.calculators.invite_specialist.registry import (
    _is_chaoshi_template,
    _is_chongzhou_template,
    _is_xiwu_template,
    hub_column_for_role,
)
from salary_pipeline.calculators.invite_specialist.types import InviteDccInput
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import PROJECT_ROOT, resolve_project_path

st.set_page_config(page_title="邀约专员算薪", layout="wide")
month_id = render_sidebar()

st.title("邀约专员算薪")
st.caption(
    f"账期 **{month_id}** · **西物** / **超市** DCC 与 **崇州** 直营各一套子表版式，"
    "对应「邀约专员提成」不同区块；DCC 写入 Hub **W**，崇州写入 **AK**。"
)

roles = list_roles()
role_by_name = {r["name"]: r for r in roles}
role_names = [r["name"] for r in roles]

xiwu_names = [r["name"] for r in roles if r.get("company") == "西物"]
chaoshi_names = [r["name"] for r in roles if r.get("company") == "超市"]
chongzhou_names = [r["name"] for r in roles if r.get("company") == "崇州"]

col_pick, col_load = st.columns([2, 1])
with col_pick:
    company_filter = st.radio(
        "主体",
        [
            "全部",
            "西物（武侯DCC · 5人）",
            "超市（机场DCC · 3人）",
            "崇州（直营店 · 1人）",
        ],
        horizontal=True,
    )
    filtered_names = role_names
    if company_filter.startswith("西物"):
        filtered_names = xiwu_names
    elif company_filter.startswith("超市"):
        filtered_names = chaoshi_names
    elif company_filter.startswith("崇州"):
        filtered_names = chongzhou_names

    selected = st.selectbox(
        "选择人员",
        filtered_names,
        format_func=lambda n: (
            f"{n}（{role_by_name[n].get('company', '')} · {role_by_name[n].get('store', '')}）"
        ),
    )
role = role_by_name[selected]
template = role["template"]
company = role.get("company", "")

cfg = load_month_config_for(month_id)
sales_path = resolve_project_path(cfg["workbooks"]["sales"])
loader: WorkbookLoader | None = None
if sales_path.exists():
    loader = WorkbookLoader(sales_path)

if col_load.button("从当月 Excel 预填", disabled=loader is None):
    if loader:
        st.session_state[f"inv_inputs_{selected}"] = extract_role_inputs(loader, selected)
        st.success(f"已从「邀约专员提成」加载 {selected} 的数据")

session_key = f"inv_inputs_{selected}"
if session_key not in st.session_state:
    if loader:
        try:
            st.session_state[session_key] = extract_role_inputs(loader, selected)
        except Exception:
            from salary_pipeline.calculators.invite_specialist.registry import (
                default_input_for_role,
            )

            st.session_state[session_key] = default_input_for_role(role)
    else:
        from salary_pipeline.calculators.invite_specialist.registry import (
            default_input_for_role,
        )

        st.session_state[session_key] = default_input_for_role(role)

st.session_state[session_key] = coerce_invite_inputs(st.session_state[session_key])
inputs = st.session_state[session_key]

st.subheader(f"{selected} · {company} · {role.get('store', '')}")

is_xiwu = _is_xiwu_template(template)
is_chaoshi = _is_chaoshi_template(template)
is_chongzhou = _is_chongzhou_template(template)
hub_col_label = hub_column_for_role(role)

with st.form("invite_calc", clear_on_submit=False, enter_to_submit=False):
    if is_chongzhou:
        layout_name = "崇州版式"
        layout_hint = "AD = I+L+O+T+W+Z−AC−F"
    elif is_xiwu:
        layout_name = "西物版式"
        layout_hint = "AD = I+L+O+T+W+Z+AC+F"
    else:
        layout_name = "超市版式"
        layout_hint = "Y = I+K×J+…"
    st.markdown(
        f"**{layout_name}（细化）** — {layout_hint}；"
        "DMS 六项每项 100 元；其余各项为「数量 × 单价」。"
    )

    with st.container(border=True):
        st.markdown("**DMS 七项指标**")
        st.caption(
            "线索有效率、响应及时率、跟进率、邀约到店率、到店成交率、线索成交率、战败率；"
            "每项达成 100 元，七项全部达成再追加 100 元。"
        )
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            dms_count = st.number_input(
                "达成项数（0–7）",
                min_value=0.0,
                max_value=7.0,
                value=float(inputs.dms_achieved_count),
                step=1.0,
                key=f"{selected}_dms_n",
            )
        with c2:
            dms_unit = st.number_input(
                "单项奖励（元）",
                value=float(inputs.dms_per_item_reward),
                step=100.0,
                key=f"{selected}_dms_u",
            )
        with c3:
            dms_all_seven = st.checkbox(
                "七项均达成追加",
                value=bool(inputs.dms_all_seven_achieved),
                key=f"{selected}_dms_all",
            )
        with c4:
            dms_bonus_amt = st.number_input(
                "追加金额（元）",
                value=float(inputs.dms_all_seven_bonus),
                step=100.0,
                key=f"{selected}_dms_b",
                disabled=not dms_all_seven,
            )
        dms_score = dms_count * dms_unit
        dms_bonus = dms_bonus_amt if dms_all_seven else 0.0
        st.metric("DMS 小计", f"{dms_score + dms_bonus:,.0f}", f"得分 {dms_score:,.0f}")

    with st.container(border=True):
        st.markdown("**邀约到店绩效** = 到店组数 × 基础单价（60 元/组）")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            invite_groups = st.number_input(
                "邀约到店组数",
                value=float(inputs.invite_groups),
                step=1.0,
                key=f"{selected}_groups",
            )
        with c2:
            invite_rate = st.number_input(
                "基础单价（元/组）",
                value=float(inputs.invite_unit_rate),
                step=10.0,
                key=f"{selected}_jrate",
            )
        with c3:
            st.metric("小计", f"{invite_groups * invite_rate:,.0f}")

    with st.container(border=True):
        if is_chaoshi:
            st.markdown("**邀约到店率追加** `超市版式无此项`")
            st.caption(
                "子表「邀约专员提成」超市块（行 11–13）不含西物 S 列「单组追加×到店量」；"
                "对应激励见下方 **达成邀约奖励**（P×Q）。"
            )
            invite_bonus = 0.0
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                st.caption(f"组数 {invite_groups:.0f}（仅展示）")
            with c2:
                st.text_input(
                    "追加单价（元/组）",
                    value="—",
                    disabled=True,
                    key=f"{selected}_sbonus_na",
                )
            with c3:
                st.metric("小计", "不适用")
        elif is_chongzhou:
            st.markdown("**过程KPI奖励** = 到店组数 × 单组追加")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                st.caption(f"组数 {invite_groups:.0f}（同上）")
            with c2:
                invite_bonus = st.number_input(
                    "单组追加（元/组）",
                    value=float(inputs.invite_rate_bonus_per_group),
                    step=1.0,
                    key=f"{selected}_sbonus",
                )
            with c3:
                st.metric("小计", f"{invite_groups * invite_bonus:,.0f}")
        else:
            st.markdown("**邀约到店率追加** = 组数 × 追加单价（到店率≥15% 填 10，未达标填 0）")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                st.caption(f"组数 {invite_groups:.0f}（同上）")
            with c2:
                invite_bonus = st.number_input(
                    "追加单价（元/组）",
                    value=float(inputs.invite_rate_bonus_per_group),
                    step=1.0,
                    key=f"{selected}_sbonus",
                )
            with c3:
                st.metric("小计", f"{invite_groups * invite_bonus:,.0f}")

    with st.container(border=True):
        st.markdown("**成交台次绩效** = 台次 × 基础单价（40 元/台）")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            deal_count = st.number_input(
                "成交台次",
                value=float(inputs.deal_count),
                step=1.0,
                key=f"{selected}_deals",
            )
        with c2:
            deal_rate = st.number_input(
                "基础单价（元/台）",
                value=float(inputs.deal_unit_rate),
                step=10.0,
                key=f"{selected}_mrate",
            )
        with c3:
            st.metric("小计", f"{deal_count * deal_rate:,.0f}")

    with st.container(border=True):
        st.markdown("**成交率追加** = 台次 × 阶梯单价（30%–35% 填 20，≥35% 填 30）")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            st.caption(f"台次 {deal_count:.0f}（同上）")
        with c2:
            deal_bonus = st.number_input(
                "追加单价（元/台）",
                value=float(inputs.deal_rate_bonus_per_unit),
                step=10.0,
                key=f"{selected}_vbonus",
            )
        with c3:
            st.metric("小计", f"{deal_count * deal_bonus:,.0f}")

    achieved_vol = float(inputs.achieved_invite_volume)
    group_bonus = float(inputs.per_group_store_bonus)
    heavy_bonus = float(inputs.heavy_attack_bonus)
    heavy_mult = float(inputs.heavy_attack_multiplier)
    task_adj = float(inputs.task_adjustment)
    task_penalty = float(inputs.task_penalty)
    call_answer_penalty = float(inputs.call_answer_penalty)

    if is_chongzhou:
        with st.container(border=True):
            st.markdown("**重攻奖励** = 基数 × 台次")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                heavy_bonus = st.number_input(
                    "单组追加基数",
                    value=heavy_bonus,
                    step=10.0,
                    key=f"{selected}_heavy",
                )
            with c2:
                heavy_mult = st.number_input(
                    "重攻台次",
                    value=heavy_mult,
                    step=1.0,
                    key=f"{selected}_heavym",
                )
            with c3:
                st.metric("小计", f"{heavy_bonus * heavy_mult:,.0f}")

        with st.container(border=True):
            st.markdown("**任务考核扣减（AC）**")
            task_penalty = st.number_input(
                "扣减金额",
                value=task_penalty,
                step=50.0,
                key=f"{selected}_task",
            )

        with st.container(border=True):
            st.markdown("**400接起率考核（F）**")
            call_answer_penalty = st.number_input(
                "扣减金额（未接起 500）",
                value=call_answer_penalty,
                step=50.0,
                key=f"{selected}_call",
            )
    elif is_xiwu:
        with st.container(border=True):
            st.markdown("**重攻车型奖励** = 基数 × 系数（10 元/组）")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                heavy_bonus = st.number_input(
                    "奖励基数",
                    value=heavy_bonus,
                    step=100.0,
                    key=f"{selected}_heavy",
                )
            with c2:
                heavy_mult = st.number_input(
                    "到店组数/系数",
                    value=heavy_mult,
                    step=1.0,
                    key=f"{selected}_heavym",
                )
            with c3:
                st.metric("小计", f"{heavy_bonus * heavy_mult:,.0f}")

        with st.container(border=True):
            st.markdown("**任务考核调整**（未达成邀约目标按比例计提，上限 100%）")
            task_adj = st.number_input(
                "调整金额（可负）",
                value=task_adj,
                step=50.0,
                key=f"{selected}_task",
            )
    else:
        with st.container(border=True):
            st.markdown("**达成邀约奖励** = 达成量 × 单组到店追加")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                achieved_vol = st.number_input(
                    "达成邀约量",
                    value=achieved_vol,
                    step=1.0,
                    key=f"{selected}_cp",
                )
            with c2:
                group_bonus = st.number_input(
                    "单组到店追加（元/组）",
                    value=group_bonus,
                    step=10.0,
                    key=f"{selected}_cq",
                )
            with c3:
                st.metric("小计", f"{achieved_vol * group_bonus:,.0f}")

        with st.container(border=True):
            st.markdown("**任务考核扣减**")
            task_penalty = st.number_input(
                "扣减金额",
                value=task_penalty,
                step=10.0,
                key=f"{selected}_cx",
            )

    form_inputs = InviteDccInput(
        dms_achieved_count=dms_count,
        dms_per_item_reward=dms_unit,
        dms_all_seven_achieved=dms_all_seven,
        dms_all_seven_bonus=dms_bonus_amt,
        invite_groups=invite_groups,
        invite_unit_rate=invite_rate,
        invite_rate_bonus_per_group=invite_bonus,
        deal_count=deal_count,
        deal_unit_rate=deal_rate,
        deal_rate_bonus_per_unit=deal_bonus,
        achieved_invite_volume=achieved_vol,
        per_group_store_bonus=group_bonus,
        heavy_attack_bonus=heavy_bonus,
        heavy_attack_multiplier=heavy_mult,
        task_adjustment=task_adj,
        task_penalty=task_penalty,
        call_answer_penalty=call_answer_penalty,
    )
    preview = compute_for_role(selected, form_inputs)
    st.metric("预计总绩效", f"{preview.hub_vehicle_performance:,.2f}")

    submitted = st.form_submit_button("计算", type="primary", use_container_width=True)

if submitted:
    st.session_state[session_key] = form_inputs
    result = compute_for_role(selected, form_inputs)
    st.session_state[f"inv_result_{selected}"] = result

if f"inv_result_{selected}" in st.session_state:
    result = st.session_state[f"inv_result_{selected}"]
    st.divider()
    m1, m2 = st.columns(2)
    with m1:
        st.metric("发放金额（子表 AD）" if is_chongzhou else "发放金额（子表 AF）", f"{result.performance_salary:,.2f}")
    with m2:
        hub_letter = "AK" if is_chongzhou else "W"
        st.metric(f"Hub {hub_col_label}（{hub_letter}）", f"{result.hub_vehicle_performance:,.2f}")

    breakdown = result.breakdown.to_dict()
    if breakdown:
        st.markdown("**分项明细**")
        st.dataframe(
            pd.DataFrame([breakdown]).T.rename(columns={0: "金额"}),
            use_container_width=True,
        )

    if loader:
        golden = lookup_golden_af(loader, selected)
        if golden is not None:
            delta = result.hub_vehicle_performance - golden
            if abs(delta) < 0.02:
                st.success(f"与当月 Excel 子表一致（{golden:,.2f}）")
            else:
                st.warning(
                    f"与当月 Excel 子表差异 {delta:+,.2f}（金标准 {golden:,.2f}）"
                )

st.divider()
st.markdown("**保存填写记录**（供后续跑批引用，可选）")
out_dir = PROJECT_ROOT / "output" / month_id / "inputs"
out_path = out_dir / "invite_specialist_inputs.json"

if st.button("保存到 output 目录"):
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    for r in roles:
        key = f"inv_inputs_{r['name']}"
        if key in st.session_state:
            payload[r["name"]] = {
                "template": r["template"],
                "company": r.get("company"),
                "inputs": asdict(st.session_state[key]),
            }
        res_key = f"inv_result_{r['name']}"
        if res_key in st.session_state:
            res = st.session_state[res_key]
            entry = payload.setdefault(r["name"], {})
            if isinstance(entry, dict):
                entry["result"] = {
                    "performance_salary": res.performance_salary,
                    "hub_vehicle_performance": res.hub_vehicle_performance,
                }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    st.success(f"已保存：{out_path.relative_to(PROJECT_ROOT)}")

if out_path.exists():
    st.caption(f"已有保存文件：{out_path.relative_to(PROJECT_ROOT)}")

st.info(
    "西物 / 超市 DCC 在子表中是两块表头不同的区域；崇州杨婷为第三块。"
    "需查看**全部字段**（含不适用占位）请用侧栏 **算薪 → 字段拉通**。"
)
