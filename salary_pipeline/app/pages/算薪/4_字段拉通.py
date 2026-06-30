"""岗位字段拉通 — 跨版式统一字段视图（不适用项留空标记）。"""

from __future__ import annotations

import json
from dataclasses import asdict

import pandas as pd
import streamlit as st

from salary_pipeline.app._matrix_view import render_grouped_alignment_matrix
from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.calculators.field_alignment.runtime import get_family_runtime
from salary_pipeline.calculators.field_alignment.schema import (
    list_alignment_families,
    load_alignment_family,
)
from salary_pipeline.calculators.invite_specialist.registry import hub_column_for_role
from salary_pipeline.app._pipeline_cache import get_workbook_loader
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import PROJECT_ROOT, resolve_project_path

st.set_page_config(page_title="岗位字段拉通", layout="wide")
month_id = render_sidebar()

st.title("岗位字段拉通")
st.caption(
    f"账期 **{month_id}** · 按岗位族展示**全部**算薪字段；"
    "当前版式无对应子表列时**留空并标记不适用**，便于跨主体对照与后续岗位扩展。"
)

families = list_alignment_families()
if not families:
    st.error("未找到字段拉通配置（config/role_field_alignment/）")
    st.stop()

family_labels = {fid: label for fid, label in families}
family_id = st.selectbox(
    "岗位族",
    list(family_labels.keys()),
    format_func=lambda fid: family_labels[fid],
)

alignment = load_alignment_family(family_id)
try:
    runtime = get_family_runtime(family_id)
except KeyError:
    st.warning("该岗位族拉通界面尚未实现。")
    st.stop()

roles = runtime.list_roles()
role_by_name = {r["name"]: r for r in roles}
role_names = [r["name"] for r in roles]

col_pick, col_load, col_tpl = st.columns([2, 1, 1])
with col_pick:
    selected = st.selectbox(
        "选择人员",
        role_names,
        format_func=lambda n: runtime.role_format(role_by_name[n], alignment),
    )
role = role_by_name[selected]
template = role["template"]
template_label = alignment.templates.get(template, {}).get("label", template)

with col_tpl:
    st.metric("当前版式", template_label)

cfg = load_month_config_for(month_id)
sales_path = resolve_project_path(cfg["workbooks"]["sales"])
loader: WorkbookLoader | None = get_workbook_loader(month_id) if sales_path.exists() else None

session_key = f"align_inputs_{family_id}_{selected}"
if col_load.button("从当月 Excel 预填", disabled=loader is None):
    if loader:
        st.session_state[session_key] = runtime.extract_role_inputs(loader, selected)
        st.success(f"已从「{alignment.rules_sheet}」加载 {selected}")

if session_key not in st.session_state:
    if loader and runtime.eager_extract:
        try:
            st.session_state[session_key] = runtime.extract_role_inputs(loader, selected)
        except Exception:
            st.session_state[session_key] = runtime.default_input_for_role(role)
    else:
        st.session_state[session_key] = runtime.default_input_for_role(role)

st.session_state[session_key] = runtime.coerce_inputs(
    st.session_state[session_key], template
)
inputs = st.session_state[session_key]
value_map = runtime.values_from_inputs(inputs)

with st.expander("版式字段对照表（字段为列、版式为行）", expanded=True):
    matrix = runtime.applicability_matrix_wide(alignment)
    st.caption("分组表头对照；在表格区域底部拖动**灰色横向滚动条**浏览全部字段。")
    render_grouped_alignment_matrix(matrix)

hub_note = (
    f"Hub：**{hub_column_for_role(role)}**"
    if family_id == "invite_specialist"
    else f"Hub：**{runtime.hub_label}**"
)
st.subheader(f"{selected} · {template_label}")
st.caption(
    f"子表：**{alignment.rules_sheet}** · {hub_note} · "
    "灰显字段为本版式子表无对应列，保留占位便于拉通。"
)

updates: dict[str, object] = {}

if family_id == "customer_specialist" and template in ("left_line_items", "left_and_baoke"):
    updates["left_person"] = role.get("person_column", "dengfang")

if not runtime.supports_alignment_form:
    st.info("客户专员左侧行项较多，详细填写请使用侧边栏 **客户专员算薪** 页；此处展示对照表与金标准核对。")
    preview = runtime.compute_for_role(selected, inputs)
    if preview.hub_metrics:
        for col, val in preview.hub_metrics.items():
            st.metric(f"Hub · {col}", f"{val:,.2f}")
    else:
        st.metric("子表合计", f"{preview.performance_salary:,.2f}")
    if loader:
        golden = runtime.lookup_golden(loader, selected)
        if isinstance(golden, dict) and golden:
            st.markdown("**与金标准 hub 列核对**")
            for col, gval in golden.items():
                calc = preview.hub_metrics.get(col, preview.performance_salary if col == "保客合计" else None)
                if calc is None and col == "保客合计":
                    calc = preview.performance_salary
                if calc is not None:
                    delta = calc - gval
                    if abs(delta) < 0.02:
                        st.success(f"{col}：一致（{gval:,.2f}）")
                    else:
                        st.warning(f"{col}：差异 {delta:+,.2f}（金标准 {gval:,.2f}）")
else:
    with st.form("aligned_fields", clear_on_submit=False, enter_to_submit=False):
        for section in alignment.sections:
            with st.container(border=True):
                st.markdown(f"**{section.label}**")
                if section.section_note:
                    st.caption(section.section_note)

                for field_def in section.fields:
                    if field_def.matrix_only or not field_def.input_attr:
                        continue

                    applicable = runtime.is_field_applicable(field_def, template)
                    label = runtime.field_label_for_template(field_def, template)
                    attr = field_def.input_attr

                    if not applicable:
                        c1, c2 = st.columns([2, 1])
                        with c1:
                            st.markdown(f"{label} `不适用`")
                            st.caption(runtime.not_applicable_reason(field_def, template))
                        with c2:
                            st.text_input(
                                label,
                                value="",
                                disabled=True,
                                key=f"align_na_{family_id}_{selected}_{field_def.id}",
                            )
                        continue

                    if field_def.value_type == "line_item":
                        attr = field_def.input_attr
                        ar_key = f"{attr}_achievement_rate"
                        coef_key = f"{attr}_coefficient"
                        qd_key = f"{attr}_qty_dengfang"
                        qz_key = f"{attr}_qty_zhangbaozhen"
                        person = role.get("person_column") or value_map.get(
                            "left_person", "dengfang"
                        )
                        ar_val = value_map.get(ar_key)
                        coef_val = float(value_map.get(coef_key, 0) or 0)
                        qd_val = float(value_map.get(qd_key, 0) or 0)
                        qz_val = float(value_map.get(qz_key, 0) or 0)
                        st.markdown(f"**{label}**")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            updates[ar_key] = st.number_input(
                                "达成率",
                                value=float(ar_val) if ar_val is not None else 0.0,
                                step=0.0001,
                                format="%.4f",
                                key=f"align_{family_id}_{selected}_{field_def.id}_ar",
                            )
                        with c2:
                            updates[coef_key] = st.number_input(
                                "系数",
                                value=coef_val,
                                step=0.01,
                                format="%.4f",
                                key=f"align_{family_id}_{selected}_{field_def.id}_c",
                            )
                        with c3:
                            if person == "dengfang":
                                updates[qd_key] = st.number_input(
                                    "数量",
                                    value=qd_val,
                                    min_value=0.0,
                                    step=1.0,
                                    key=f"align_{family_id}_{selected}_{field_def.id}_qd",
                                )
                            else:
                                updates[qz_key] = st.number_input(
                                    "数量",
                                    value=qz_val,
                                    min_value=0.0,
                                    step=1.0,
                                    key=f"align_{family_id}_{selected}_{field_def.id}_qz",
                                )
                        subtotal = coef_val * (qd_val if person == "dengfang" else qz_val)
                        st.caption(f"小计：{subtotal:,.2f}")
                        continue

                    if field_def.value_type == "baoke_metric":
                        current = value_map.get(attr)
                        if current is None:
                            val = 0.0
                        else:
                            val = float(current or 0)
                        updates[attr] = st.number_input(
                            label,
                            value=val,
                            step=0.0001 if "rate" in attr or "pct" in attr else 1.0,
                            format="%.4f" if "rate" in attr or "pct" in attr else "%.2f",
                            key=f"align_{family_id}_{selected}_{field_def.id}",
                        )
                        continue

                    if field_def.value_type == "metric_pair":
                        t_key = f"{attr}_target"
                        a_key = f"{attr}_actual"
                        c1, c2 = st.columns(2)
                        with c1:
                            updates[t_key] = st.number_input(
                                f"{label} · 目标",
                                value=float(value_map.get(t_key, 0) or 0),
                                min_value=0.0,
                                step=1.0,
                                key=f"align_{family_id}_{selected}_{field_def.id}_t",
                            )
                        with c2:
                            updates[a_key] = st.number_input(
                                f"{label} · 实际",
                                value=float(value_map.get(a_key, 0) or 0),
                                min_value=0.0,
                                step=1.0,
                                key=f"align_{family_id}_{selected}_{field_def.id}_a",
                            )
                        continue

                    current = value_map.get(attr)

                    if field_def.value_type == "checkbox":
                        updates[attr] = st.checkbox(
                            label,
                            value=bool(current),
                            key=f"align_{family_id}_{selected}_{field_def.id}",
                        )
                    else:
                        step = 1.0
                        if attr.endswith("_count"):
                            step = 1.0
                        elif "rate" in attr or "bonus" in attr or "penalty" in attr:
                            step = 1.0
                        else:
                            step = 10.0
                        if attr == "kpi_base":
                            step = 100.0
                        updates[attr] = st.number_input(
                            label,
                            value=float(current or 0),
                            step=step,
                            key=f"align_{family_id}_{selected}_{field_def.id}",
                        )

        form_inputs = runtime.inputs_from_values(inputs, updates, template)
        preview = runtime.compute_for_role(selected, form_inputs)
        if family_id == "customer_specialist":
            if preview.hub_metrics:
                st.metric(
                    "预计 Hub 绩效",
                    ", ".join(f"{k} {v:,.2f}" for k, v in preview.hub_metrics.items()),
                )
            else:
                st.metric("预计子表合计", f"{preview.performance_salary:,.2f}")
        else:
            st.metric("预计总绩效", f"{preview.hub_vehicle_performance:,.2f}")
        submitted = st.form_submit_button("计算并暂存", type="primary", use_container_width=True)

    if submitted:
        st.session_state[session_key] = form_inputs
        st.session_state[f"align_result_{family_id}_{selected}"] = preview

    result_key = f"align_result_{family_id}_{selected}"
    if result_key in st.session_state:
        result = st.session_state[result_key]
        st.divider()
        bd = result.breakdown
        breakdown = bd.to_dict() if hasattr(bd, "to_dict") and not isinstance(bd, dict) else bd
        if breakdown:
            st.markdown("**分项明细（仅含本版式有效项）**")
            st.dataframe(
                pd.DataFrame([breakdown]).T.rename(columns={0: "金额"}),
                use_container_width=True,
            )
        if loader:
            golden = runtime.lookup_golden(loader, selected)
            if golden is not None and not isinstance(golden, dict):
                delta = result.hub_vehicle_performance - golden
                if abs(delta) < 0.02:
                    st.success(f"与当月 Excel 子表一致（{golden:,.2f}）")
                else:
                    st.warning(f"与金标准差异 {delta:+,.2f}（{golden:,.2f}）")

st.divider()
st.markdown("**保存拉通填写记录**")
out_dir = PROJECT_ROOT / "output" / month_id / "inputs"
out_path = out_dir / runtime.save_filename

if st.button("保存到 output 目录"):
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    for r in roles:
        key = f"align_inputs_{family_id}_{r['name']}"
        if key in st.session_state:
            raw_inputs = st.session_state[key]
            if isinstance(raw_inputs, list):
                inputs_payload = [asdict(x) for x in raw_inputs]
            else:
                inputs_payload = asdict(raw_inputs)
            entry: dict[str, object] = {
                "template": r["template"],
                "inputs": inputs_payload,
                "alignment_family": family_id,
            }
            if family_id == "invite_specialist":
                entry["company"] = r.get("company")
            else:
                entry["title"] = r.get("title")
            payload[r["name"]] = entry
        res_key = f"align_result_{family_id}_{r['name']}"
        if res_key in st.session_state:
            res = st.session_state[res_key]
            existing = payload.setdefault(r["name"], {})
            if isinstance(existing, dict):
                existing["result"] = {
                    "performance_salary": res.performance_salary,
                    "hub_vehicle_performance": res.hub_vehicle_performance,
                }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    st.success(f"已保存：{out_path.relative_to(PROJECT_ROOT)}")

if out_path.exists():
    st.caption(f"已有保存文件：{out_path.relative_to(PROJECT_ROOT)}")

st.info(
    "在 `config/role_field_alignment/` 增加 YAML 并在 `field_alignment/runtime.py` 注册即可扩展岗位族；"
    "版式专用算薪在侧栏 **算薪** 分组；对账类功能见顶层菜单。"
)
