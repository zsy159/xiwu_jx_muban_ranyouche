"""新月接入 — 上传销售账套并一键注册账期配置。"""

from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path

import streamlit as st

from salary_pipeline.app._shared import init_session_state, render_sidebar
from salary_pipeline.app.onboard_helpers import (
    RULE_CANONICAL,
    RULE_EXTRACT,
    RULE_INHERIT,
    UPLOAD_MODE_FULL,
    UPLOAD_MODE_SHEETS,
    default_label_for_month,
    default_rule_mode_label,
    list_inherit_source_months,
    prepare_onboard_from_sheet_uploads,
    sales_relative_path,
    save_sales_workbook,
    validate_month_id,
)
from salary_pipeline.ingestion_upload.file_intake import (
    STREAMLIT_UPLOAD_ACCEPT,
    pairs_from_streamlit_files,
)
from salary_pipeline.ingestion_upload.manifest import (
    FAMILY_SALES,
    group_manifest_by_family,
)
from salary_pipeline.main import cmd_onboard_month
from salary_pipeline.paths import CONFIG_DIR, PROJECT_ROOT

st.set_page_config(page_title="新月接入", layout="wide")

init_session_state()
render_sidebar()

st.title("新月接入")
st.caption("上传销售账套 · 一键生成 month 配置并注册账期")

st.info(
    "支持**整本账套**或**分表上传**。分表模式按工作表名称匹配底层明细，"
    "保存至 `data/raw/<账期>/uploads/` 并合并为销售账套。"
    "计算规则默认使用 repo 内 **2026-05 固化公式拓扑**，仅绑定当月数据路径。"
)

st.subheader("基础信息")
col1, col2 = st.columns(2)
with col1:
    month_id = st.text_input(
        "账期 (YYYY-MM)",
        value="",
        placeholder="2026-07",
        help="与 data/raw/<账期>/ 及 output/<账期>/ 对应",
    )
with col2:
    label_default = default_label_for_month(month_id) if month_id.strip() else ""
    label = st.text_input(
        "显示名称",
        value=label_default,
        placeholder="2026年07月",
        help="写入 months_registry 的中文标签",
    )

st.subheader("销售数据上传")
upload_mode = st.radio(
    "上传方式",
    options=[UPLOAD_MODE_FULL, UPLOAD_MODE_SHEETS],
    format_func=lambda m: {
        UPLOAD_MODE_FULL: "整本账套（单个 .xlsx）",
        UPLOAD_MODE_SHEETS: "分表上传（多个 .xlsx / ZIP，按工作表名匹配）",
    }[m],
    horizontal=True,
)

# file_uploader 必须放在 st.form 外，否则 macOS 无法多选且 ZIP 类型受限（与「发薪上传」一致）。
sales_file = None
sheet_files: list = []
if upload_mode == UPLOAD_MODE_FULL:
    sales_file = st.file_uploader(
        "销售账套 (.xlsx)",
        type=["xlsx"],
        help="保存至 data/raw/<账期>/；建议使用合并后的销售账套",
    )
else:
    sheet_files = st.file_uploader(
        "底层 Excel / ZIP 文件",
        type=STREAMLIT_UPLOAD_ACCEPT,
        accept_multiple_files=True,
        help="可多选 .xlsx 或 .zip；单文件 ≤80 MB，合计 ≤200 MB；按工作表名称匹配必需表",
    )
    st.caption(
        "每个文件可含一张或多张工作表；系统会自动合并为 "
        "`销售账套-合并-<账期>.xlsx`， supplemental 表写入 `uploads/`。"
    )

st.subheader("规则来源")
_canonical_label = default_rule_mode_label()
rule_mode = st.radio(
    "拓扑与规则如何确定？",
    options=[RULE_CANONICAL, RULE_EXTRACT, RULE_INHERIT],
    format_func=lambda m: {
        RULE_CANONICAL: f"✅ 使用系统固化规则（{_canonical_label}）",
        RULE_EXTRACT: "⚙️ 从新表提取规则（高级：重建样板拓扑）",
        RULE_INHERIT: "🗂️ 继承其他已注册账期（高级）",
    }[m],
    index=0,
    horizontal=False,
)

inherit_month: str | None = None
if rule_mode == RULE_INHERIT:
    candidates = list_inherit_source_months(month_id)
    if not candidates:
        st.warning(
            "暂无可继承的历史账期。请改用「使用系统固化规则」，"
            "或先用「从新表提取规则」注册样板月。"
        )
    else:
        inherit_month = st.selectbox(
            "继承自账期",
            candidates,
            format_func=lambda mid: mid,
            help="复用所选月份的 sales / rules / aftersales 拓扑 JSON（不拷贝金标准数值）",
        )
elif rule_mode == RULE_CANONICAL:
    st.caption(
        f"公式地图固定为 `data/topology/2026-05/` 下样板拓扑；"
        f"当月仅绑定 `data/raw/<账期>/` 中的 Excel 数据路径。"
    )

submitted = st.button("🚀 一键建档 (Onboard)", type="primary")

if submitted:
    errors: list[str] = []

    month_err = validate_month_id(month_id)
    if month_err:
        errors.append(month_err)

    label_trimmed = label.strip()
    if not label_trimmed:
        errors.append("显示名称不能为空")

    if upload_mode == UPLOAD_MODE_FULL:
        if sales_file is None:
            errors.append("请上传销售账套 .xlsx 文件")
        elif not sales_file.name.lower().endswith(".xlsx"):
            errors.append("销售账套须为 .xlsx 格式")
    elif not sheet_files:
        errors.append("分表上传模式下请至少选择一个 Excel 或 ZIP 文件")

    extract_topology = rule_mode == RULE_EXTRACT
    inherit_topology: str | None = inherit_month if rule_mode == RULE_INHERIT else None

    if rule_mode == RULE_INHERIT and not inherit_topology:
        errors.append("请选择要继承的历史账期，或改用「使用系统固化规则」")

    if errors:
        for err in errors:
            st.error(err)
    else:
        month_clean = month_id.strip()
        with st.spinner("正在保存销售数据并注册账期…"):
            try:
                sheet_sources_rel: str | None = None

                if upload_mode == UPLOAD_MODE_FULL:
                    assert sales_file is not None
                    saved_path = save_sales_workbook(
                        month_clean,
                        sales_file.getvalue(),
                        sales_file.name,
                    )
                else:
                    pairs = pairs_from_streamlit_files(sheet_files)
                    sheet_result = prepare_onboard_from_sheet_uploads(month_clean, pairs)
                    if sheet_result.errors:
                        for err in sheet_result.errors:
                            st.error(err)
                        st.stop()
                    for warn in sheet_result.warnings:
                        st.warning(warn)
                    if sheet_result.sales_path is None:
                        st.error("未能生成合并销售账套")
                        st.stop()
                    saved_path = sheet_result.sales_path
                    if sheet_result.sheet_sources_path is not None:
                        sheet_sources_rel = sales_relative_path(
                            sheet_result.sheet_sources_path
                        )

                sales_rel = sales_relative_path(saved_path)

                args = argparse.Namespace(
                    month=month_clean,
                    sales=sales_rel,
                    rules=None,
                    sheet_sources=sheet_sources_rel,
                    label=label_trimmed,
                    extract_topology=extract_topology,
                    inherit_topology=inherit_topology,
                )

                stdout_buf = io.StringIO()
                with contextlib.redirect_stdout(stdout_buf):
                    rc = cmd_onboard_month(args)
                cli_output = stdout_buf.getvalue().strip()

                if rc == 0:
                    config_path = CONFIG_DIR / f"month-{month_clean}.yaml"
                    st.balloons()
                    st.success(
                        f"账期 **{month_clean}**（{label_trimmed}）已注册。"
                        f" 配置：`{config_path.relative_to(PROJECT_ROOT)}`"
                    )
                    st.caption(f"销售账套：`{saved_path.relative_to(PROJECT_ROOT)}`")
                    if sheet_sources_rel:
                        st.caption(f"分表来源：`{sheet_sources_rel}`")
                    if upload_mode == UPLOAD_MODE_SHEETS:
                        uploads_dir = saved_path.parent / "uploads"
                        if uploads_dir.is_dir():
                            count = len(list(uploads_dir.glob("*.xlsx")))
                            st.caption(
                                f"已保存 {count} 个分表至 "
                                f"`{uploads_dir.relative_to(PROJECT_ROOT)}/`"
                            )
                    if cli_output:
                        with st.expander("CLI 输出"):
                            st.code(cli_output)
                else:
                    st.error(f"建档失败（退出码 {rc}）")
                    if cli_output:
                        st.code(cli_output)
            except Exception as exc:
                st.error(f"建档异常: {exc}")

with st.expander("底层数据表（分表上传参考：必需 / 可选）"):
    for family_label, sheets in group_manifest_by_family():
        if family_label == FAMILY_SALES:
            st.markdown(f"**{family_label}**（试算必需）")
        else:
            st.markdown(f"**{family_label}**（岗位族专用 · 可选）")
        for sheet in sheets:
            roles = "、".join(sheet.families)
            if sheet.optional_note:
                st.markdown(
                    f"- **{sheet.name}** — 可选 · 公式表 · 岗位族: {roles}"
                )
            elif sheet.optional_skeleton:
                st.markdown(
                    f"- **{sheet.name}** — 可选 · 人员骨架（店别/职务/姓名行键）· 岗位族: {roles}"
                )
            elif sheet.optional_role_family:
                st.markdown(
                    f"- **{sheet.name}** — 可选 · 岗位族专用（缺失不阻断试算）· 岗位族: {roles}"
                )
            elif sheet.optional_input:
                st.markdown(
                    f"- **{sheet.name}** — 可选 · 管理岗拓扑回放 · 岗位族: {roles}"
                )
            else:
                st.markdown(
                    f"- **{sheet.name}** — **必需** · header_row={sheet.header_row} · "
                    f"岗位族: {roles}"
                )

with st.expander("使用说明"):
    st.markdown(
        """
**整本账套** — 上传已合并的销售账套 xlsx，直接保存至 `data/raw/<账期>/`。

**分表上传** — 与「发薪上传」相同的工作表匹配逻辑：可一次选择多个 xlsx 或 ZIP，
系统按**工作表名称**匹配必需表，写入 `uploads/` 后合并为 `销售账套-合并-<账期>.xlsx`，
并生成 `sheet_sources.json` 供 Hub 读取 supplemental 表。

**使用系统固化规则（默认）** — 上传数据后，计算始终使用 repo 内
`data/topology/2026-05/` 的 2026-05 样板公式拓扑；`month-YYYY-MM.yaml` 仅绑定
当月 `data/raw/<账期>/` 中的 workbook 路径，不拷贝金标准单元格数值。

**从新表提取规则** — 适用于需从带公式账套重建拓扑的高级场景；
系统会调用 `extract_sales_topology` 生成当月拓扑 JSON。

**继承其他已注册账期** — 复用已在 `months_registry` 中注册账期的
`topology.*` 路径（需至少有一个历史账期）。

建档完成后，可在侧边栏切换至新账期，并使用「发薪上传」继续补充或更新底层明细表。
        """
    )
