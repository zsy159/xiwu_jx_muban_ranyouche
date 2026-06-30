"""新媒体算薪 — 财务填写入口。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.calculators.new_media import (
    LiveAnchorInput,
    ManualPerformanceInput,
    MetricPair,
    OpsManagerInput,
    VideoOpsInput,
    compute_for_role,
    extract_role_inputs,
    list_roles,
    lookup_golden_ab,
)
from salary_pipeline.data_ingestion.data_loader import WorkbookLoader
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.paths import PROJECT_ROOT, resolve_project_path

st.set_page_config(page_title="新媒体算薪", layout="wide")
month_id = render_sidebar()

st.title("新媒体算薪")
st.caption(
    f"账期 **{month_id}** · 按「新媒体」子表规则从目标/实际填写项计算 **绩效薪资**，"
    "对应 Hub **整车绩效（W 列）**。"
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

if col_load.button("从当月 Excel 预填", disabled=loader is None):
    if loader:
        st.session_state[f"nm_inputs_{selected}"] = extract_role_inputs(
            loader, selected
        )
        st.success(f"已从「新媒体」子表加载 {selected} 的数据")

session_key = f"nm_inputs_{selected}"
if session_key not in st.session_state:
    if loader:
        try:
            st.session_state[session_key] = extract_role_inputs(loader, selected)
        except Exception:
            from salary_pipeline.calculators.new_media.registry import (
                default_input_for_role,
            )

            st.session_state[session_key] = default_input_for_role(role)
    else:
        from salary_pipeline.calculators.new_media.registry import default_input_for_role

        st.session_state[session_key] = default_input_for_role(role)

inputs = st.session_state[session_key]


def _metric_pair_ui(label: str, pair: MetricPair, key: str) -> MetricPair:
    prefix = f"{selected}_{key}"
    c1, c2 = st.columns(2)
    with c1:
        target = st.number_input(
            f"{label} · 目标",
            value=float(pair.target),
            min_value=0.0,
            step=1.0,
            key=f"{prefix}_t",
        )
    with c2:
        actual = st.number_input(
            f"{label} · 实际",
            value=float(pair.actual),
            min_value=0.0,
            step=1.0,
            key=f"{prefix}_a",
        )
    return MetricPair(target=target, actual=actual)


st.subheader(f"{selected} · {role.get('title', '')}")

with st.form("new_media_calc", clear_on_submit=False, enter_to_submit=False):
    if template == "live_anchor":
        st.markdown("**考核指标（目标 / 实际）**")
        c1, c2 = st.columns(2)
        with c1:
            live = _metric_pair_ui("直播场次", inputs.live_sessions, "live")
            leads = _metric_pair_ui("直播线索", inputs.leads, "leads")
        with c2:
            fans = _metric_pair_ui("粉丝关注", inputs.fans, "fans")
            videos = _metric_pair_ui("视频发布", inputs.videos, "videos")

        c3, c4, c5 = st.columns(3)
        with c3:
            kpi_base = st.number_input(
                "岗位绩效 KPI 基数",
                value=float(inputs.kpi_base),
                min_value=0.0,
                step=100.0,
            )
        with c4:
            terminal_rate = st.number_input(
                "终端提成单价（元/台）",
                value=float(inputs.terminal_unit_rate),
                min_value=0.0,
                step=10.0,
            )
        with c5:
            terminal_count = st.number_input(
                "终端完成台数",
                value=float(inputs.terminal_count),
                min_value=0.0,
                step=1.0,
            )

        c6, c7 = st.columns(2)
        with c6:
            lead_rate = st.number_input(
                "线索超额单价（元/条）",
                value=float(inputs.lead_excess_unit_rate),
                min_value=0.0,
                step=1.0,
            )
        with c7:
            session_rate = st.number_input(
                "场次超额单价（元/场）",
                value=float(inputs.session_excess_unit_rate),
                min_value=0.0,
                step=10.0,
            )
        track_sessions = st.checkbox(
            "计入场次超额奖励（部分主播适用）",
            value=bool(inputs.track_session_excess),
        )

        form_inputs = LiveAnchorInput(
            live_sessions=live,
            leads=leads,
            fans=fans,
            videos=videos,
            kpi_base=kpi_base,
            terminal_unit_rate=terminal_rate,
            terminal_count=terminal_count,
            lead_excess_unit_rate=lead_rate,
            session_excess_unit_rate=session_rate,
            track_session_excess=track_sessions,
        )

    elif template == "video_ops":
        st.markdown("**考核指标（目标 / 实际）**")
        c1, c2 = st.columns(2)
        with c1:
            videos = _metric_pair_ui("视频发布数", inputs.videos, "vid")
            plays = _metric_pair_ui("播放量", inputs.play_count, "play")
        with c2:
            fans = _metric_pair_ui("短视频粉丝", inputs.short_video_fans, "sf")
            xhs = _metric_pair_ui("小红书笔记", inputs.xiaohongshu, "xhs")

        c3, c4, c5 = st.columns(3)
        with c3:
            kpi_base = st.number_input("岗位绩效 KPI 基数", value=float(inputs.kpi_base))
        with c4:
            terminal_rate = st.number_input(
                "终端提成单价", value=float(inputs.terminal_unit_rate)
            )
        with c5:
            terminal_count = st.number_input(
                "终端完成台数", value=float(inputs.terminal_count)
            )

        c6, c7 = st.columns(2)
        with c6:
            quality_rate = st.number_input(
                "优质视频单价", value=float(inputs.quality_video_unit_rate)
            )
            quality_count = st.number_input(
                "优质视频条数", value=float(inputs.quality_video_count)
            )
        with c7:
            excess_rate = st.number_input(
                "超额视频单价", value=float(inputs.excess_video_unit_rate)
            )

        form_inputs = VideoOpsInput(
            videos=videos,
            play_count=plays,
            short_video_fans=fans,
            xiaohongshu=xhs,
            kpi_base=kpi_base,
            terminal_unit_rate=terminal_rate,
            terminal_count=terminal_count,
            quality_video_unit_rate=quality_rate,
            quality_video_count=quality_count,
            excess_video_unit_rate=excess_rate,
        )

    elif template == "ops_manager":
        st.markdown("**考核指标（目标 / 实际）**")
        c1, c2 = st.columns(2)
        with c1:
            live = _metric_pair_ui("直播场次", inputs.live_sessions, "om_live")
            videos = _metric_pair_ui("视频创作", inputs.video_creations, "om_vid")
        with c2:
            leads = _metric_pair_ui("线索量", inputs.leads, "om_lead")
            visits = _metric_pair_ui("邀约到店", inputs.store_visits, "om_visit")

        c3, c4, c5 = st.columns(3)
        with c3:
            kpi_base = st.number_input("岗位绩效 KPI 基数", value=float(inputs.kpi_base))
        with c4:
            terminal_rate = st.number_input(
                "终端提成单价", value=float(inputs.terminal_unit_rate)
            )
        with c5:
            terminal_count = st.number_input(
                "终端完成台数", value=float(inputs.terminal_count)
            )

        form_inputs = OpsManagerInput(
            live_sessions=live,
            video_creations=videos,
            leads=leads,
            store_visits=visits,
            kpi_base=kpi_base,
            terminal_unit_rate=terminal_rate,
            terminal_count=terminal_count,
        )

    else:
        form_inputs = ManualPerformanceInput(
            performance_salary=st.number_input(
                "整车绩效 / 绩效薪资（手工录入）",
                value=float(inputs.performance_salary),
                min_value=0.0,
                step=100.0,
            )
        )

    submitted = st.form_submit_button("计算", type="primary", use_container_width=True)

if submitted:
    st.session_state[session_key] = form_inputs
    result = compute_for_role(selected, form_inputs)
    st.session_state[f"nm_result_{selected}"] = result

if f"nm_result_{selected}" in st.session_state:
    result = st.session_state[f"nm_result_{selected}"]
    st.divider()
    m1, m2 = st.columns(2)
    with m1:
        st.metric("绩效薪资（子表 Q）", f"{result.performance_salary:,.2f}")
    with m2:
        st.metric("Hub 整车绩效（W）", f"{result.hub_vehicle_performance:,.2f}")

    breakdown = {k: v for k, v in result.breakdown.to_dict().items() if v}
    if breakdown:
        st.markdown("**分项明细**")
        st.dataframe(
            pd.DataFrame([breakdown]).T.rename(columns={0: "金额"}),
            use_container_width=True,
        )

    if loader:
        golden = lookup_golden_ab(loader, selected)
        if golden is not None:
            delta = result.hub_vehicle_performance - golden
            if abs(delta) < 0.02:
                st.success(f"与当月 Excel AB 列一致（{golden:,.2f}）")
            else:
                st.warning(
                    f"与当月 Excel AB 列差异 {delta:+,.2f}（金标准 {golden:,.2f}）"
                )

st.divider()
st.markdown("**保存填写记录**（供后续跑批引用，可选）")
out_dir = PROJECT_ROOT / "output" / month_id / "inputs"
out_path = out_dir / "new_media_inputs.json"

if st.button("保存到 output 目录"):
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    for r in roles:
        key = f"nm_inputs_{r['name']}"
        if key in st.session_state:
            from dataclasses import asdict

            payload[r["name"]] = {
                "template": r["template"],
                "inputs": asdict(st.session_state[key]),
            }
        res_key = f"nm_result_{r['name']}"
        if res_key in st.session_state:
            res = st.session_state[res_key]
            payload.setdefault(r["name"], {})["result"] = {
                "performance_salary": res.performance_salary,
                "hub_vehicle_performance": res.hub_vehicle_performance,
            }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    st.success(f"已保存：{out_path.relative_to(PROJECT_ROOT)}")

if out_path.exists():
    st.caption(f"已有保存文件：{out_path.relative_to(PROJECT_ROOT)}")
