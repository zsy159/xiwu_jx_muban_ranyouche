"""客户专员算薪 — 财务填写入口。"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass

import pandas as pd
import streamlit as st

from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.calculators.customer_specialist import (
    ActivityRowInput,
    BaokeMetricRow,
    BaokeStoreInput,
    CustomerSpecialistInput,
    LeftLineItemsInput,
    LineItem,
    compute_for_role,
    extract_role_inputs,
    list_roles,
    lookup_golden_cells,
)
from salary_pipeline.calculators.customer_specialist.registry import default_input_for_role
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import PROJECT_ROOT, resolve_project_path

st.set_page_config(page_title="客户专员算薪", layout="wide")
month_id = render_sidebar()

st.title("客户专员算薪")
st.caption(
    f"账期 **{month_id}** · 按「客户部提成」子表规则计算绩效，"
    "对应 Hub **整车绩效 / 权限结余绩效 / 加装绩效**（按人直引，非 SUMIF）。"
)

roles = list_roles()
role_names = [r["name"] for r in roles]
role_by_name = {r["name"]: r for r in roles}

col_pick, col_load = st.columns([2, 1])
with col_pick:
    selected = st.selectbox(
        "选择人员",
        role_names,
        format_func=lambda n: f"{n}（{role_by_name[n].get('title', '')}）",
    )
role = role_by_name[selected]
template = role["template"]

cfg = load_month_config_for(month_id)
sales_path = resolve_project_path(cfg["workbooks"]["sales"])
loader: WorkbookLoader | None = None
if sales_path.exists():
    loader = WorkbookLoader(sales_path)

session_key = f"cs_inputs_{selected}"
if col_load.button("从当月 Excel 预填", disabled=loader is None):
    if loader:
        st.session_state[session_key] = extract_role_inputs(loader, selected)
        st.success(f"已从「客户部提成」加载 {selected}")

if session_key not in st.session_state:
    if loader:
        try:
            st.session_state[session_key] = extract_role_inputs(loader, selected)
        except Exception:
            st.session_state[session_key] = default_input_for_role(role)
    else:
        st.session_state[session_key] = default_input_for_role(role)

inputs: CustomerSpecialistInput = st.session_state[session_key]

_LINE_COLS = {
    "category": "分类",
    "item_name": "项目",
    "coefficient": "系数",
    "qty_dengfang": "数量",
    "qty_zhangbaozhen": "数量",
}
_BAOKE_COLS = {
    "label": "指标",
    "metric_type": "指标类型",
    "baseline_rate": "1-3月基线",
    "actual_rate": "5月实际",
    "improvement_pct": "达成提升(%)",
    "delivery_count": "台次",
    "flat_amount": "固定金额",
}


def _cell(row: pd.Series, key: str) -> object:
    """兼容中英文列名（data_editor 回写）。"""
    cn = _LINE_COLS.get(key) or _BAOKE_COLS.get(key)
    if cn and cn in row.index:
        return row[cn]
    return row.get(key)


def _line_items_df(items: list[LineItem], person: str) -> pd.DataFrame:
    qty_key = "qty_dengfang" if person == "dengfang" else "qty_zhangbaozhen"
    rows = []
    for item in items:
        rows.append(
            {
                _LINE_COLS["category"]: item.category,
                _LINE_COLS["item_name"]: item.item_name,
                _LINE_COLS["coefficient"]: item.coefficient,
                _LINE_COLS[qty_key]: getattr(item, qty_key),
            }
        )
    return pd.DataFrame(rows)


def _df_to_line_items(df: pd.DataFrame, person: str) -> list[LineItem]:
    qty_key = "qty_dengfang" if person == "dengfang" else "qty_zhangbaozhen"
    items: list[LineItem] = []
    for _, row in df.iterrows():
        items.append(
            LineItem(
                category=str(_cell(row, "category") or ""),
                item_name=str(_cell(row, "item_name") or ""),
                coefficient=float(_cell(row, "coefficient") or 0),
                qty_dengfang=float(_cell(row, "qty_dengfang") or 0),
                qty_zhangbaozhen=float(_cell(row, "qty_zhangbaozhen") or 0),
            )
        )
    return items


def _baoke_df(metrics: list[BaokeMetricRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                _BAOKE_COLS["label"]: m.label,
                _BAOKE_COLS["metric_type"]: m.metric_type,
                _BAOKE_COLS["baseline_rate"]: m.baseline_rate,
                _BAOKE_COLS["actual_rate"]: m.actual_rate,
                _BAOKE_COLS["improvement_pct"]: m.improvement_pct,
                _BAOKE_COLS["delivery_count"]: m.delivery_count,
                _BAOKE_COLS["flat_amount"]: m.flat_amount,
            }
            for m in metrics
        ]
    )


_BAOKE_TYPE_BY_LABEL = {
    "电话回访": "phone_callback",
    "基盘客户转介绍": "referral",
    "保客挖掘置换/增购": "mining",
    "全员营销": "all_staff",
}


def _df_to_baoke(df: pd.DataFrame) -> list[BaokeMetricRow]:
    metrics: list[BaokeMetricRow] = []
    for _, row in df.iterrows():
        label = str(_cell(row, "label") or "")
        mtype = str(_cell(row, "metric_type") or "") or _BAOKE_TYPE_BY_LABEL.get(
            label, "all_staff"
        )
        metrics.append(
            BaokeMetricRow(
                metric_type=mtype,
                label=label,
                baseline_rate=_cell(row, "baseline_rate"),
                actual_rate=_cell(row, "actual_rate"),
                improvement_pct=_cell(row, "improvement_pct"),
                delivery_count=float(_cell(row, "delivery_count") or 0),
                flat_amount=float(_cell(row, "flat_amount") or 0),
            )
        )
    return metrics


st.subheader(f"{selected} · {role.get('title', '')}")

with st.form("customer_specialist_calc", clear_on_submit=False):
    form_inputs = inputs

    if inputs.left is not None:
        st.markdown("**左侧行项矩阵**")
        person = inputs.left.person
        df = _line_items_df(inputs.left.line_items, person)
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        fixed = 0.0
        if person == "zhangbaozhen":
            fixed = st.number_input(
                "整车绩效固定额（Hub W）",
                value=float(inputs.left.fixed_vehicle_performance),
                step=100.0,
            )
        form_inputs = CustomerSpecialistInput(
            template=template,
            left=LeftLineItemsInput(
                person=person,
                line_items=_df_to_line_items(edited, person),
                fixed_vehicle_performance=fixed,
            ),
            activity=inputs.activity,
            baoke=inputs.baoke,
        )

    if inputs.activity is not None:
        st.markdown("**活动合计行（周舟）**")
        act = inputs.activity
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            prospect = st.number_input("潜客回访", value=float(act.prospect_callbacks))
            five_day = st.number_input("5天新车回访", value=float(act.five_day_callbacks))
        with c2:
            thirty_day = st.number_input("30天回访", value=float(act.thirty_day_callbacks))
            defeat = st.number_input("战败回访", value=float(act.defeat_callbacks))
        with c3:
            visits = st.number_input("面访量", value=float(act.visit_count))
            groups = st.number_input("群聊量", value=float(act.group_chat_count))
        with c4:
            birthdays = st.number_input("生日关怀", value=float(act.birthday_count))
            posts = st.number_input("口碑发帖", value=float(act.reputation_posts))
        c5, c6, c7 = st.columns(3)
        with c5:
            complaint = st.number_input("投诉处理", value=float(act.complaint_handling))
        with c6:
            sat_bonus = st.number_input("满意度绩效", value=float(act.satisfaction_bonus))
        with c7:
            baoke_flat = st.number_input("保客营销（活动行）", value=float(act.baoke_marketing_flat))
        activity = ActivityRowInput(
            prospect_callbacks=prospect,
            five_day_callbacks=five_day,
            thirty_day_callbacks=thirty_day,
            defeat_callbacks=defeat,
            visit_count=visits,
            group_chat_count=groups,
            birthday_count=birthdays,
            reputation_posts=posts,
            complaint_handling=complaint,
            satisfaction_bonus=sat_bonus,
            baoke_marketing_flat=baoke_flat,
        )
        form_inputs = CustomerSpecialistInput(
            template=template,
            left=form_inputs.left,
            activity=activity,
            baoke=form_inputs.baoke,
        )

    if inputs.baoke is not None:
        st.markdown(f"**保客营销块** · {inputs.baoke.store_label}")
        bdf = _baoke_df(inputs.baoke.metrics)
        bedited = st.data_editor(
            bdf,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                _BAOKE_COLS["metric_type"]: None,
            },
        )
        form_inputs = CustomerSpecialistInput(
            template=template,
            left=form_inputs.left,
            activity=form_inputs.activity,
            baoke=BaokeStoreInput(
                store_label=inputs.baoke.store_label,
                metrics=_df_to_baoke(bedited),
            ),
        )

    submitted = st.form_submit_button("计算", type="primary", use_container_width=True)

if submitted:
    st.session_state[session_key] = form_inputs
    result = compute_for_role(selected, form_inputs)
    st.session_state[f"cs_result_{selected}"] = result

if f"cs_result_{selected}" in st.session_state:
    result = st.session_state[f"cs_result_{selected}"]
    st.divider()
    if result.hub_metrics:
        cols = st.columns(len(result.hub_metrics))
        for col, (hub_col, val) in zip(cols, result.hub_metrics.items()):
            with col:
                st.metric(f"Hub · {hub_col}", f"{val:,.2f}")
    else:
        st.metric("子表合计", f"{result.performance_salary:,.2f}")

    breakdown = result.breakdown.to_dict()
    if breakdown:
        st.markdown("**分项明细**")
        st.dataframe(
            pd.DataFrame([breakdown]).T.rename(columns={0: "金额"}),
            use_container_width=True,
        )

    if loader:
        golden = lookup_golden_cells(loader, selected)
        if golden:
            st.markdown("**与金标准核对**")
            for col, gval in golden.items():
                calc = result.hub_metrics.get(col)
                if calc is None and col == "保客合计":
                    calc = result.performance_salary
                if calc is not None:
                    delta = calc - gval
                    if abs(delta) < 0.02:
                        st.success(f"{col}：一致（{gval:,.2f}）")
                    else:
                        st.warning(f"{col}：差异 {delta:+,.2f}（金标准 {gval:,.2f}）")

st.divider()
out_dir = PROJECT_ROOT / "output" / month_id / "inputs"
out_path = out_dir / "customer_specialist_inputs.json"

if st.button("保存到 output 目录"):
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}

    def _serialize(obj: object) -> object:
        if is_dataclass(obj):
            return {f.name: _serialize(getattr(obj, f.name)) for f in fields(obj)}
        if isinstance(obj, list):
            return [_serialize(x) for x in obj]
        return obj

    for r in roles:
        key = f"cs_inputs_{r['name']}"
        if key in st.session_state:
            payload[r["name"]] = {
                "template": r["template"],
                "inputs": _serialize(st.session_state[key]),
            }
        res_key = f"cs_result_{r['name']}"
        if res_key in st.session_state:
            res = st.session_state[res_key]
            payload.setdefault(r["name"], {})["result"] = {
                "performance_salary": res.performance_salary,
                "hub_metrics": res.hub_metrics,
            }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    st.success(f"已保存：{out_path.relative_to(PROJECT_ROOT)}")

if out_path.exists():
    st.caption(f"已有保存文件：{out_path.relative_to(PROJECT_ROOT)}")

st.caption("字段版式对照请用侧栏 **算薪 → 字段拉通**（客户专员族）。")
