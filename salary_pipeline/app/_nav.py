"""观察台导航注册 — 使用 st.navigation 显式声明分组与子页面。"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
PAGES_DIR = APP_DIR / "pages"
SALARY_DIR = PAGES_DIR / "算薪"

# st.switch_page 路径（相对 streamlit_app.py 所在目录）
P_UPLOAD = "pages/0_发薪上传.py"
P_OVERVIEW = "pages/1_总览.py"
P_RECONCILE = "pages/2_对账中心.py"
P_EXPLORE = "pages/3_差异探索.py"
P_ACCEPTANCE = "pages/4_验收摘要.py"
P_DEV = "pages/11_开发者.py"
P_SALARY_SUMMARY = "pages/算薪/1_汇总.py"
P_SALARY_NEW_MEDIA = "pages/算薪/2_新媒体.py"
P_SALARY_INVITE = "pages/算薪/3_邀约专员.py"
P_SALARY_ALIGN = "pages/算薪/4_字段拉通.py"
P_SALARY_CUSTOMER = "pages/算薪/5_客户专员.py"
P_SALARY_DSM = "pages/算薪/6_直营店经理.py"
P_SALARY_RECRUIT = "pages/算薪/7_招聘.py"
P_SALARY_ADVISOR = "pages/算薪/8_销售顾问.py"


def build_navigation() -> dict[str, list[st.Page]]:
    sections: dict[str, list[st.Page]] = {
        "": [
            st.Page(PAGES_DIR / "1_总览.py", title="总览", default=True, icon="📊"),
        ],
        "上传": [
            st.Page(PAGES_DIR / "0_发薪上传.py", title="发薪上传", icon="📤"),
        ],
        "对账": [
            st.Page(PAGES_DIR / "2_对账中心.py", title="对账中心"),
            st.Page(PAGES_DIR / "3_差异探索.py", title="差异探索"),
            st.Page(PAGES_DIR / "4_验收摘要.py", title="验收摘要"),
        ],
        "算薪": [
            st.Page(SALARY_DIR / "1_汇总.py", title="汇总"),
            st.Page(SALARY_DIR / "2_新媒体.py", title="新媒体"),
            st.Page(SALARY_DIR / "3_邀约专员.py", title="邀约专员"),
            st.Page(SALARY_DIR / "4_字段拉通.py", title="字段拉通"),
            st.Page(SALARY_DIR / "5_客户专员.py", title="客户专员"),
            st.Page(SALARY_DIR / "6_直营店经理.py", title="直营店经理"),
            st.Page(SALARY_DIR / "7_招聘.py", title="招聘"),
            st.Page(SALARY_DIR / "8_销售顾问.py", title="销售顾问"),
        ],
    }
    if st.session_state.get("dev_mode"):
        sections["开发"] = [st.Page(PAGES_DIR / "11_开发者.py", title="开发者")]
    return sections
