"""
Page 7 — AI Monitoring · Dashboard Home (manager-only)
Headline KPIs for the AI Sales Agent's cost, behaviour and performance, plus a
quick overview of spend and activity over time.
"""

import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth.manager_auth import require_manager, logout_button
from src.database.mongodb import ping
from src.ui.branding import page_header, inject_global_css
from src.monitoring import analytics_repository as analytics
from src.monitoring import usage_repository as usage
from src.dashboard.components import (
    kpi_card, style_fig, fmt_usd, fmt_int, fmt_ms, ACCENT, CYAN,
)

inject_global_css()
require_manager()
logout_button()

page_header(
    "مراقبة الذكاء الاصطناعي",
    subtitle="AI Monitoring — cost, behaviour & performance at a glance",
    rtl=True,
)

if not ping():
    st.error("❌ MongoDB connection failed — check your .env file")
    st.stop()

kpis = analytics.get_dashboard_kpis()

if kpis["llm_calls"] == 0 and kpis["total_messages"] == 0:
    st.info("لا توجد بيانات مراقبة بعد — ابدأ محادثات في المساعد لتُسجَّل التكاليف والتتبّع.\n\n"
            "No monitoring data yet — chat in the Assistant to populate usage logs & traces.")
    st.stop()

# ── KPI grid ────────────────────────────────────────────────────────────────────
st.divider()
r1 = st.columns(4)
kpi_card(r1[0], "👥", fmt_int(kpis["total_users"]), "Total Users")
kpi_card(r1[1], "💬", fmt_int(kpis["total_conversations"]), "Total Conversations")
kpi_card(r1[2], "✉️", fmt_int(kpis["total_messages"]), "Total Messages")
kpi_card(r1[3], "💵", fmt_usd(kpis["total_cost"], 4), "Total Cost")

r2 = st.columns(4)
kpi_card(r2[0], "📊", fmt_usd(kpis["avg_cost_per_conversation"], 5), "Avg Cost / Conversation")
kpi_card(r2[1], "⏱️", fmt_ms(kpis["avg_latency"]), "Avg Latency")
kpi_card(r2[2], "🛠️", fmt_int(kpis["total_tool_calls"]), "Total Tool Calls")
kpi_card(r2[3], "🔢", fmt_int(kpis["total_tokens"]), "Total Tokens")

st.caption(
    f"Chat cost {fmt_usd(kpis['chat_cost'], 4)} · Embedding cost "
    f"{fmt_usd(kpis['embedding_cost'], 4)} · {fmt_int(kpis['llm_calls'])} LLM calls"
)

# ── Overview charts ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("📈 نظرة عامة · Overview")

over_time = usage.get_cost_over_time()
by_provider = usage.get_cost_by_provider()

oc1, oc2 = st.columns(2)
with oc1:
    st.caption("التكلفة عبر الزمن · Cost over time")
    if over_time:
        df = pd.DataFrame(over_time)
        fig = px.area(df, x="date", y="cost")
        fig.update_traces(line_color=CYAN, fillcolor="rgba(38,198,218,.22)")
        st.plotly_chart(style_fig(fig), use_container_width=True)
    else:
        st.info("No cost history yet.")

with oc2:
    st.caption("التكلفة حسب المزوّد · Cost by provider")
    if by_provider:
        df = pd.DataFrame(by_provider)
        fig = px.pie(df, names="provider", values="cost", hole=0.55)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(style_fig(fig), use_container_width=True)
    else:
        st.info("No provider data yet.")

# ── Quick navigation ────────────────────────────────────────────────────────────
st.divider()
st.subheader("🔎 الوحدات · Modules")
nav = st.columns(4)
nav[0].page_link("pages/8_Cost_Monitor.py", label="💰 Cost Monitor", use_container_width=True)
nav[1].page_link("pages/9_Behavior_Trace.py", label="🧭 Behavior Trace", use_container_width=True)
nav[2].page_link("pages/10_Optimization.py", label="⚡ Optimization", use_container_width=True)
nav[3].page_link("pages/11_Analytics.py", label="📊 Analytics", use_container_width=True)
