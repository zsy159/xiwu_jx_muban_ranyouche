"""财务调账 — 编辑绩效整理表并保存财务确认版。"""

from __future__ import annotations

import streamlit as st

from salary_pipeline.app._shared import init_session_state, render_sidebar
from salary_pipeline.app.finance_adjust_helpers import (
    build_perf_editor_column_config,
    describe_loaded_source,
    load_performance_sheet_for_edit,
    save_confirmed_performance_sheet,
)
from salary_pipeline.observability.loaders import load_month_config_for
from salary_pipeline.pipelines.performance_sheet_paths import (
    CONFIRMED_PERF_FILENAME,
    SYSTEM_PERF_FILENAME,
)

st.set_page_config(page_title="财务调账", layout="wide")

init_session_state()
month_id = render_sidebar()

st.title("财务调账")
st.caption(
    f"账期 **{month_id}** · 在系统生成绩效整理表基础上手工调整，"
    f"保存至 `{CONFIRMED_PERF_FILENAME}`（不覆盖 `{SYSTEM_PERF_FILENAME}`）"
)

cfg = load_month_config_for(month_id)
df, loaded_path, source_label = load_performance_sheet_for_edit(cfg)

if source_label == "missing":
    if df is not None and df.empty and loaded_path is not None:
        st.warning(
            f"找到 `{loaded_path.name}` 但无数据行（或表头无法识别）。"
            f"请重新运行试算/ compute 生成绩效整理表。"
        )
    else:
        st.warning(
            f"未找到 `{SYSTEM_PERF_FILENAME}`。请先运行 "
            f"`python main.py compute --month {month_id}` 生成系统绩效整理表。"
        )
    st.stop()

badge = "🟢 财务确认版" if source_label == "confirmed" else "🔵 系统生成底稿"
st.caption(f"{badge} · {describe_loaded_source(source_label, loaded_path)}")

st.markdown(
    """
<style>
/* 宽表横向滚动：强制显示滚动条轨道（macOS overlay 滚动条默认 hover 才出现且很淡） */
[data-testid="stDataEditor"] div[data-testid="glideDataEditor"],
[data-testid="stDataEditor"] > div {
    overflow-x: scroll !important;
    scrollbar-gutter: stable;
}
[data-testid="stDataEditor"] div[data-testid="glideDataEditor"]::-webkit-scrollbar,
[data-testid="stDataEditor"] > div::-webkit-scrollbar {
    height: 14px;
    display: block;
}
[data-testid="stDataEditor"] div[data-testid="glideDataEditor"]::-webkit-scrollbar-track,
[data-testid="stDataEditor"] > div::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 0.06);
    border-radius: 7px;
}
[data-testid="stDataEditor"] div[data-testid="glideDataEditor"]::-webkit-scrollbar-thumb,
[data-testid="stDataEditor"] > div::-webkit-scrollbar-thumb {
    background: rgba(100, 100, 100, 0.55);
    border-radius: 7px;
    border: 2px solid rgba(240, 242, 246, 0.9);
}
[data-testid="stDataEditor"] div[data-testid="glideDataEditor"]::-webkit-scrollbar-thumb:hover,
[data-testid="stDataEditor"] > div::-webkit-scrollbar-thumb:hover {
    background: rgba(80, 80, 80, 0.85);
}
[data-testid="stDataEditor"] div[data-testid="glideDataEditor"],
[data-testid="stDataEditor"] > div {
    scrollbar-width: thin;
    scrollbar-color: rgba(100, 100, 100, 0.55) rgba(0, 0, 0, 0.06);
}
</style>
""",
    unsafe_allow_html=True,
)
st.caption("表格较宽时：在表格区域 **Shift + 滚轮** 可横向滚动；滚动条位于表格底部。")

_editor_kw: dict = {
    "num_rows": "dynamic",
    "column_config": build_perf_editor_column_config(df),
    "key": f"finance_perf_editor_{month_id}",
}
try:
    _ver = tuple(int(x) for x in st.__version__.split(".")[:2])
except (ValueError, IndexError):
    _ver = (0, 0)
if _ver >= (1, 40):
    _editor_kw["width"] = "content"

with st.form("finance_perf_form", clear_on_submit=False):
    edited = st.data_editor(df, **_editor_kw)
    submitted = st.form_submit_button("💾 保存调整并提交至发薪流水线")

if submitted:
    dest = save_confirmed_performance_sheet(cfg, edited)
    st.success(
        f"已保存财务确认版 → `{dest}`。"
        f"下游 Hub overlay / 发薪 SUMIF 将优先读取此文件。"
    )
    st.cache_data.clear()
