"""
Page 3 — Manager Login
Single sign-in for the Kayfa manager. Gates the CRM and Performance dashboards.
When already signed in, shows the account and a sign-out button.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth.manager_auth import (
    is_authenticated, current_user, logout, login_form,
)
from src.ui.branding import inject_global_css, brand_mark

# Re-assert global CSS so a direct/first load is styled (see note in app.py).
inject_global_css()

if is_authenticated():
    st.markdown(
        "<div class='k-login'>"
        f"<div class='k-login__brand'>{brand_mark(72)}</div>"
        "<h2 class='k-login__title'>أهلاً بك في لوحة المدير</h2>"
        f"<p class='k-login__sub'>مسجّل الدخول باسم <b>{current_user()}</b> · "
        "Signed in as manager</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.success("✅ لديك صلاحية الوصول إلى لوحات المدير.")
        st.page_link("pages/4_Performance.py", label="📈 لوحة الأداء · Performance Dashboard")
        st.page_link("pages/2_CRM_Dashboard.py", label="📊 تحليلات العملاء · CRM Analytics")
        st.page_link("pages/5_Leads.py", label="📋 إدارة العملاء · Leads & Data")
        st.divider()
        if st.button("🚪 تسجيل الخروج · Sign out", type="primary",
                     use_container_width=True):
            logout()
            st.rerun()
else:
    login_form()
