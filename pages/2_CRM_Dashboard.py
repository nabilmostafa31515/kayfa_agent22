"""
Page 2 — CRM Dashboard
View, search, and filter leads with Plotly analytics charts.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.crm_repository import (
    get_all_leads, search_leads, get_lead_stats,
    get_leads_by_interest, get_leads_by_status,
    get_leads_by_language, get_score_distribution,
    get_leads_over_time, update_lead_status,
)
from src.database.mongodb import ping
from src.ui.branding import page_header, is_dark, active_palette

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
    "لوحة إدارة العملاء",
    subtitle="Kayfa CRM Dashboard — Lead Management",
)

# ── MongoDB status ────────────────────────────────────────────────────────────
db_ok = ping()
if db_ok:
    st.success("✅ Connected to MongoDB Atlas")
else:
    st.error("❌ MongoDB connection failed — check your .env file")
    st.stop()

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
    # Format columns
    df["lead_score"] = df["lead_score"].apply(lambda x: f"{x:.0%}")
    df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
    df = df.rename(columns={
        "_id": "ID", "name": "Name", "phone": "Phone", "email": "Email",
        "language": "Lang", "interest_area": "Interest",
        "recommended_product": "Product", "lead_score": "Score",
        "status": "Status", "created_at": "Created",
    })
    cols_show = ["Name", "Phone", "Email", "Lang", "Interest", "Score", "Status", "Created"]
    st.dataframe(df[cols_show], width="stretch", hide_index=True)

    # Quick status update
    st.divider()
    st.markdown("#### ✏️ Update Lead Status")
    raw_ids = [l["_id"] for l in leads]
    raw_names = [l.get("name", "Unknown") for l in leads]
    options = [f"{n} ({i[:8]}…)" for n, i in zip(raw_names, raw_ids)]
    selected = st.selectbox("Select lead", options)
    new_status = st.selectbox("New status", ["new", "contacted", "qualified", "converted", "lost"])
    if st.button("Update Status", type="primary"):
        idx = options.index(selected)
        lead_id = raw_ids[idx]
        success = update_lead_status(lead_id, new_status)
        if success:
            st.success(f"✅ Status updated to '{new_status}'")
            st.rerun()
        else:
            st.error("Update failed.")