"""
Page 5 — Leads (manager-only)
Lead data & forms: searchable/filterable table, full ticket detail, and the
status-update form. The charts/analysis live on the CRM Dashboard page.
"""

import html
import sys
from pathlib import Path

import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.crm_repository import (
    get_all_leads, search_leads, update_lead_status,
)
from src.database.mongodb import ping
from src.auth.manager_auth import require_manager, logout_button
from src.ui.branding import page_header, inject_global_css

# Re-assert global CSS so a direct/first load is styled (see note in app.py).
inject_global_css()

# Manager-only: render the login form and halt if no session is open.
require_manager()
logout_button()

# ── Header ────────────────────────────────────────────────────────────────────
page_header(
    "العملاء المحتملون",
    subtitle="Leads — search, inspect & update tickets",
    rtl=True,
)

# ── MongoDB status ────────────────────────────────────────────────────────────
if not ping():
    st.error("❌ MongoDB connection failed — check your .env file")
    st.stop()

st.page_link("pages/2_CRM_Dashboard.py", label="📊 عرض التحليلات · View analytics & charts")
st.divider()

# ── Lead Table ────────────────────────────────────────────────────────────────
st.markdown("### 📋 All Leads")

col_search, col_filter = st.columns([3, 1])
search_query = col_search.text_input("🔍 Search by name, email, or interest…")
status_filter = col_filter.selectbox(
    "Filter by status",
    ["All", "new", "contacted", "qualified", "converted", "lost"]
)

# Fetch
if search_query:
    leads = search_leads(search_query)
else:
    leads = get_all_leads()

# Apply status filter
if status_filter != "All":
    leads = [l for l in leads if l.get("status") == status_filter]

if not leads:
    st.info("No leads found.")
else:
    df = pd.DataFrame(leads)
    # Ensure newer ticket columns exist even when legacy leads predate them.
    for col in ["temperature", "location", "goal", "current_level", "next_action"]:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    # Format columns
    df["lead_score"] = df["lead_score"].apply(lambda x: f"{x:.0%}" if isinstance(x, (int, float)) else x)
    df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
    TEMP_EMOJI = {"hot": "🔥 hot", "warm": "🌤️ warm", "cold": "❄️ cold"}
    df["temperature"] = df["temperature"].apply(lambda t: TEMP_EMOJI.get(t, t or "—"))
    df = df.rename(columns={
        "_id": "ID", "name": "Name", "phone": "Phone", "email": "Email",
        "language": "Lang", "location": "Location", "interest_area": "Interest",
        "recommended_product": "Product", "lead_score": "Score",
        "temperature": "Temp", "status": "Status", "created_at": "Created",
    })
    cols_show = ["Name", "Phone", "Email", "Location", "Lang", "Interest",
                 "Score", "Temp", "Status", "Created"]
    st.dataframe(df[cols_show], width="stretch", hide_index=True)

    # ── Full ticket detail ──────────────────────────────────────────────────
    st.markdown("#### 🎫 Ticket Detail")
    raw_ids = [l["_id"] for l in leads]
    raw_names = [l.get("name", "Unknown") for l in leads]
    options = [f"{n} ({i[:8]}…)" for n, i in zip(raw_names, raw_ids)]
    selected = st.selectbox("Select lead", options)
    idx = options.index(selected)
    lead = leads[idx]

    # Arabic display maps for enum-style values so the ticket reads in one
    # language end to end (labels + these values are all Arabic).
    LANG_AR = {"arabic": "العربية", "english": "الإنجليزية"}
    TEMP_AR = {"hot": "🔥 ساخن", "warm": "🌤️ دافئ", "cold": "❄️ بارد"}
    STATUS_AR = {"new": "جديد", "contacted": "تم التواصل", "qualified": "مؤهل",
                 "converted": "تم التحويل", "lost": "مفقود"}
    LEVEL_AR = {"beginner": "مبتدئ", "intermediate": "متوسط", "advanced": "متقدم"}
    BUDGET_AR = {"low": "منخفضة", "medium": "متوسطة", "high": "مرتفعة"}
    CHANNEL_AR = {"whatsapp": "واتساب", "phone": "هاتف", "email": "بريد إلكتروني"}

    def _fmt(value, mapping=None):
        if value in (None, "", []):
            return "—"
        if isinstance(value, list):
            return "، ".join(html.escape(str(x)) for x in value) if value else "—"
        if mapping and value in mapping:
            return html.escape(mapping[value])
        return html.escape(str(value))

    def _group(title, rows):
        items = "".join(
            f"<div class='k-ticket__row'>"
            f"<span class='k-ticket__label'>{lbl}</span>"
            f"<span class='k-ticket__val' dir='auto'>{val}</span>"
            f"</div>"
            for lbl, val in rows
        )
        return f"<div class='k-ticket__group'><div class='k-ticket__head'>{title}</div>{items}</div>"

    score = lead.get("lead_score", 0)
    score_txt = f"{score:.0%}" if isinstance(score, (int, float)) else html.escape(str(score))

    who = _group("👤 بيانات العميل", [
        ("الاسم", _fmt(lead.get("name"))),
        ("الهاتف", _fmt(lead.get("phone"))),
        ("واتساب", _fmt(lead.get("whatsapp"))),
        ("البريد الإلكتروني", _fmt(lead.get("email"))),
        ("الموقع", _fmt(lead.get("location"))),
        ("اللغة", _fmt(lead.get("language"), LANG_AR)),
        ("اللهجة", _fmt(lead.get("dialect"))),
        ("قناة التواصل", _fmt(lead.get("contact_channel"), CHANNEL_AR)),
        ("أفضل وقت للتواصل", _fmt(lead.get("best_contact_time"))),
    ])
    want = _group("🎯 ما الذي يريده", [
        ("الاهتمام", _fmt(lead.get("interest_area"))),
        ("المنتجات محل الاهتمام", _fmt(lead.get("products_of_interest"))),
        ("التوصية", _fmt(lead.get("recommended_product"))),
        ("الهدف", _fmt(lead.get("goal"))),
        ("المستوى", _fmt(lead.get("current_level"), LEVEL_AR)),
        ("المتطلبات السابقة", _fmt(lead.get("prerequisites"))),
    ])
    likely = _group("📊 احتمالية الشراء", [
        ("الدرجة", score_txt),
        ("الحرارة", _fmt(lead.get("temperature"), TEMP_AR)),
        ("إشارات الشراء", _fmt(lead.get("buying_signals"))),
        ("حساسية الميزانية", _fmt(lead.get("budget_sensitivity"), BUDGET_AR)),
        ("الاعتراضات", _fmt(lead.get("objections"))),
    ])
    happened = _group("📝 ماذا حدث", [
        ("ملخص المحادثة", _fmt(lead.get("conversation_summary"))),
        ("الإجراء التالي الموصى به", _fmt(lead.get("next_action"))),
        ("الحالة", _fmt(lead.get("status"), STATUS_AR)),
        ("تاريخ الإنشاء", html.escape(str(df.iloc[idx]["Created"]))),
    ])

    dc1, dc2 = st.columns(2)
    dc1.markdown(f"<div class='k-ticket' dir='rtl'>{who}{want}</div>", unsafe_allow_html=True)
    dc2.markdown(f"<div class='k-ticket' dir='rtl'>{likely}{happened}</div>", unsafe_allow_html=True)

    # Quick status update
    st.divider()
    st.markdown("#### ✏️ Update Lead Status")
    new_status = st.selectbox("New status", ["new", "contacted", "qualified", "converted", "lost"])
    if st.button("Update Status", type="primary"):
        lead_id = raw_ids[idx]
        success = update_lead_status(lead_id, new_status)
        if success:
            st.success(f"✅ Status updated to '{new_status}'")
            st.rerun()
        else:
            st.error("Update failed.")
