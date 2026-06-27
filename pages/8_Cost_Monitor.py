"""
Page 8 — Cost Monitor (manager-only)
AI cost tracked on three levels — per message, per conversation, per user —
including BOTH chat-model and embedding-model cost (cross-provider aware).
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
from src.monitoring import usage_repository as usage
from src.dashboard.components import (
    kpi_card, style_fig, fmt_usd, fmt_int, fmt_ms, resolve_user_label,
    short_id, ACCENT, CYAN,
)

inject_global_css()
require_manager()
logout_button()

page_header(
    "مراقبة التكاليف",
    subtitle="Cost Monitor — per message · per conversation · per user (chat + embedding)",
    rtl=True,
)

if not ping():
    st.error("❌ MongoDB connection failed — check your .env file")
    st.stop()

totals = usage.get_totals()

if totals["llm_calls"] == 0:
    st.info("لا توجد سجلات تكلفة بعد — ابدأ محادثات في المساعد.\n\n"
            "No cost logs yet — chat in the Assistant to populate the cost monitor.")
    st.stop()

# ── Totals ──────────────────────────────────────────────────────────────────────
st.divider()
k = st.columns(4)
kpi_card(k[0], "💵", fmt_usd(totals["total_cost"], 4), "Total Cost")
kpi_card(k[1], "🤖", fmt_usd(totals["chat_cost"], 4), "Chat Cost")
kpi_card(k[2], "🔡", fmt_usd(totals["embedding_cost"], 4), "Embedding Cost")
kpi_card(k[3], "🔢", fmt_int(totals["total_tokens"]), "Total Tokens")

k2 = st.columns(4)
kpi_card(k2[0], "💬", fmt_int(totals["conversations"]), "Conversations")
kpi_card(k2[1], "✉️", fmt_int(totals["messages"]), "Messages")
kpi_card(k2[2], "🛠️", fmt_int(totals["tool_calls"]), "Tool Calls")
kpi_card(k2[3], "⏱️", fmt_ms(totals["avg_latency"]), "Avg Latency / call")

# ── Charts ──────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("📈 الرسوم البيانية · Charts")

over_time = usage.get_cost_over_time()
tokens_over_time = usage.get_token_usage_over_time()
by_provider = usage.get_cost_by_provider()
latency_time = usage.get_latency_over_time()

c1, c2 = st.columns(2)
with c1:
    st.caption("التكلفة عبر الزمن · Cost over time")
    if over_time:
        df = pd.DataFrame(over_time)
        fig = px.area(df, x="date", y="cost")
        fig.update_traces(line_color=CYAN, fillcolor="rgba(38,198,218,.22)")
        st.plotly_chart(style_fig(fig), use_container_width=True)
with c2:
    st.caption("التكلفة حسب المزوّد · Cost by provider")
    if by_provider:
        df = pd.DataFrame(by_provider)
        fig = px.bar(df, x="provider", y="cost", text="calls")
        fig.update_traces(marker_color=ACCENT,
                          hovertemplate="%{x}<br>$%{y:.4f}<br>%{text} calls")
        st.plotly_chart(style_fig(fig), use_container_width=True)

c3, c4 = st.columns(2)
with c3:
    st.caption("استخدام التوكنز · Token usage over time")
    if tokens_over_time:
        df = pd.DataFrame(tokens_over_time)
        df_long = df.melt(id_vars="date",
                          value_vars=["input_tokens", "output_tokens", "embedding_tokens"],
                          var_name="type", value_name="tokens")
        fig = px.bar(df_long, x="date", y="tokens", color="type", barmode="stack",
                     color_discrete_map={"input_tokens": ACCENT,
                                         "output_tokens": CYAN,
                                         "embedding_tokens": "#8A8FE0"})
        st.plotly_chart(style_fig(fig), use_container_width=True)
with c4:
    st.caption("زمن الاستجابة · Latency over time")
    if latency_time:
        df = pd.DataFrame(latency_time)
        fig = px.line(df, x="date", y=["avg_latency", "max_latency"], markers=True,
                      color_discrete_map={"avg_latency": ACCENT, "max_latency": "#cf222e"})
        fig.update_yaxes(title="ms")
        st.plotly_chart(style_fig(fig), use_container_width=True)

# ── Three levels: per user / conversation / message ──────────────────────────────
st.divider()
st.subheader("🧾 التكلفة على ثلاثة مستويات · Cost on three levels")
tab_user, tab_conv, tab_msg = st.tabs(
    ["👥 Per User", "💬 Per Conversation", "✉️ Per Message"]
)

with tab_user:
    rows = usage.get_cost_per_user(50)
    if rows:
        # Top expensive users chart.
        top = rows[:10]
        df = pd.DataFrame([{
            "User": resolve_user_label(r["user_id"]),
            "Cost": r["total_cost"],
        } for r in top])
        fig = px.bar(df, x="Cost", y="User", orientation="h")
        fig.update_traces(marker_color=ACCENT, hovertemplate="%{y}<br>$%{x:.5f}")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.caption("أعلى المستخدمين تكلفةً · Top expensive users")
        st.plotly_chart(style_fig(fig), use_container_width=True)

        table = pd.DataFrame([{
            "User": resolve_user_label(r["user_id"]),
            "Cost ($)": round(r["total_cost"], 6),
            "Tokens": r["total_tokens"],
            "Messages": r["messages"],
            "Conversations": r["conversations"],
            "LLM calls": r["llm_calls"],
        } for r in rows])
        st.dataframe(table, use_container_width=True, hide_index=True)

with tab_conv:
    rows = usage.get_cost_per_conversation(50)
    if rows:
        top = rows[:10]
        df = pd.DataFrame([{
            "Conversation": short_id(r["conversation_id"]),
            "Cost": r["total_cost"],
        } for r in top])
        fig = px.bar(df, x="Cost", y="Conversation", orientation="h")
        fig.update_traces(marker_color=CYAN, hovertemplate="%{y}<br>$%{x:.5f}")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.caption("ترتيب المحادثات حسب التكلفة · Conversation cost ranking")
        st.plotly_chart(style_fig(fig), use_container_width=True)

        table = pd.DataFrame([{
            "Conversation": short_id(r["conversation_id"], 12),
            "User": resolve_user_label(r["user_id"]),
            "Cost ($)": round(r["total_cost"], 6),
            "Messages": r["messages"],
            "Tool calls": r["tool_calls"],
            "Tokens": r["total_tokens"],
            "Last activity": r["last_time"].strftime("%Y-%m-%d %H:%M") if r.get("last_time") else "",
        } for r in rows])
        st.dataframe(table, use_container_width=True, hide_index=True)

with tab_msg:
    rows = usage.get_cost_per_message(100)
    if rows:
        table = pd.DataFrame([{
            "Message": short_id(r["message_id"], 12),
            "Conversation": short_id(r["conversation_id"], 10),
            "User": resolve_user_label(r["user_id"]),
            "Cost ($)": round(r["total_cost"], 6),
            "In tok": r["input_tokens"],
            "Out tok": r["output_tokens"],
            "Tool calls": r["tool_calls"],
            "Latency": fmt_ms(r["latency_ms"]),
            "When": r["timestamp"].strftime("%Y-%m-%d %H:%M") if r.get("timestamp") else "",
        } for r in rows])
        st.dataframe(table, use_container_width=True, hide_index=True, height=440)
