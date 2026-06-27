"""
Page 11 — Analytics (manager-only)
Aggregate analytics across the AI Sales Agent: model/provider breakdowns, token
distribution, tool-call volume, conversation cost ranking, and dated KPI
snapshots (the `analytics` collection) to track headline numbers over time.
"""

import sys
from pathlib import Path
from collections import defaultdict

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
    kpi_card, style_fig, fmt_usd, fmt_int, fmt_ms, resolve_user_label,
    short_id, ACCENT, CYAN,
)

inject_global_css()
require_manager()
logout_button()

page_header(
    "التحليلات",
    subtitle="Analytics — model/provider breakdowns, tool calls & KPI snapshots",
    rtl=True,
)

if not ping():
    st.error("❌ MongoDB connection failed — check your .env file")
    st.stop()

kpis = analytics.get_dashboard_kpis()
totals = usage.get_totals()

# ── KPI snapshot controls ────────────────────────────────────────────────────────
st.divider()
sc1, sc2 = st.columns([3, 1])
sc1.markdown("#### 📌 لقطات المؤشرات · KPI Snapshots")
if sc2.button("📸 Save snapshot", type="primary", use_container_width=True):
    sid = analytics.save_snapshot()
    if sid:
        st.success("Saved a KPI snapshot.")
    else:
        st.error("Could not save snapshot.")

snapshots = analytics.get_snapshots(200)
if snapshots:
    df = pd.DataFrame(snapshots)
    df["created_at"] = pd.to_datetime(df["created_at"])
    df = df.sort_values("created_at")
    sc = st.columns(2)
    with sc[0]:
        st.caption("التكلفة الإجمالية عبر اللقطات · Total cost across snapshots")
        fig = px.line(df, x="created_at", y="total_cost", markers=True)
        fig.update_traces(line_color=ACCENT)
        st.plotly_chart(style_fig(fig), use_container_width=True)
    with sc[1]:
        st.caption("الرسائل والمحادثات · Messages & conversations")
        fig = px.line(df, x="created_at", y=["total_messages", "total_conversations"],
                      markers=True,
                      color_discrete_map={"total_messages": CYAN,
                                          "total_conversations": ACCENT})
        st.plotly_chart(style_fig(fig), use_container_width=True)
else:
    st.caption("لا توجد لقطات محفوظة بعد — اضغط «Save snapshot» لإنشاء أول لقطة.")

if totals["llm_calls"] == 0:
    st.info("لا توجد بيانات استخدام بعد — ابدأ محادثات في المساعد.\n\n"
            "No usage data yet — chat in the Assistant to populate analytics.")
    st.stop()

# ── Breakdowns ────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("🧩 التوزيعات · Breakdowns")

by_model = usage.get_cost_by_model()
by_provider = usage.get_cost_by_provider()

b1, b2 = st.columns(2)
with b1:
    st.caption("التكلفة حسب الموديل · Cost by model")
    if by_model:
        df = pd.DataFrame(by_model)
        fig = px.bar(df, x="model", y="cost", text="calls")
        fig.update_traces(marker_color=ACCENT,
                          hovertemplate="%{x}<br>$%{y:.4f}<br>%{text} calls")
        st.plotly_chart(style_fig(fig), use_container_width=True)
with b2:
    st.caption("التوكنز حسب الموديل · Tokens by model")
    if by_model:
        df = pd.DataFrame(by_model)
        fig = px.bar(df, x="model", y="tokens")
        fig.update_traces(marker_color=CYAN)
        st.plotly_chart(style_fig(fig), use_container_width=True)

# ── Tool calls + token split ──────────────────────────────────────────────────────
st.divider()
st.subheader("🛠️ أدوات وتوكنز · Tool Calls & Tokens")

recent = usage.get_recent_usage(2000)

# Tool calls over time (derived from usage rows).
tc_by_day = defaultdict(int)
for r in recent:
    ts = r.get("timestamp")
    if ts is not None and hasattr(ts, "strftime"):
        tc_by_day[ts.strftime("%Y-%m-%d")] += int(r.get("tool_calls", 0) or 0)

t1, t2 = st.columns(2)
with t1:
    st.caption("عدد استدعاءات الأدوات يومياً · Tool calls over time")
    if tc_by_day:
        df = pd.DataFrame(sorted(tc_by_day.items()), columns=["date", "tool_calls"])
        fig = px.bar(df, x="date", y="tool_calls")
        fig.update_traces(marker_color="#8A8FE0")
        st.plotly_chart(style_fig(fig), use_container_width=True)
    else:
        st.info("No tool-call activity recorded.")
with t2:
    st.caption("توزيع التوكنز · Token distribution")
    df = pd.DataFrame([
        {"type": "Input", "tokens": totals["input_tokens"]},
        {"type": "Output", "tokens": totals["output_tokens"]},
        {"type": "Embedding", "tokens": totals["embedding_tokens"]},
    ])
    fig = px.pie(df, names="type", values="tokens", hole=0.55)
    fig.update_traces(textinfo="percent+label")
    st.plotly_chart(style_fig(fig), use_container_width=True)

# ── Conversation cost ranking ─────────────────────────────────────────────────────
st.divider()
st.subheader("🏆 ترتيب المحادثات حسب التكلفة · Conversation Cost Ranking")
conv_rows = usage.get_cost_per_conversation(15)
if conv_rows:
    df = pd.DataFrame([{
        "Conversation": short_id(r["conversation_id"], 10),
        "User": resolve_user_label(r["user_id"]),
        "Cost": r["total_cost"],
        "Messages": r["messages"],
        "Tool calls": r["tool_calls"],
    } for r in conv_rows])
    fig = px.bar(df, x="Cost", y="Conversation", orientation="h",
                 hover_data=["User", "Messages", "Tool calls"])
    fig.update_traces(marker_color=ACCENT, hovertemplate="%{y}<br>$%{x:.5f}")
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(style_fig(fig, height=420), use_container_width=True)
