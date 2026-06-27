"""
Page 10 — Optimization (manager-only)
Analyses collected logs, detects expensive behaviours and shows costed
recommendations (current cost → suggested improvement → estimated savings),
plus a Before-vs-After comparison across saved optimization runs.
"""

import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth.manager_auth import require_manager, logout_button
from src.database.mongodb import ping
from src.ui.branding import page_header, inject_global_css
from src.optimization import analyze
from src.optimization import repository as opt_repo
from src.dashboard.components import (
    kpi_card, style_fig, fmt_usd, fmt_int, fmt_ms, SEVERITY_COLOR,
    ACCENT, CYAN, GOOD,
)

inject_global_css()
require_manager()
logout_button()

page_header(
    "تحسين الأداء والتكلفة",
    subtitle="Optimization — detect expensive behaviour & estimate savings",
    rtl=True,
)

if not ping():
    st.error("❌ MongoDB connection failed — check your .env file")
    st.stop()

tab_live, tab_compare = st.tabs(["⚡ Recommendations", "🔁 Before vs After"])

# ── Live analysis ─────────────────────────────────────────────────────────────────
with tab_live:
    report = analyze()

    if report.window == 0:
        st.info("لا توجد بيانات كافية للتحليل بعد — ابدأ محادثات في المساعد.\n\n"
                "Not enough data to analyse yet — chat in the Assistant first.")
    else:
        k = st.columns(4)
        kpi_card(k[0], "💵", fmt_usd(report.total_cost, 4), "Current Cost (window)")
        kpi_card(k[1], "💚", fmt_usd(report.total_estimated_savings, 4), "Estimated Savings")
        kpi_card(k[2], "🎯", fmt_usd(report.projected_cost, 4), "Projected Cost")
        save_pct = (report.total_estimated_savings / report.total_cost * 100) if report.total_cost else 0
        kpi_card(k[3], "📉", f"{save_pct:.0f}%", "Potential Reduction")

        # Current → Projected bar.
        fig = go.Figure(go.Bar(
            x=["Current Cost", "Projected Cost"],
            y=[report.total_cost, report.projected_cost],
            marker_color=[ACCENT, GOOD],
            text=[fmt_usd(report.total_cost, 4), fmt_usd(report.projected_cost, 4)],
            textposition="outside",
        ))
        fig.update_layout(title="Current → Suggested Improvement", yaxis_title="USD")
        st.plotly_chart(style_fig(fig, height=320), use_container_width=True)

        # Behaviour metrics snapshot.
        with st.expander("📊 Behaviour metrics (analysed window)", expanded=False):
            mt = report.metrics
            mc = st.columns(4)
            mc[0].metric("Avg chunks / msg", mt.get("avg_chunks", 0))
            mc[1].metric("Avg tool calls / msg", mt.get("avg_tool_calls", 0))
            mc[2].metric("Avg tokens / msg", fmt_int(mt.get("avg_total_tokens", 0)))
            mc[3].metric("Avg latency", fmt_ms(mt.get("avg_latency_ms", 0)))
            mc2 = st.columns(4)
            mc2[0].metric("Peak input tok", fmt_int(mt.get("max_input_tokens", 0)))
            mc2[1].metric("Messages", fmt_int(mt.get("messages", 0)))
            mc2[2].metric("LLM calls", fmt_int(mt.get("llm_calls", 0)))
            mc2[3].metric("Parallelizable turns", fmt_int(mt.get("parallelizable_turns", 0)))

        st.divider()
        st.subheader("💡 التوصيات · Recommendations")

        if not report.recommendations:
            st.success("✅ No expensive behaviours detected — the agent is running efficiently.")
        else:
            for r in report.recommendations:
                color = SEVERITY_COLOR.get(r.severity, ACCENT)
                st.markdown(
                    f"<div style='border-left:4px solid {color};padding:6px 14px;margin:8px 0;"
                    f"background:var(--surface);border-radius:8px;'>"
                    f"<b>{r.title}</b> "
                    f"<span class='badge badge-soft' style='margin-inline-start:8px'>{r.category}</span> "
                    f"<span style='color:{color};font-weight:700;margin-inline-start:8px'>"
                    f"{r.severity.upper()}</span><br>"
                    f"<span style='color:var(--muted)'>{r.detail}</span></div>",
                    unsafe_allow_html=True,
                )
                cc = st.columns(3)
                cc[0].metric("Current", r.current_value or "—")
                cc[1].metric("Suggested", r.suggested_value or "—")
                cc[2].metric("Est. savings",
                             fmt_usd(r.estimated_savings, 5),
                             f"{r.estimated_savings_pct:.1f}%" if r.estimated_savings_pct else None)
                if r.latency_note:
                    st.caption(f"⏱️ {r.latency_note}")

            # Summary table.
            df = pd.DataFrame([{
                "Recommendation": r.title,
                "Category": r.category,
                "Severity": r.severity,
                "Current": r.current_value,
                "Suggested": r.suggested_value,
                "Est. savings ($)": round(r.estimated_savings, 6),
                "Savings %": r.estimated_savings_pct,
            } for r in report.recommendations])
            st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()
        cs1, cs2 = st.columns([3, 1])
        label = cs1.text_input("Label this report (optional)",
                               placeholder="e.g. baseline before tuning")
        if cs2.button("💾 Save report", type="primary", use_container_width=True):
            rid = opt_repo.save_report(report, label=label)
            if rid:
                st.success(f"Saved optimization report (ID: {rid}). "
                           "Use the Before vs After tab to compare runs.")
            else:
                st.error("Could not save the report.")

# ── Before vs After ───────────────────────────────────────────────────────────────
with tab_compare:
    st.subheader("🔁 المقارنة قبل/بعد · Before vs After")
    saved = opt_repo.list_reports(50)
    if len(saved) < 1:
        st.info("احفظ تقريرين على الأقل للمقارنة بينهما.\n\n"
                "Save at least one report (two to compare a real before/after).")
    else:
        def _rlabel(r):
            ts = r.get("generated_at")
            ts_txt = ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, "strftime") else str(ts)
            return f"{r.get('label','')} · {ts_txt} · {fmt_usd(r.get('total_cost',0),4)}"

        c1, c2 = st.columns(2)
        before_i = c1.selectbox("Before", range(len(saved)),
                                index=min(1, len(saved) - 1),
                                format_func=lambda i: _rlabel(saved[i]))
        after_i = c2.selectbox("After", range(len(saved)), index=0,
                               format_func=lambda i: _rlabel(saved[i]))
        before, after = saved[before_i], saved[after_i]

        b_cost = before.get("total_cost", 0.0)
        a_cost = after.get("total_cost", 0.0)
        delta = b_cost - a_cost
        delta_pct = (delta / b_cost * 100) if b_cost else 0.0

        k = st.columns(3)
        kpi_card(k[0], "⬅️", fmt_usd(b_cost, 4), "Before — Total Cost")
        kpi_card(k[1], "➡️", fmt_usd(a_cost, 4), "After — Total Cost")
        kpi_card(k[2], "📉", fmt_usd(delta, 4), f"Saved ({delta_pct:.0f}%)")

        # Compare key behaviour metrics side by side.
        bm, am = before.get("metrics", {}), after.get("metrics", {})
        fields = [
            ("avg_total_tokens", "Avg tokens / msg"),
            ("avg_chunks", "Avg chunks / msg"),
            ("avg_tool_calls", "Avg tool calls / msg"),
            ("avg_latency_ms", "Avg latency (ms)"),
            ("avg_cost_per_message", "Avg cost / msg"),
        ]
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Before", x=[lbl for _, lbl in fields],
                             y=[bm.get(f, 0) for f, _ in fields], marker_color=ACCENT))
        fig.add_trace(go.Bar(name="After", x=[lbl for _, lbl in fields],
                             y=[am.get(f, 0) for f, _ in fields], marker_color=GOOD))
        fig.update_layout(barmode="group", title="Behaviour metrics — Before vs After")
        st.plotly_chart(style_fig(fig, height=380), use_container_width=True)

        comp = pd.DataFrame([{
            "Metric": lbl,
            "Before": bm.get(f, 0),
            "After": am.get(f, 0),
            "Δ": round((bm.get(f, 0) or 0) - (am.get(f, 0) or 0), 4),
        } for f, lbl in fields])
        st.dataframe(comp, use_container_width=True, hide_index=True)
