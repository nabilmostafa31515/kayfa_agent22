"""
Page 6 — Usage & Behavior (manager-only)
LLM cost records and end-user behavior traces, both attributed by user_id.

Answers: how much are we spending (by model / user / day), and what are users
doing (events, recent activity)?
"""

import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth.manager_auth import require_manager, logout_button
from src.database.mongodb import ping
from src.database.cost_repository import (
    get_cost_summary, get_cost_by_model, get_cost_by_user, get_cost_over_time,
)
from src.database.traces_repository import (
    get_event_counts, get_recent_traces, get_active_users,
)
from src.database.users_repository import get_user_by_id
from src.ui.branding import page_header, is_dark, active_palette, inject_global_css

inject_global_css()

# ── Auth gate (same unified auth as the chat) ───────────────────────────────────
require_manager()
logout_button()

_P = active_palette()
PLOTLY_TEMPLATE = "plotly_dark" if is_dark() else "plotly_white"


def _style(fig):
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color=_P["text"], margin=dict(t=30, b=10, l=10, r=10),
    )
    return fig


def _kpi(col, icon, value, label):
    col.markdown(
        f"<div class='kpi-card'><div class='kpi-icon'>{icon}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-label'>{label}</div></div>",
        unsafe_allow_html=True,
    )


# ── Header ──────────────────────────────────────────────────────────────────────
page_header(
    "الاستخدام والتكاليف",
    subtitle="Usage & Behavior — LLM cost records and user behavior traces",
    rtl=True,
)

if not ping():
    st.error("❌ MongoDB connection failed — check your .env file")
    st.stop()

summary = get_cost_summary()
by_model = get_cost_by_model()
by_user = get_cost_by_user()
over_time = get_cost_over_time()
events = get_event_counts()
recent = get_recent_traces(100)

# ── KPIs ────────────────────────────────────────────────────────────────────────
st.divider()
k1, k2, k3, k4 = st.columns(4)
_kpi(k1, "💵", f"${summary.get('total_cost', 0):.4f}", "Total cost (est.)")
_kpi(k2, "🔢", f"{summary.get('total_tokens', 0):,}", "Total tokens")
_kpi(k3, "🤖", f"{summary.get('calls', 0):,}", "LLM calls")
_kpi(k4, "👥", f"{get_active_users():,}", "Active users")

if summary.get("calls", 0) == 0:
    st.info("لا توجد سجلات استخدام بعد — ابدأ محادثات في المساعد لتظهر التكاليف.\n\n"
            "No usage records yet — chat in the Assistant to populate cost data.")
    st.stop()

# ── Cost charts ─────────────────────────────────────────────────────────────────
st.divider()
st.subheader("💰 التكاليف · Costs")
cc1, cc2 = st.columns(2)

with cc1:
    st.caption("التكلفة حسب الموديل · Cost by model")
    if by_model:
        df = pd.DataFrame(by_model)
        fig = px.bar(df, x="model", y="cost", text="calls")
        fig.update_traces(marker_color="#404BCF",
                          hovertemplate="%{x}<br>$%{y:.4f}<br>%{text} calls")
        st.plotly_chart(_style(fig), use_container_width=True)

with cc2:
    st.caption("التكلفة عبر الزمن · Cost over time")
    if over_time:
        df = pd.DataFrame(over_time)
        fig = px.area(df, x="date", y="cost")
        fig.update_traces(line_color="#26C6DA", fillcolor="rgba(38,198,218,.25)")
        st.plotly_chart(_style(fig), use_container_width=True)

# Top users by cost (resolve user_id → email for readability)
st.caption("أعلى المستخدمين تكلفةً · Top users by cost")
if by_user:
    rows = []
    for u in by_user:
        info = get_user_by_id(u["user_id"]) if u["user_id"] not in ("", "—") else None
        rows.append({
            "User": (info or {}).get("email", u["user_id"] or "anonymous"),
            "Cost ($)": round(u["cost"], 4),
            "Tokens": u["tokens"],
            "Calls": u["calls"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Behavior traces ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("📊 سلوك المستخدمين · Behavior")
bc1, bc2 = st.columns([1, 1])

with bc1:
    st.caption("الأحداث · Events")
    if events:
        df = pd.DataFrame(events)
        fig = px.bar(df, x="count", y="event", orientation="h")
        fig.update_traces(marker_color="#404BCF")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(_style(fig), use_container_width=True)

with bc2:
    st.caption("أحدث النشاط · Recent activity")
    if recent:
        rows = [{
            "When": t["created_at"].strftime("%Y-%m-%d %H:%M") if t.get("created_at") else "",
            "Event": t.get("event", ""),
            "User": t.get("user_id", "") or "—",
        } for t in recent[:50]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=360)
