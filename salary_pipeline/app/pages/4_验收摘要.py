"""验收摘要 — 财务一页纸导出"""

from __future__ import annotations

import streamlit as st

from salary_pipeline.app._shared import render_sidebar
from salary_pipeline.observability.loaders import (
    build_acceptance_summary,
    render_acceptance_markdown,
)

st.set_page_config(page_title="验收摘要", layout="wide")
month_id = render_sidebar()

st.title("验收摘要")
st.caption("面向财务的一页纸结论，与 CLI reconcile 判定一致。")

summary = build_acceptance_summary(month_id)
md = render_acceptance_markdown(summary)

st.markdown(md)

st.download_button(
    "下载 Markdown",
    data=md,
    file_name=f"验收摘要_{month_id}.md",
    mime="text/markdown",
)
