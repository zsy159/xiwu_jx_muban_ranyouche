"""薪酬流水线观察台 — 导航入口（st.navigation 分组）。"""

from __future__ import annotations

import streamlit as st

from salary_pipeline.app._nav import build_navigation
from salary_pipeline.app._shared import init_session_state

st.set_page_config(
    page_title="薪酬观察台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()

pg = st.navigation(build_navigation(), position="sidebar", expanded=False)
pg.run()
