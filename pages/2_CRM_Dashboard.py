"""
Page 2 — CRM Dashboard
KPI cards and Plotly analytics charts. Lead data & forms (table, ticket detail,
status updates) live on the Leads page.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.crm_repository import (
    get_lead_stats,
    get_leads_by_interest, get_leads_by_status,
    get_leads_by_language, get_leads_by_temperature,
    get_score_distribution, get_leads_over_time,
)
from src.database.mongodb import ping
from src.auth.manager_auth import require_manager, logout_button
from src.ui.branding import page_header, is_dark, active_palette, inject_global_css

# Re-assert global CSS from within the page so a direct/first load is styled
# (app.py's pre-nav inject doesn't stick until a rerun). See the note in
# pages/1_Chat_Assistant.py.
inject_global_css()

# Manager-only: render the login form and halt if no session is open.
require_manager()
logout_button()

_P = active_palette()
PLOTLY_TEMPLATE = "plotly_dark" if is_dark() else "plotly_white"
BRAND_SEQ = ["#404BCF", "#6368CF", "#8A8FE0", "#26C6DA", "#A6B0F2", "#C7CCF7"]


def _style(fig):
    """Apply theme-aware template, transparent background, and font color."""
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color=_P["text"],
    )
    return fig

# ── Header ────────────────────────────────────────────────────────────────────
page_header(
    "لوحة تحليلات العملاء",
    subtitle="Kayfa CRM Dashboard — Analytics & Insights",
    rtl=True,
)

# ── MongoDB status ────────────────────────────────────────────────────────────
db_ok = ping()
if db_ok:
    st.success("✅ Connected to MongoDB Atlas")
else:
    st.error("❌ MongoDB connection failed — check your .env file")
    st.stop()

st.page_link("pages/5_Leads.py", label="📋 إدارة العملاء والبيانات · Manage leads & data")
st.divider()

# ── KPI Cards ─────────────────────────────────────────────────────────────────
stats = get_lead_stats()
k1, k2, k3, k4 = st.columns(4)

k1.markdown(f"""
<div class='kpi-card'>
  <div class='kpi-icon'>👥</div>
  <div class='kpi-value'>{stats.get('total', 0)}</div>
  <div class='kpi-label'>Total Leads</div>
</div>""", unsafe_allow_html=True)

k2.markdown(f"""
<div class='kpi-card'>
  <div class='kpi-icon'>✅</div>
  <div class='kpi-value'>{stats.get('qualified', 0)}</div>
  <div class='kpi-label'>Qualified Leads (≥60%)</div>
</div>""", unsafe_allow_html=True)

k3.markdown(f"""
<div class='kpi-card'>
  <div class='kpi-icon'>📈</div>
  <div class='kpi-value'>{stats.get('avg_score', 0):.0%}</div>
  <div class='kpi-label'>Avg Lead Score</div>
</div>""", unsafe_allow_html=True)

k4.markdown(f"""
<div class='kpi-card'>
  <div class='kpi-icon'>🎯</div>
  <div class='kpi-value' style='font-size:1.15rem; padding-top:4px;'>{stats.get('top_interest', '—')}</div>
  <div class='kpi-label'>Top Interest Area</div>
</div>""", unsafe_allow_html=True)

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
c1, c2 = st.columns(2)

# Chart 1: Leads per Interest Area
with c1:
    interest_data = get_leads_by_interest()
    if interest_data:
        df_int = pd.DataFrame(interest_data)
        fig = px.bar(
            df_int, x="count", y="interest_area", orientation="h",
            title="Leads per Interest Area",
            color="count", color_continuous_scale=["#C7CCF7", "#404BCF"],
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(
            showlegend=False, coloraxis_showscale=False,
            yaxis_title="", xaxis_title="Leads",
        )
        st.plotly_chart(_style(fig), width="stretch")
    else:
        st.info("No interest area data yet.")

# Chart 2: Leads by Status
with c2:
    status_data = get_leads_by_status()
    if status_data:
        df_st = pd.DataFrame(status_data)
        fig2 = px.pie(
            df_st, names="status", values="count",
            title="Leads by Status",
            color_discrete_sequence=BRAND_SEQ,
            template=PLOTLY_TEMPLATE, hole=0.45,
        )
        st.plotly_chart(_style(fig2), width="stretch")
    else:
        st.info("No status data yet.")

c3, c4 = st.columns(2)

# Chart 3: Lead Score Distribution
with c3:
    scores = get_score_distribution()
    if scores:
        fig3 = go.Figure(go.Histogram(
            x=scores, nbinsx=10,
            marker_color="#404BCF",
            name="Lead Score",
        ))
        fig3.update_layout(
            title="Lead Score Distribution",
            xaxis_title="Score", yaxis_title="Count",
            template=PLOTLY_TEMPLATE,
        )
        st.plotly_chart(_style(fig3), width="stretch")
    else:
        st.info("No score data yet.")

# Chart 4: Language Breakdown
with c4:
    lang_data = get_leads_by_language()
    if lang_data:
        df_lang = pd.DataFrame(lang_data)
        fig4 = px.pie(
            df_lang, names="language", values="count",
            title="Language Breakdown",
            color_discrete_map={"arabic": "#404BCF", "english": "#26C6DA"},
            template=PLOTLY_TEMPLATE, hole=0.45,
        )
        st.plotly_chart(_style(fig4), width="stretch")
    else:
        st.info("No language data yet.")

c5, c6 = st.columns(2)

# Chart 5: Lead Temperature (hot / warm / cold)
TEMP_COLORS = {"hot": "#EF5350", "warm": "#FFA726", "cold": "#42A5F5"}
TEMP_ORDER = {"hot": 0, "warm": 1, "cold": 2}
with c5:
    temp_data = get_leads_by_temperature()
    if temp_data:
        df_temp = pd.DataFrame(temp_data)
        fig5 = px.pie(
            df_temp, names="temperature", values="count",
            title="Lead Temperature",
            color="temperature", color_discrete_map=TEMP_COLORS,
            template=PLOTLY_TEMPLATE, hole=0.45,
        )
        st.plotly_chart(_style(fig5), width="stretch")
    else:
        st.info("No temperature data yet.")

# Quick hot/warm/cold counts beside the donut
with c6:
    temp_counts = {t["temperature"]: t["count"] for t in get_leads_by_temperature()}
    st.markdown("<br>", unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    m1.metric("🔥 Hot", temp_counts.get("hot", 0))
    m2.metric("🌤️ Warm", temp_counts.get("warm", 0))
    m3.metric("❄️ Cold", temp_counts.get("cold", 0))

st.divider()

# ── Leads Over Time ─────────────────────────────────────────────────────────
st.markdown("### 📈 Leads Over Time")
trend = get_leads_over_time()
if trend:
    df_t = pd.DataFrame(trend)
    df_t["date"] = pd.to_datetime(df_t["date"])
    # fill missing days with 0 so the line is continuous
    full_range = pd.date_range(df_t["date"].min(), df_t["date"].max(), freq="D")
    df_t = (df_t.set_index("date").reindex(full_range, fill_value=0)
            .rename_axis("date").reset_index())
    df_t["cumulative"] = df_t["count"].cumsum()

    # pad x-range by half a day so a single/sparse point sits in a sensible window
    x_min = (df_t["date"].min() - pd.Timedelta(hours=12)).isoformat()
    x_max = (df_t["date"].max() + pd.Timedelta(hours=12)).isoformat()

    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(
        x=df_t["date"], y=df_t["count"], name="New Leads",
        mode="lines+markers", fill="tozeroy", line=dict(color="#404BCF", width=2.5),
        marker=dict(size=7, color="#404BCF"), fillcolor="rgba(64,75,207,0.12)",
    ))
    fig_t.add_trace(go.Scatter(
        x=df_t["date"], y=df_t["cumulative"], name="Cumulative",
        mode="lines+markers", line=dict(color="#26C6DA", width=2, dash="dot"),
        marker=dict(size=6, color="#26C6DA"), yaxis="y2",
    ))
    fig_t.update_layout(
        height=340,
        xaxis=dict(title="", type="date", tickformat="%b %d", range=[x_min, x_max]),
        yaxis=dict(title="New Leads", rangemode="tozero", dtick=1),
        yaxis2=dict(title="Cumulative", overlaying="y", side="right",
                    showgrid=False, rangemode="tozero"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=30, b=10),
    )
    st.plotly_chart(_style(fig_t), width="stretch")
else:
    st.info("No lead history yet.")

st.divider()

# Lead data, full ticket detail and status updates live on the Leads page.
st.page_link("pages/5_Leads.py", label="📋 إدارة العملاء والبيانات · Go to lead management & data")