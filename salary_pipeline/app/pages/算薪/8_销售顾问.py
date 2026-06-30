"""销售顾问算薪 — 绩效整理表汇总填写 + Hub W–AI 实时复算。"""

from __future__ import annotations

import json
from dataclasses import asdict

import pandas as pd
import streamlit as st

from salary_pipeline.app._pipeline_cache import (
    get_advisor_person_row,
    get_computed_perf_frame,
    get_eval_perf_frame,
    get_workbook_loader,
)
from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.calculators.field_alignment.sales_advisor import template_for_role
from salary_pipeline.calculators.sales_advisor import (
    hub_linked_names,
    is_hub_linked,
    list_roles,
    lookup_golden_hub_all,
)
from salary_pipeline.calculators.sales_advisor.aligned_input import (
    ALL_HUB_COLUMNS,
    GATE_HUB_COLUMNS,
    AdvisorAlignedInput,
    coerce_aligned_input,
    compute_aligned,
    default_aligned_input,
    extract_aligned_inputs,
    registration_performance_total,
)
from salary_pipeline.calculators.sales_advisor.vehicle_performance_detail import (
    EDITABLE_COLUMNS,
    load_vehicle_performance_detail,
    recompute_from_display_frame,
)
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import PROJECT_ROOT, resolve_project_path

st.set_page_config(page_title="销售顾问算薪", layout="wide")
month_id = render_sidebar()

st.title("销售顾问算薪")
st.caption(
    f"账期 **{month_id}** · 填写**绩效整理表按人汇总**（整车/加装/保险等）"
    "与完成率，实时复算 Hub **W–AI 共 13 列绩效**。"
    "其中六项为对账门槛；其余七列同链路可算。"
    "底层订单明细见 Phase B；此处为财务对账用的**最终取数层**。"
)

roles = list_roles()
role_by_name = {r["name"]: r for r in roles}
linked_names = hub_linked_names()
picker_names = linked_names or [r["name"] for r in roles if is_hub_linked(r)]

col_pick, col_load = st.columns([2, 1])
with col_pick:
    selected = st.selectbox(
        "选择顾问（hub_linked）",
        picker_names,
        format_func=lambda n: (
            f"{n}（{template_for_role(role_by_name.get(n, {}))}）"
            f"{' · 仅子表' if not is_hub_linked(role_by_name.get(n, {})) else ''}"
        ),
    )

role = role_by_name.get(selected, {"name": selected})
template = template_for_role(role)
template_labels = {
    "personal_h": "个人完成率",
    "store_ba": "门店块",
    "insurance_add": "保险追加常数",
}
template_label = template_labels.get(template, template)

cfg = load_month_config_for(month_id)
sales_path = resolve_project_path(cfg["workbooks"]["sales"])
loader = get_workbook_loader(month_id) if sales_path.exists() else None

person = get_advisor_person_row(month_id, selected)
if person is None:
    st.warning(f"提成汇总中未找到 {selected}")
    st.stop()

session_key = f"sa_inputs_{selected}"
eval_perf: pd.DataFrame | None = None

if col_load.button("从当月 Excel 预填", disabled=loader is None):
    if loader is not None:
        eval_perf = get_eval_perf_frame(month_id)
        if eval_perf is not None:
            st.session_state[session_key] = extract_aligned_inputs(
                loader, eval_perf, person
            )
            st.session_state[f"sa_vehicle_detail_{selected}"] = load_vehicle_performance_detail(
                loader,
                selected,
                eval_perf=eval_perf,
                computed_perf=get_computed_perf_frame(month_id),
            )
            st.success(f"已从绩效整理表汇总加载 {selected} 的数据")

if session_key not in st.session_state:
    if loader is not None:
        eval_perf = get_eval_perf_frame(month_id)
        if eval_perf is not None:
            try:
                st.session_state[session_key] = extract_aligned_inputs(
                    loader, eval_perf, person
                )
            except Exception:
                st.session_state[session_key] = default_aligned_input(role)
        else:
            st.session_state[session_key] = default_aligned_input(role)
    else:
        st.session_state[session_key] = default_aligned_input(role)

inputs = coerce_aligned_input(st.session_state[session_key])
st.session_state[session_key] = inputs
st.subheader(f"{selected} · {template_label}")

detail_key = f"sa_vehicle_detail_{selected}"
if detail_key not in st.session_state and loader is not None:
    computed_for_detail = get_computed_perf_frame(month_id)
    st.session_state[detail_key] = load_vehicle_performance_detail(
        loader,
        selected,
        eval_perf=eval_perf if eval_perf is not None else get_eval_perf_frame(month_id),
        computed_perf=computed_for_detail,
    )

with st.expander("整车绩效明细（原始数据层）", expanded=False):
    st.caption(
        "每笔订单：车型 + 渠道 + 部门 → 查提成标准 → × 台数 = 单车整车绩效；"
        "合计再乘完成率得到 Hub 整车绩效。"
        "可编辑台数、车型、渠道后点「应用到整车绩效合计」。"
    )
    if loader is None:
        st.warning("当月 Excel 不存在，无法加载订单明细")
    else:
        detail = st.session_state.get(detail_key)
        if detail is None or not detail.orders:
            st.info(f"{selected} 当月无整车订单记录")
        else:
            display = detail.to_display_frame()
            golden_cols = [c for c in display.columns if c.startswith("金标准")]
            editor = st.data_editor(
                display,
                column_config={
                    "车架号": st.column_config.TextColumn(disabled=True),
                    "订单号": st.column_config.TextColumn(disabled=True),
                    "部门": st.column_config.TextColumn(disabled=True),
                    "单车提成标准": st.column_config.NumberColumn(
                        "单车提成标准", format="%.2f", disabled=True
                    ),
                    "标准来源": st.column_config.TextColumn(disabled=True),
                    "单车整车绩效": st.column_config.NumberColumn(
                        "单车整车绩效", format="%.2f", disabled=True
                    ),
                    "台数": st.column_config.NumberColumn("台数", min_value=0.0, step=1.0),
                    "车型": st.column_config.TextColumn("车型"),
                    "渠道": st.column_config.TextColumn("渠道"),
                    **{
                        c: st.column_config.NumberColumn(c, format="%.2f", disabled=True)
                        for c in golden_cols
                    },
                },
                disabled=[c for c in display.columns if c not in EDITABLE_COLUMNS],
                hide_index=True,
                use_container_width=True,
                key=f"sa_vehicle_editor_{selected}",
            )
            recomputed = recompute_from_display_frame(
                editor,
                loader,
                golden_ag=[o.golden_ag for o in detail.orders],
            )
            recomputed.advisor_name = selected
            c_sum, c_golden, c_apply = st.columns([2, 2, 1])
            with c_sum:
                st.metric("整车绩效合计（绩效整理表）", f"{recomputed.ag_sum:,.2f}")
            with c_golden:
                if recomputed.golden_ag_sum is not None:
                    st.metric("金标准合计", f"{recomputed.golden_ag_sum:,.2f}")
            with c_apply:
                if st.button("应用到整车绩效合计", key=f"sa_apply_ag_{selected}"):
                    inputs.perf_ag_sum = recomputed.ag_sum
                    st.session_state[session_key] = inputs
                    st.session_state[detail_key] = recomputed
                    st.success(f"已更新整车绩效合计为 {recomputed.ag_sum:,.2f}")
                    st.rerun()

if loader is None:
    st.error("当月 Excel 不存在，无法复算")
    st.stop()

with st.form("sales_advisor_calc", clear_on_submit=False, enter_to_submit=False):
    with st.container(border=True):
        st.markdown("**完成率乘数**")
        if template == "store_ba":
            c1, c2 = st.columns(2)
            with c1:
                store_rate = st.number_input(
                    "店别完成率（整车用）",
                    value=float(inputs.store_completion_rate),
                    min_value=0.0,
                    step=0.01,
                    format="%.4f",
                )
            with c2:
                sales_rate = st.number_input(
                    "销量完成率（加装/保险用）",
                    value=float(inputs.sales_completion_rate),
                    min_value=0.0,
                    step=0.01,
                    format="%.4f",
                )
        else:
            sales_rate = st.number_input(
                "销量完成率",
                value=float(inputs.sales_completion_rate),
                min_value=0.0,
                step=0.01,
                format="%.4f",
            )
            store_rate = inputs.store_completion_rate

    with st.container(border=True):
        st.markdown("**绩效整理表合计（SUMIFS 来源）**")
        st.caption(
            "以下为绩效整理表 AG/AI/AJ 列按姓名求和；"
            "Hub 整车/加装/保险列 = 对应合计 × 完成率（与提成汇总 W/Y/Z 公式一致，"
            "请勿直接与 Hub 格数值对比）。"
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            ag_sum = st.number_input(
                "整车绩效合计",
                value=float(inputs.perf_ag_sum),
                step=100.0,
                help="绩效整理表按姓名汇总的整车绩效；可在上方「整车绩效明细」从订单重算后应用",
            )
        with c2:
            ai_sum = st.number_input("加装绩效合计", value=float(inputs.perf_ai_sum), step=100.0)
        with c3:
            aj_sum = st.number_input("保险绩效合计", value=float(inputs.perf_aj_sum), step=100.0)
        ins_add = 0.0
        if template == "insurance_add":
            ins_add = st.number_input(
                "保险追加常数",
                value=float(inputs.insurance_add_const),
                step=100.0,
            )

    with st.container(border=True):
        st.markdown("**绩效整理表合计（SUMIFS 直引）**")
        st.caption("权限结余绩效 Hub X 列 = AH 列按姓名汇总，不乘完成率。")
        ah_sum = st.number_input(
            "权限结余合计（AH）",
            value=float(inputs.perf_ah_sum),
            step=50.0,
        )

    with st.container(border=True):
        st.markdown("**绩效整理表合计（SUMIF 直引）**")
        st.caption(
            "金融、爱车宝、上户分项直引 Hub，不乘完成率。"
            "Hub「上户绩效」（AC 列）= AN 列 + AS 列两项之和，"
            "并非两个独立的 Hub 列。"
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            ak_sum = st.number_input("金融绩效合计（AK）", value=float(inputs.perf_ak_sum), step=50.0)
        with c2:
            am_sum = st.number_input("爱车宝绩效合计（AM）", value=float(inputs.perf_am_sum), step=50.0)
        reg_c1, reg_c2 = st.columns(2)
        with reg_c1:
            an_sum = st.number_input(
                "AN 列合计（上户分项一）",
                value=float(inputs.perf_an_sum),
                step=50.0,
                help="绩效整理表 AN 列按姓名 SUMIF，对应 Hub 上户公式第一段",
            )
        with reg_c2:
            as_sum = st.number_input(
                "AS 列合计（上户分项二）",
                value=float(inputs.perf_as_sum),
                step=50.0,
                help="绩效整理表 AS 列按姓名 SUMIF，对应 Hub 上户公式第二段",
            )
        reg_preview = registration_performance_total(
            AdvisorAlignedInput(perf_an_sum=an_sum, perf_as_sum=as_sum)
        )
        st.metric(
            "上户绩效合计 → Hub AC",
            f"{reg_preview:,.2f}",
            help="两项之和，对应提成汇总「上户绩效」列",
        )

    with st.container(border=True):
        st.markdown("**绩效整理表合计（扩展 SUMIF，AD–AI）**")
        st.caption("盈利产品、延保、特殊车型、座位险、二手车、玻碎险等直引 Hub，不乘完成率。")
        e1, e2, e3 = st.columns(3)
        with e1:
            al_sum = st.number_input("盈利产品合计（AL）", value=float(inputs.perf_al_sum), step=50.0)
            at_sum = st.number_input("延保提成合计（AT）", value=float(inputs.perf_at_sum), step=50.0)
        with e2:
            aq_sum = st.number_input("特殊车型合计（AQ）", value=float(inputs.perf_aq_sum), step=50.0)
            ao_sum = st.number_input("座位险合计（AO）", value=float(inputs.perf_ao_sum), step=50.0)
        with e3:
            ar_sum = st.number_input("二手车合计（AR）", value=float(inputs.perf_ar_sum), step=50.0)
            ap_sum = st.number_input("玻碎险合计（AP）", value=float(inputs.perf_ap_sum), step=50.0)

    form_inputs = AdvisorAlignedInput(
        sales_completion_rate=sales_rate,
        store_completion_rate=store_rate,
        insurance_add_const=ins_add if template == "insurance_add" else inputs.insurance_add_const,
        perf_ag_sum=ag_sum,
        perf_ah_sum=ah_sum,
        perf_ai_sum=ai_sum,
        perf_aj_sum=aj_sum,
        perf_ak_sum=ak_sum,
        perf_al_sum=al_sum,
        perf_am_sum=am_sum,
        perf_an_sum=an_sum,
        perf_ao_sum=ao_sum,
        perf_ap_sum=ap_sum,
        perf_aq_sum=aq_sum,
        perf_ar_sum=ar_sum,
        perf_as_sum=as_sum,
        perf_at_sum=at_sum,
    )
    preview = compute_aligned(selected, form_inputs, loader)
    gate_total = sum(preview.hub_metrics.get(c, 0.0) for c in GATE_HUB_COLUMNS)
    all_total = sum(preview.hub_metrics.get(c, 0.0) for c in ALL_HUB_COLUMNS)
    c_gate, c_all = st.columns(2)
    with c_gate:
        st.metric("预计门槛合计（六项）", f"{gate_total:,.2f}")
    with c_all:
        st.metric("预计绩效合计（十三列）", f"{all_total:,.2f}")

    submitted = st.form_submit_button("计算", type="primary", use_container_width=True)

if submitted:
    st.session_state[session_key] = form_inputs
    st.session_state[f"sa_result_{selected}"] = preview

if f"sa_result_{selected}" in st.session_state:
    result = st.session_state[f"sa_result_{selected}"]
    st.divider()
    rows = []
    golden_all = lookup_golden_hub_all(loader, selected, ALL_HUB_COLUMNS)
    for hub_col in ALL_HUB_COLUMNS:
        calc = float(result.hub_metrics.get(hub_col, 0.0))
        golden = golden_all.get(hub_col)
        delta = None if golden is None else calc - golden
        is_gate = hub_col in GATE_HUB_COLUMNS
        rows.append(
            {
                "Hub列": hub_col,
                "门槛": "是" if is_gate else "—",
                "计算值": calc,
                "金标准": golden,
                "差异": delta,
                "一致": "✓" if delta is not None and abs(delta) < 0.02 else "—",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    if result.breakdown:
        st.markdown("**分项基数**")
        st.dataframe(
            pd.DataFrame([result.breakdown]).T.rename(columns={0: "金额"}),
            use_container_width=True,
        )

    mismatches = [r for r in rows if r["差异"] is not None and abs(r["差异"]) >= 0.02]
    if not mismatches:
        st.success("十三列绩效与当月 Excel 一致")
    elif mismatches:
        st.warning(f"{len(mismatches)} 列与金标准有差异（预填后微调可验证公式）")

st.divider()
st.markdown("**保存填写记录**（供后续跑批引用，可选）")
out_dir = PROJECT_ROOT / "output" / month_id / "inputs"
out_path = out_dir / "sales_advisor_aligned_inputs.json"

if st.button("保存到 output 目录"):
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    for name in picker_names:
        key = f"sa_inputs_{name}"
        if key in st.session_state:
            payload[name] = {
                "template": template_for_role(role_by_name.get(name, {})),
                "inputs": asdict(st.session_state[key]),
            }
        res_key = f"sa_result_{name}"
        if res_key in st.session_state:
            res = st.session_state[res_key]
            entry = payload.setdefault(name, {})
            if isinstance(entry, dict):
                entry["result"] = dict(res.hub_metrics)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    st.success(f"已保存：{out_path.relative_to(PROJECT_ROOT)}")

if out_path.exists():
    st.caption(f"已有保存文件：{out_path.relative_to(PROJECT_ROOT)}")

st.info(
    "版式字段对照与灰显不适用项见侧栏 **算薪 → 字段拉通 → 销售顾问**。"
    "整车绩效可展开「整车绩效明细」查看每笔订单的计算过程；"
    "其余列的订单级下钻将陆续补齐。"
)
