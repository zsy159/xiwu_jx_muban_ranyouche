"""发薪上传 — 销售账套底层数据上传、试算与正式生成。"""

from __future__ import annotations

import io
import threading
import time
import zipfile
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from salary_pipeline.app._shared import init_session_state, render_sidebar
from salary_pipeline.ingestion_upload.file_intake import (
    IntakeResult,
    SheetMatchStatus,
    discover_local_raw_workbooks,
    display_match_status,
    intake_local_raw,
    intake_uploads,
    preferred_conflict_source_index,
)
from salary_pipeline.ingestion_upload.manifest import group_manifest_by_family
from salary_pipeline.ingestion_upload.overrides import (
    apply_overrides,
    load_overrides,
    overrides_path,
    store_sheet_override,
)
from salary_pipeline.pipelines.non_frontline_columns import non_frontline_preview_columns
from salary_pipeline.ingestion_upload.promote import promote_staging
from salary_pipeline.ingestion_upload.sheet_merge import build_consolidated_workbook
from salary_pipeline.ingestion_upload.topology import (
    extract_sales_topology,
    topology_is_current,
)
from salary_pipeline.ingestion_upload.progress import (
    TrialProgressReporter,
    render_progress_markdown,
)
from salary_pipeline.ingestion_upload.trial_job import TrialJob
from salary_pipeline.ingestion_upload.trial_run import (
    ESTIMATED_FULL_MINUTES,
    ESTIMATED_INCREMENTAL_MINUTES,
    inspect_trial_cache,
    run_trial_compute,
)
from salary_pipeline.ingestion_upload.month_config import write_month_config
from salary_pipeline.paths import PROJECT_ROOT, raw_month_dir

st.set_page_config(page_title="发薪上传", layout="wide")

init_session_state()

_STATUS_ICON = {
    SheetMatchStatus.READY: "✅",
    SheetMatchStatus.MISSING: "⬜",
    SheetMatchStatus.CONFLICT: "⚠️",
    SheetMatchStatus.NOTE: "ℹ️",
}


def _get_trial_job() -> TrialJob:
    job = st.session_state.get("trial_job")
    if job is None:
        job = TrialJob()
        st.session_state.trial_job = job
    return job


def _init_upload_state() -> None:
    defaults = {
        "upload_intake": None,
        "upload_month": st.session_state.get("month_id", "2026-05"),
        "upload_month_prev": None,
        "conflict_resolutions": {},
        "consolidated_path": None,
        "topology_rel": None,
        "trial_result": None,
        "trial_job": TrialJob(),
        "promoted": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _ensure_consolidated_and_topology(
    intake: IntakeResult,
    upload_month: str,
    resolutions: dict[str, str],
    *,
    on_stage: Callable[[str], None] | None = None,
    on_progress: Callable[[str, str], None] | None = None,
) -> tuple[Path, str]:
    """Merge workbook if needed; extract topology only when workbook changed."""
    def _report(stage_key: str, label: str) -> None:
        if on_progress is not None:
            on_progress(stage_key, label)
        if on_stage is not None:
            on_stage(label)

    out = intake.staging_dir / f"销售账套-合并-{upload_month}.xlsx"
    consolidated = st.session_state.consolidated_path
    topology_rel = st.session_state.topology_rel

    if consolidated is None or not consolidated.exists():
        _report("merge_topology", "合并销售账套…")
        build_consolidated_workbook(
            intake,
            out,
            conflict_resolutions=resolutions or None,
        )
        consolidated = out
        st.session_state.consolidated_path = out

    topo_str = topology_rel or ""
    if topo_str and topology_is_current(consolidated, topo_str):
        _report("merge_topology", "拓扑未变，跳过提取…")
    else:
        _report("merge_topology", "提取公式拓扑…")
        topo_str = str(extract_sales_topology(consolidated, upload_month))
        st.session_state.topology_rel = topo_str

    return consolidated, topo_str


def _preview_trial_cache_hint(upload_month: str, topology_rel: str | None) -> str:
    """Show expected trial duration based on hub cache availability."""
    if not topology_rel:
        return f"首次全量约 {ESTIMATED_FULL_MINUTES} 分钟"
    try:
        write_month_config(
            upload_month,
            sales_workbook=f"output/{upload_month}/.staging/placeholder.xlsx",
            sales_topology=topology_rel,
            staging=True,
        )
        from salary_pipeline.ingestion_upload.month_config import (
            load_written_month_config,
        )

        cfg = load_written_month_config(upload_month)
        if st.session_state.consolidated_path and st.session_state.consolidated_path.exists():
            cfg["workbooks"]["sales"] = str(
                st.session_state.consolidated_path.relative_to(PROJECT_ROOT)
            )
        status = inspect_trial_cache(cfg)
        return status.timing_hint()
    except Exception:
        return (
            f"首次全量约 {ESTIMATED_FULL_MINUTES} 分钟；"
            f"输入未变时增量约 {ESTIMATED_INCREMENTAL_MINUTES} 分钟"
        )


def _reset_upload_flow() -> None:
    st.session_state.upload_intake = None
    st.session_state.conflict_resolutions = {}
    st.session_state.consolidated_path = None
    st.session_state.topology_rel = None
    st.session_state.trial_result = None
    _get_trial_job().reset()
    st.session_state.promoted = False


def _start_trial_compute_thread(
    job: TrialJob,
    *,
    upload_month: str,
    intake: IntakeResult,
    resolutions: dict[str, str],
    consolidated: Path,
    topology_rel: str,
) -> None:
    """Run long trial compute off the Streamlit script thread."""

    def _worker() -> None:
        try:
            def _on_progress(stage_key: str, label: str) -> None:
                job.report_progress(stage_key, label)

            trial = run_trial_compute(
                upload_month,
                consolidated,
                rules_workbook=intake.rules_workbook,
                topology_rel=topology_rel,
                sheet_sources_path=intake.sheet_sources_path,
                progress_callback=_on_progress,
                progress_reporter=job.reporter,
            )
            mode = "增量" if trial.from_stage == "hub" else "全量"
            job.mark_done(trial, completion_label=f"试算完成（{mode}）")
        except Exception as exc:
            job.mark_exception(exc)

    threading.Thread(target=_worker, daemon=True, name="trial-compute").start()


def _render_trial_job_panel(job: TrialJob) -> None:
    view = job.read_view()
    status = view["status"]
    if status == "idle":
        return

    if status == "running":
        st.warning("试算进行中请勿保存代码，以免页面重载中断试算。")

    snap = view["snapshot"]
    if snap is not None:
        st.progress(min(view["percent"], 100.0) / 100.0)
        st.markdown(render_progress_markdown(snap))

    if status == "done":
        trial = view["result"]
        if trial is not None:
            st.session_state.trial_result = trial
            mode = "增量" if trial.from_stage == "hub" else "全量"
            cache_note = trial.cache_message or ""
            if trial.cache_source:
                cache_note = f"{cache_note}（来源: {trial.cache_source}）"
            st.success(
                f"试算完成（{mode}，耗时 {trial.elapsed_seconds / 60:.1f} 分钟）。"
                + (f" {cache_note}" if cache_note else "")
                + " 请预览下方表格后确认正式生成。"
            )
    elif status == "error":
        st.error(view["error"] or "试算失败")
        if view["traceback_text"]:
            with st.expander("错误详情"):
                st.code(view["traceback_text"])


@st.fragment(run_every=timedelta(seconds=2))
def _poll_trial_job_fragment() -> None:
    """Poll background trial job; widgets must live inside the fragment body."""
    job = _get_trial_job()
    if job.read_view()["status"] == "idle":
        return
    _render_trial_job_panel(job)


_init_upload_state()

st.title("发薪上传")
st.caption("西物销售账套 · 工作表级匹配 · 试算预览 · 确认后正式生成")

sidebar_month = render_sidebar()

col_m1, col_m2 = st.columns([2, 3])
with col_m1:
    upload_month = st.text_input(
        "账期 (YYYY-MM)",
        value=st.session_state.upload_month,
        help="与 data/raw/<账期>/ 及 output/<账期>/ 对应；默认跟随侧边栏账期",
    )
    upload_month = upload_month.strip()
    st.session_state.upload_month = upload_month
    if upload_month != sidebar_month:
        st.caption(f"侧边栏当前账期：**{sidebar_month}**（与本页不同）")

prev_month = st.session_state.get("upload_month_prev")
if prev_month is not None and upload_month != prev_month:
    _reset_upload_flow()
st.session_state.upload_month_prev = upload_month

with col_m2:
    st.info(
        "上传当月底层 Excel（可多选或 ZIP）。系统按**工作表名称**匹配必需表，"
        "试算写入 `output/<账期>/.staging/`，确认后再晋升正式目录。"
    )

uploaded = st.file_uploader(
    "选择 Excel 文件",
    type=["xlsx", "zip"],
    accept_multiple_files=True,
    help="单文件 ≤80 MB，合计 ≤200 MB",
)

if uploaded and st.button("解析上传并匹配工作表", type="primary"):
    with st.spinner("正在校验并扫描工作表…"):
        pairs = [(f.name, f.getvalue()) for f in uploaded]
        intake = intake_uploads(upload_month, pairs)
        _reset_upload_flow()
        st.session_state.upload_intake = intake

with st.expander("从本地账套模拟导入", expanded=False):
    st.caption(
        "使用 `data/raw/<账期>/` 下已有的西物销售提成工作簿，"
        "走与真实上传相同的工作表匹配与 staging 流程，无需重复上传大文件。"
    )
    sim_sales, sim_rules = discover_local_raw_workbooks(upload_month)
    if sim_sales is not None:
        st.text(f"销售账套: {sim_sales.relative_to(PROJECT_ROOT)}")
    else:
        st.warning(f"`data/raw/{upload_month}/` 下未找到销售提成工作簿")
    if sim_rules is not None:
        st.text(f"提成依据: {sim_rules.relative_to(PROJECT_ROOT)}")
    include_rules = st.checkbox(
        "同时包含提成依据（试算需规则表；可能与销售账套内岗位族表冲突）",
        value=False,
        key="sim_include_rules",
    )
    if st.button("模拟导入并匹配工作表", key="sim_local_intake"):
        with st.spinner("正在从本地账套读取并匹配…"):
            intake = intake_local_raw(
                upload_month,
                include_rules_workbook=include_rules,
            )
            _reset_upload_flow()
            st.session_state.upload_intake = intake
            if not intake.errors:
                required = [m for m in intake.matches if not m.required.optional_note]
                ready = sum(
                    1
                    for m in required
                    if display_match_status(m, {})[0] == SheetMatchStatus.READY
                )
                st.success(
                    f"模拟导入完成：{ready}/{len(required)} 必需表就绪"
                    + (f"，staging: `{intake.staging_dir.relative_to(PROJECT_ROOT)}`" if intake.staging_dir else "")
                )

intake: IntakeResult | None = st.session_state.upload_intake

if intake is not None:
    if intake.errors:
        for err in intake.errors:
            st.error(err)
    else:
        if intake.month_id != upload_month:
            st.warning(
                f"当前清单来自账期 **{intake.month_id}**，与本页账期 **{upload_month}** 不一致。"
                "请重新解析上传或模拟导入。"
            )

        conflicts = [m for m in intake.matches if m.status == SheetMatchStatus.CONFLICT]
        resolutions: dict[str, str] = dict(st.session_state.conflict_resolutions)
        if conflicts:
            st.markdown("#### 冲突工作表 — 请选择来源文件")
            for match in conflicts:
                default_idx = preferred_conflict_source_index(
                    match.sources,
                    sales_workbook=intake.sales_workbook,
                )
                choice = st.selectbox(
                    f"「{match.required.name}」来源",
                    match.sources,
                    index=default_idx,
                    key=f"conflict_{match.required.name}",
                )
                resolutions[match.required.name] = choice
            st.session_state.conflict_resolutions = resolutions

        st.subheader("底层数据就绪清单")
        match_by_name = {m.required.name: m for m in intake.matches}
        for family_label, sheets in group_manifest_by_family():
            st.markdown(f"**{family_label}**")
            rows = []
            for sheet in sheets:
                match = match_by_name.get(sheet.name)
                if match is None:
                    continue
                display_status, display_sources = display_match_status(
                    match, resolutions
                )
                icon = _STATUS_ICON.get(display_status, "•")
                source = "、".join(display_sources) if display_sources else "—"
                note = ""
                if sheet.optional_note:
                    note = "（公式表，非必需输入）"
                roles = "、".join(sheet.families)
                rows.append(
                    {
                        "状态": icon,
                        "工作表": sheet.name + note,
                        "岗位族": roles,
                        "来源文件": source,
                        "header_row": sheet.header_row,
                    }
                )
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        if intake.warnings:
            for warn in intake.warnings:
                st.warning(warn)

        ready = intake.can_proceed(resolutions)
        blockers = intake.proceed_blockers(resolutions)

        trial_job = _get_trial_job()
        trial_running = trial_job.is_running()
        if trial_job.read_view()["status"] != "idle":
            _poll_trial_job_fragment()

        c1, c2, c3 = st.columns(3)
        with c1:
            build_btn = st.button(
                "合并为销售账套",
                disabled=not ready or trial_running,
                help="将全部必需工作表合并到单一 xlsx",
            )
        with c2:
            trial_btn = st.button(
                "试算（预览）",
                disabled=not ready or trial_running,
                help=(
                    f"SalesPipeline 试算；首次全量约 {ESTIMATED_FULL_MINUTES} 分钟，"
                    f"输入未变时增量约 {ESTIMATED_INCREMENTAL_MINUTES} 分钟"
                ),
            )
        with c3:
            promote_btn = st.button(
                "确认并正式生成",
                disabled=st.session_state.trial_result is None,
                type="primary",
            )

        topology_rel: str | None = st.session_state.topology_rel
        if ready:
            st.caption(_preview_trial_cache_hint(upload_month, topology_rel))

        if not ready and blockers:
            st.info("当前不可试算：" + "；".join(blockers))
        elif st.session_state.trial_result is None:
            st.caption("完成试算预览后，方可「确认并正式生成」。")

        if build_btn and ready:
            with st.spinner("正在合并工作表…"):
                out = intake.staging_dir / f"销售账套-合并-{upload_month}.xlsx"
                try:
                    build_consolidated_workbook(
                        intake,
                        out,
                        conflict_resolutions=resolutions or None,
                    )
                    st.session_state.consolidated_path = out
                    existing_topo = st.session_state.topology_rel
                    if existing_topo and topology_is_current(out, existing_topo):
                        st.session_state.topology_rel = existing_topo
                    else:
                        st.session_state.topology_rel = str(
                            extract_sales_topology(out, upload_month)
                        )
                    st.success(f"已合并: `{out.relative_to(PROJECT_ROOT)}`")
                except Exception as exc:
                    st.error(f"合并失败: {exc}")

        consolidated: Path | None = st.session_state.consolidated_path
        topology_rel = st.session_state.topology_rel

        if trial_btn and ready and not trial_running:
            reporter = TrialProgressReporter(mode="full")
            st.session_state.trial_result = None
            trial_job.start(reporter)
            st.session_state.trial_start_time = time.perf_counter()

            def _on_merge_progress(stage_key: str, label: str) -> None:
                trial_job.report_progress(stage_key, label)

            try:
                consolidated, topology_rel = _ensure_consolidated_and_topology(
                    intake,
                    upload_month,
                    resolutions,
                    on_progress=_on_merge_progress,
                )
            except Exception as exc:
                trial_job.mark_exception(exc)
            else:
                _start_trial_compute_thread(
                    trial_job,
                    upload_month=upload_month,
                    intake=intake,
                    resolutions=resolutions,
                    consolidated=consolidated,
                    topology_rel=topology_rel,
                )
            st.rerun()

        trial = st.session_state.trial_result
        if trial is not None and not trial.errors:
            st.subheader("试算预览")
            tab1, tab2 = st.tabs(["提成汇总", "绩效整理表"])
            with tab1:
                if not trial.summary_preview.empty:
                    nf_help = (
                        "非一线语义列：管理区块 W/Y→岗位/业绩绩效；"
                        "支持部门 M–Z 子表头（售后总产值、台次、提成系数等）"
                    )
                    nf_column_config = {
                        col: st.column_config.NumberColumn(
                            col,
                            help=nf_help,
                            format="%.2f",
                        )
                        for col in non_frontline_preview_columns()
                        if col in trial.summary_preview.columns
                    }
                    edited_summary = st.data_editor(
                        trial.summary_preview,
                        column_config=nf_column_config or None,
                        num_rows="fixed",
                        use_container_width=True,
                        key="editor_summary",
                    )
                    if st.button("保存提成汇总修改", key="save_summary"):
                        store_sheet_override(
                            overrides_path(trial.staging_dir),
                            "提成汇总",
                            edited_summary,
                        )
                        st.toast("已写入 overrides.json")
            with tab2:
                if not trial.performance_preview.empty:
                    edited_perf = st.data_editor(
                        trial.performance_preview,
                        num_rows="fixed",
                        use_container_width=True,
                        key="editor_perf",
                    )
                    if st.button("保存绩效整理表修改", key="save_perf"):
                        store_sheet_override(
                            overrides_path(trial.staging_dir),
                            "绩效整理表",
                            edited_perf,
                        )
                        st.toast("已写入 overrides.json")

        if promote_btn and trial is not None and consolidated is not None:
            with st.spinner("正在归档并晋升正式目录…"):
                originals = [uf.path for uf in intake.uploads]
                promoted = promote_staging(
                    upload_month,
                    staging_dir=trial.staging_dir,
                    consolidated_workbook=consolidated,
                    original_uploads=originals,
                    rules_workbook=intake.rules_workbook,
                    topology_rel=topology_rel or "",
                )
                st.session_state.promoted = True
                st.success("已正式生成并注册账期")
                for label, path in promoted.items():
                    st.caption(f"{label}: `{path.relative_to(PROJECT_ROOT)}`")

        if st.session_state.promoted or (
            trial is not None and trial.commission_summary_path
        ):
            st.subheader("导出")
            export_cols = st.columns(2)
            staging = trial.staging_dir if trial else raw_month_dir(upload_month) / ".staging"
            ov_path = overrides_path(staging)
            overrides = load_overrides(ov_path)

            if trial and trial.commission_summary_path and trial.commission_summary_path.exists():
                summary_df = pd.read_excel(
                    trial.commission_summary_path,
                    sheet_name="提成汇总",
                    header=1,
                )
                summary_df = apply_overrides(summary_df, "提成汇总", overrides)
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    summary_df.to_excel(writer, sheet_name="提成汇总", index=False)
                export_cols[0].download_button(
                    "下载提成汇总",
                    buf.getvalue(),
                    file_name=f"提成汇总-{upload_month}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

            if trial and trial.performance_sheet_path and trial.performance_sheet_path.exists():
                perf_df = pd.read_excel(
                    trial.performance_sheet_path,
                    sheet_name="绩效整理表",
                    header=1,
                )
                perf_df = apply_overrides(perf_df, "绩效整理表", overrides)
                buf2 = io.BytesIO()
                with pd.ExcelWriter(buf2, engine="openpyxl") as writer:
                    perf_df.to_excel(writer, sheet_name="绩效整理表", index=False)
                export_cols[1].download_button(
                    "下载绩效整理表",
                    buf2.getvalue(),
                    file_name=f"绩效整理表-{upload_month}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

            if (
                trial
                and trial.commission_summary_path
                and trial.performance_sheet_path
                and trial.commission_summary_path.exists()
                and trial.performance_sheet_path.exists()
            ):
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(
                        trial.commission_summary_path,
                        arcname=trial.commission_summary_path.name,
                    )
                    zf.write(
                        trial.performance_sheet_path,
                        arcname=trial.performance_sheet_path.name,
                    )
                st.download_button(
                    "下载 ZIP（提成汇总 + 绩效整理表）",
                    zip_buf.getvalue(),
                    file_name=f"发薪产出-{upload_month}.zip",
                    mime="application/zip",
                )

with st.expander("必需底层数据表说明"):
    for family_label, sheets in group_manifest_by_family():
        st.markdown(f"**{family_label}**")
        for sheet in sheets:
            roles = "、".join(sheet.families)
            if sheet.optional_note:
                st.markdown(
                    f"- **{sheet.name}** — 公式表（若上传则标注，非必需）· 岗位族: {roles}"
                )
            else:
                st.markdown(
                    f"- **{sheet.name}** — header_row={sheet.header_row} · "
                    f"来源: {sheet.source} · 岗位族: {roles}"
                )
