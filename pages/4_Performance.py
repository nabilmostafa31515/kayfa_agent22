"""
Page 4 — Performance Dashboard (manager-only)
Monitor *improvement over time*: week-over-week KPIs, the sales conversion
funnel, conversion-rate trend, and lead-quality (avg score) trend.

Distinct from the CRM Dashboard (which manages individual leads) — this page
answers "are we getting better?".
"""

import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth.manager_auth import require_manager, logout_button
from src.database.crm_repository import (
    get_conversion_summary, get_conversion_funnel, get_weekly_performance,
    FUNNEL_STAGES,
)
from src.database.mongodb import ping
from src.ui.branding import page_header, is_dark, active_palette, inject_global_css

# Re-assert global CSS so a direct/first load is styled (see note in app.py).
inject_global_css()

# ── Auth gate ───────────────────────────────────────────────────────────────────
require_manager()       # renders login + st.stop() when not signed in
logout_button()         # sidebar "signed in as … · Sign out"

_P = active_palette()
PLOTLY_TEMPLATE = "plotly_dark" if is_dark() else "plotly_white"
ACCENT, CYAN = "#404BCF", "#26C6DA"
GOOD, BAD = "#2ea043", "#cf222e"


def _style(fig):
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color=_P["text"],
    )
    return fig


# ── Header ────────────────────────────────────────────────────────────────────
page_header(
    "لوحة الأداء والتحسّن",
    subtitle="Performance Dashboard — track improvement over time",
    rtl=True,
)

if not ping():
    st.error("❌ MongoDB connection failed — check your .env file")
    st.stop()

weekly = get_weekly_performance()
summary = get_conversion_summary()

if summary["total"] == 0:
    st.info("لا توجد بيانات عملاء بعد — ابدأ بمحادثات في المساعد لرؤية مؤشرات الأداء.\n\n"
            "No lead data yet — start some chats in the Assistant to populate metrics.")
    st.stop()

st.divider()


# ── Week-over-week KPIs ─────────────────────────────────────────────────────────
def _wow(field, fmt="int"):
    """Return (current_value, delta_string|None) for the latest vs previous week."""
    if not weekly:
        return (0, None)
    cur = weekly[-1].get(field, 0) or 0
    prev = weekly[-2].get(field, 0) if len(weekly) >= 2 else None
    if fmt == "pct":
        cur_disp = f"{cur:.0%}"
        delta = None if prev is None else f"{(cur - prev) * 100:+.0f} pts"
    elif fmt == "score":
        cur_disp = f"{cur:.2f}"
        delta = None if prev is None else f"{cur - prev:+.2f}"
    else:
        cur_disp = f"{int(cur)}"
        delta = None if prev is None else f"{int(cur - prev):+d}"
    return (cur_disp, delta)

st.markdown("#### 📅 هذا الأسبوع مقابل الأسبوع السابق · This week vs. last week")
k1, k2, k3, k4 = st.columns(4)

v, d = _wow("total")
k1.metric("🆕 New Leads", v, d)
v, d = _wow("conversion_rate", "pct")
k2.metric("✅ Conversion Rate", v, d)
v, d = _wow("avg_score", "score")
k3.metric("📈 Avg Lead Score", v, d)
v, d = _wow("qualified")
k4.metric("🎯 Qualified Leads", v, d)

st.caption(
    f"الإجمالي التراكمي · All-time: {summary['total']} leads · "
    f"{summary['converted']} converted "
    f"({summary['conversion_rate']:.0%}) · "
    f"{summary['qualified']} qualified ({summary['qualified_rate']:.0%})"
)

st.divider()

# ── Conversion funnel ───────────────────────────────────────────────────────────
st.markdown("### 🔻 قمع التحويل · Conversion Funnel")
funnel = get_conversion_funnel()
STAGE_LABELS = {
    "new": "جديد · New", "contacted": "تم التواصل · Contacted",
    "qualified": "مؤهل · Qualified", "converted": "تم التحويل · Converted",
}
fig_funnel = go.Figure(go.Funnel(
    y=[STAGE_LABELS[s] for s in FUNNEL_STAGES],
    x=[next(f["count"] for f in funnel if f["stage"] == s) for s in FUNNEL_STAGES],
    textinfo="value+percent initial",
    marker=dict(color=[ACCENT, "#5965e0", "#8A8FE0", CYAN]),
    connector=dict(line=dict(color=_P["border"], width=1)),
))
fig_funnel.update_layout(height=340, margin=dict(t=10, b=10))
st.plotly_chart(_style(fig_funnel), width="stretch")

st.divider()

# ── Weekly trends ───────────────────────────────────────────────────────────────
df = pd.DataFrame(weekly)
df["week_start"] = pd.to_datetime(df["week_start"])
df = df.sort_values("week_start")
df["cumulative"] = df["total"].cumsum()

if len(df) < 2:
    st.info("📉 أسبوع واحد فقط من البيانات حتى الآن — ستظهر اتجاهات التحسّن مع تراكم بيانات أكثر.\n\n"
            "Only one week of data so far — improvement trends will appear as more accumulates.")

t1, t2 = st.columns(2)

# Conversion rate over time
with t1:
    fig_cr = go.Figure(go.Scatter(
        x=df["week_start"], y=df["conversion_rate"],
        mode="lines+markers", fill="tozeroy",
        line=dict(color=ACCENT, width=2.5), marker=dict(size=8, color=ACCENT),
        fillcolor="rgba(64,75,207,0.12)",
        hovertemplate="%{x|%b %d}<br>Conversion: %{y:.0%}<extra></extra>",
    ))
    fig_cr.update_layout(
        title="معدّل التحويل أسبوعياً · Conversion Rate / Week",
        height=320, yaxis=dict(title="", tickformat=".0%", rangemode="tozero"),
        xaxis=dict(title="", tickformat="%b %d"), margin=dict(t=40, b=10),
    )
    st.plotly_chart(_style(fig_cr), width="stretch")

# Avg lead score (quality) over time
with t2:
    fig_q = go.Figure(go.Scatter(
        x=df["week_start"], y=df["avg_score"],
        mode="lines+markers", fill="tozeroy",
        line=dict(color=CYAN, width=2.5), marker=dict(size=8, color=CYAN),
        fillcolor="rgba(38,198,218,0.12)",
        hovertemplate="%{x|%b %d}<br>Avg score: %{y:.2f}<extra></extra>",
    ))
    fig_q.update_layout(
        title="جودة العملاء (متوسط الدرجة) · Lead Quality (Avg Score)",
        height=320, yaxis=dict(title="", range=[0, 1]),
        xaxis=dict(title="", tickformat="%b %d"), margin=dict(t=40, b=10),
    )
    st.plotly_chart(_style(fig_q), width="stretch")

st.divider()

# ── Volume: new leads per week + cumulative ──────────────────────────────────────
st.markdown("### 📊 حجم العملاء أسبوعياً · Weekly Lead Volume")
fig_vol = go.Figure()
fig_vol.add_trace(go.Bar(
    x=df["week_start"], y=df["total"], name="New Leads",
    marker_color=ACCENT,
    hovertemplate="%{x|%b %d}<br>New: %{y}<extra></extra>",
))
fig_vol.add_trace(go.Bar(
    x=df["week_start"], y=df["converted"], name="Converted",
    marker_color=GOOD,
    hovertemplate="%{x|%b %d}<br>Converted: %{y}<extra></extra>",
))
fig_vol.add_trace(go.Scatter(
    x=df["week_start"], y=df["cumulative"], name="Cumulative",
    mode="lines+markers", line=dict(color=CYAN, width=2, dash="dot"),
    marker=dict(size=6, color=CYAN), yaxis="y2",
    hovertemplate="%{x|%b %d}<br>Total: %{y}<extra></extra>",
))
fig_vol.update_layout(
    height=340, barmode="group",
    xaxis=dict(title="", tickformat="%b %d"),
    yaxis=dict(title="Per week", rangemode="tozero", dtick=1),
    yaxis2=dict(title="Cumulative", overlaying="y", side="right",
                showgrid=False, rangemode="tozero"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(t=30, b=10),
)
st.plotly_chart(_style(fig_vol), width="stretch")
