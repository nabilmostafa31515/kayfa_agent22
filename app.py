"""
Kayfa AI Sales Agent — entry point & navigation router.
Run: streamlit run app.py
"""

import sys
import logging
from pathlib import Path

# Force UTF-8 stdio (Arabic logs on Windows consoles)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

import streamlit as st
from src.ui.branding import (
    PAGE_ICON, inject_global_css, show_sidebar_logo, theme_toggle, brand_mark,
)

st.set_page_config(
    page_title="Kayfa AI Sales Agent",
    page_icon=PAGE_ICON,
    layout="centered",
    initial_sidebar_state="expanded",
)


# ── Landing page ────────────────────────────────────────────────────────────────
def home():
    st.markdown(
        "<div class='k-hero'>"
        f"<div style='display:flex;justify-content:center;'>{brand_mark(120)}</div>"
        "<h1>Kayfa AI Sales Agent</h1>"
        "<div class='k-hero__ar'>مساعد مبيعات ذكي لمنصة كيفا التعليمية</div>"
        "<div class='k-hero__en'>An intelligent bilingual sales assistant for Kayfa's learning platform</div>"
        "<div class='k-chips'>"
        "<span class='k-chip'>🤖 Agentic AI</span>"
        "<span class='k-chip'>📚 RAG Knowledge Base</span>"
        "<span class='k-chip'>🌍 Bilingual · AR / EN</span>"
        "<span class='k-chip'>📊 CRM &amp; Analytics</span>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    st.write("")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(
            "<a class='k-card k-card--link' href='Chat_Assistant' target='_self'>"
            "<span class='k-card__title'>💬 Chat Assistant</span>"
            "<span class='k-card__desc'>تحدّث مع كيفا AI لاكتشاف الكورسات والمسارات المناسبة لك — بالعربية أو الإنجليزية.</span>"
            "<span class='k-card__cta'>ابدأ المحادثة · Open Chat →</span>"
            "</a>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            "<a class='k-card k-card--link' href='CRM_Dashboard' target='_self'>"
            "<span class='k-card__title'>📊 CRM Dashboard</span>"
            "<span class='k-card__desc'>عرض وإدارة العملاء المحتملين مع تحليلات بيانية وإحصائيات في الوقت الفعلي.</span>"
            "<span class='k-card__cta'>افتح اللوحة · Open Dashboard →</span>"
            "</a>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div class='k-footer'>Powered by LangGraph · RAG · MongoDB Atlas · "
        "<a href='https://kayfa.io' target='_blank'>kayfa.io</a></div>",
        unsafe_allow_html=True,
    )


# ── Navigation ──────────────────────────────────────────────────────────────────
pages = [
    st.Page(home, title="Home", icon=":material/home:", default=True),
    st.Page("pages/1_Chat_Assistant.py", title="Chat Assistant", icon=":material/chat:"),
    st.Page("pages/2_CRM_Dashboard.py", title="CRM Dashboard", icon=":material/insights:"),
]
nav = st.navigation(pages)

# Global chrome — runs on every page before the selected page renders.
inject_global_css()
show_sidebar_logo()
theme_toggle()

nav.run()