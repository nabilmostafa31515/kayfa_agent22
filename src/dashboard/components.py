"""Reusable Streamlit/Plotly building blocks for the monitoring pages.

Consistent with Part 1's branding (``active_palette`` / ``is_dark`` / KPI card
CSS) so the new pages feel native. Importing this module does not touch Part 1.
"""

from __future__ import annotations

import streamlit as st

from src.ui.branding import is_dark, active_palette

# Brand palette (matches existing dashboards).
ACCENT = "#404BCF"
ACCENT2 = "#5965e0"
CYAN = "#26C6DA"
GOOD = "#2ea043"
WARN = "#db6d00"
BAD = "#cf222e"

SEVERITY_COLOR = {"high": BAD, "medium": WARN, "low": GOOD}


def plotly_template() -> str:
    return "plotly_dark" if is_dark() else "plotly_white"


def style_fig(fig, height: int | None = None):
    """Apply the shared transparent, theme-aware Plotly styling."""
    p = active_palette()
    fig.update_layout(
        template=plotly_template(),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color=p["text"], margin=dict(t=40, b=10, l=10, r=10),
    )
    if height:
        fig.update_layout(height=height)
    return fig


def kpi_card(col, icon: str, value, label: str) -> None:
    """Render one KPI card (reuses the .kpi-card CSS from branding.py)."""
    col.markdown(
        f"<div class='kpi-card'><div class='kpi-icon'>{icon}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-label'>{label}</div></div>",
        unsafe_allow_html=True,
    )


def fmt_usd(value: float, places: int = 4) -> str:
    try:
        return f"${value:,.{places}f}"
    except (TypeError, ValueError):
        return "$0.0000"


def fmt_int(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def fmt_ms(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "0 ms"
    if v >= 1000:
        return f"{v / 1000:.2f} s"
    return f"{v:.0f} ms"


def short_id(value: str, head: int = 8) -> str:
    if not value:
        return "—"
    return value if len(value) <= head + 3 else f"{value[:head]}…"


def resolve_user_label(user_id: str) -> str:
    """Map a user_id to a readable email/name (cached per session)."""
    if not user_id or user_id in ("", "—", "anonymous"):
        return "anonymous"
    cache = st.session_state.setdefault("_user_label_cache", {})
    if user_id in cache:
        return cache[user_id]
    label = user_id
    try:
        from src.database.users_repository import get_user_by_id
        info = get_user_by_id(user_id)
        if info:
            label = info.get("email") or info.get("name") or user_id
    except Exception:
        pass
    cache[user_id] = label
    return label
