"""
Branding & theming for the Kayfa AI Agent — a small design system.

Public API:
    LOGO_PATH, PAGE_ICON, LOGO_FALLBACK_EMOJI
    is_dark(), active_palette()
    inject_global_css()
    theme_toggle()
    show_sidebar_logo()
    brand_mark(size_px)        -> HTML string for a clean logo chip
    page_header(title, subtitle=None, icon=None, badge=None)
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

# ── Logo discovery ──────────────────────────────────────────────────────────────
# branding.py lives at: kayfa_agent/src/ui/branding.py
# parents[0]=ui  parents[1]=src  parents[2]=kayfa_agent (project root)
_ROOT = Path(__file__).resolve().parents[2]
_LOGO_CANDIDATES = [
    _ROOT / "logo.jpg",
    _ROOT / "logo.png",
    _ROOT / "assets" / "logo.png",
    _ROOT / "assets" / "logo.jpg",
    _ROOT / "assets" / "logo.svg",
    _ROOT / "data" / "logo.png",
]
LOGO_PATH = next((str(p) for p in _LOGO_CANDIDATES if p.exists()), None)
LOGO_FALLBACK_EMOJI = "🎓"

# st.set_page_config(page_icon=...) needs a non-None value
PAGE_ICON = LOGO_PATH if LOGO_PATH else LOGO_FALLBACK_EMOJI


# ── Palettes ────────────────────────────────────────────────────────────────────
# Light is the default (matches .streamlit/config.toml base="light" so native
# Streamlit widgets stay visually consistent with the custom CSS).
_LIGHT = {
    "bg":        "#f6f7fb",
    "surface":   "#ffffff",
    "surface2":  "#f1f3fa",
    "border":    "#e3e6f0",
    "accent":    "#404bcf",
    "accent2":   "#5965e0",
    "cyan":      "#0e9bb0",
    "text":      "#1b1f33",
    "muted":     "#6b7390",
    "shadow":    "0 8px 24px rgba(27,31,51,.08)",
    "chip_bg":   "#eef0fb",
}
_DARK = {
    "bg":        "#0e1018",
    "surface":   "#171a24",
    "surface2":  "#1e2230",
    "border":    "#2a2f42",
    "accent":    "#6c78ff",
    "accent2":   "#8a93ff",
    "cyan":      "#34d3e8",
    "text":      "#e8eaf6",
    "muted":     "#9aa3bd",
    "shadow":    "0 10px 30px rgba(0,0,0,.45)",
    "chip_bg":   "rgba(108,120,255,.14)",
}


def is_dark() -> bool:
    return st.session_state.get("_theme", "light") == "dark"


def active_palette() -> dict:
    return _DARK if is_dark() else _LIGHT


# ── Logo helpers ────────────────────────────────────────────────────────────────
def _img_to_base64(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


def brand_mark(size_px: int = 64) -> str:
    """Return HTML for the logo inside a clean white rounded chip.

    The source logo sits on a white background, so we always frame it on a
    white card with a soft border + shadow — that reads as an intentional
    brandmark on both light and dark themes (no raw white square).
    """
    if LOGO_PATH:
        b64 = _img_to_base64(LOGO_PATH)
        if b64:
            ext = Path(LOGO_PATH).suffix.lstrip(".") or "png"
            pad = max(8, size_px // 7)
            return (
                f"<span class='k-logo-chip' style='padding:{pad}px;'>"
                f"<img src='data:image/{ext};base64,{b64}' "
                f"style='height:{size_px}px;width:auto;display:block;' alt='Kayfa'>"
                f"</span>"
            )
    return f"<span class='k-logo-chip k-logo-chip--text'>{LOGO_FALLBACK_EMOJI} Kayfa</span>"


def logo_data_uri() -> str | None:
    """Return the logo as a `data:` URI for embedding in custom HTML (e.g. the
    chat avatar), or None if no logo asset is available."""
    if LOGO_PATH:
        b64 = _img_to_base64(LOGO_PATH)
        if b64:
            ext = Path(LOGO_PATH).suffix.lstrip(".") or "png"
            return f"data:image/{ext};base64,{b64}"
    return None


def show_sidebar_logo():
    with st.sidebar:
        # Clickable brand → Home. Inline <span>s only: block tags inside an <a>
        # get split out by Streamlit's markdown sanitizer.
        st.markdown(
            "<a class='k-sidebar-brand' href='./' target='_self'>"
            f"{brand_mark(40)}"
            "<span class='k-sidebar-brand__text'>"
            "<span class='k-sidebar-brand__name'>Kayfa&nbsp;AI</span>"
            "<span class='k-sidebar-brand__tag'>Sales&nbsp;Assistant</span>"
            "</span>"
            "</a>",
            unsafe_allow_html=True,
        )


def page_header(title: str, subtitle: str | None = None,
                icon: str | None = None, badge: str | None = None,
                logo_size: int = 88, rtl: bool = False):
    """Render a consistent page header: a big logo.jpg brandmark + title.

    By default the logo sits on the left with the title beside it (LTR). Pass
    ``rtl=True`` for an Arabic-first layout: the logo moves to the right with
    the title flowing right-to-left beside it.
    """
    badge_html = f"<span class='badge badge-soft'>{badge}</span>" if badge else ""
    icon_html = f"<span class='k-page-header__icon'>{icon}</span>" if icon else ""
    sub_html = f"<p class='k-page-header__sub'>{subtitle}</p>" if subtitle else ""
    # Emit as a single line — multi-line indented HTML can be misread by the
    # markdown parser as an indented code block (esp. when a piece is empty).
    # dir pins the layout direction: 'ltr' → logo left; 'rtl' → logo right with
    # the title/subtitle right-aligned (the layout stays consistent regardless
    # of the title's script).
    direction = "rtl" if rtl else "ltr"
    html = (
        f"<div class='k-page-header' dir='{direction}'>"
        f"<div class='k-page-header__brand'>{brand_mark(logo_size)}</div>"
        "<div class='k-page-header__body'>"
        "<div class='k-page-header__row'>"
        f"<h1 class='k-page-header__title'>{icon_html}{title}</h1>{badge_html}"
        "</div>"
        f"{sub_html}"
        "</div>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ── Theme toggle ─────────────────────────────────────────────────────────────────
def theme_toggle():
    with st.sidebar:
        st.markdown("<div class='k-theme-toggle'>", unsafe_allow_html=True)
        current = st.session_state.get("_theme", "light")
        label = "🌙  Dark mode" if current == "light" else "☀️  Light mode"
        if st.button(label, key="_theme_btn", use_container_width=True):
            st.session_state["_theme"] = "dark" if current == "light" else "light"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# ── Global CSS ──────────────────────────────────────────────────────────────────
def inject_global_css():
    p = active_palette()
    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@400;500;600;700;800&display=swap');

:root {{
  --bg:{p['bg']}; --surface:{p['surface']}; --surface2:{p['surface2']};
  --border:{p['border']}; --accent:{p['accent']}; --accent2:{p['accent2']};
  --cyan:{p['cyan']}; --text:{p['text']}; --muted:{p['muted']};
  --shadow:{p['shadow']}; --chip-bg:{p['chip_bg']};
  --radius:16px;
}}

html, body, [class*="css"], .stApp, button, input, textarea {{
  font-family:'Inter','Tajawal',system-ui,sans-serif;
}}
.stApp {{ background:var(--bg)!important; color:var(--text); }}
.block-container {{ padding-top:2.2rem; max-width:1180px; }}

/* Hide Streamlit chrome */
#MainMenu, footer, [data-testid="stToolbar"] {{ visibility:hidden; }}
header[data-testid="stHeader"] {{ background:transparent; height:0; }}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {{
  background:var(--surface)!important;
  border-right:1px solid var(--border);
}}
section[data-testid="stSidebar"] .block-container {{ padding-top:1rem; }}

.k-sidebar-brand {{
  display:flex; align-items:center; gap:12px; padding:8px 8px 10px; margin-bottom:4px;
  border-radius:12px; text-decoration:none !important; cursor:pointer;
  transition:background .15s ease;
}}
.k-sidebar-brand:hover {{ background:var(--chip-bg); }}
.k-sidebar-brand__text {{ display:flex; flex-direction:column; }}
.k-sidebar-brand__name {{
  display:block; font-weight:800; font-size:1.05rem; color:var(--text) !important; line-height:1.1;
}}
.k-sidebar-brand:hover .k-sidebar-brand__name {{ color:var(--accent) !important; }}
.k-sidebar-brand__tag  {{ display:block; font-size:.72rem; color:var(--muted) !important; letter-spacing:.02em; }}

/* Logo chip — frames the white-bg logo cleanly on any theme */
.k-logo-chip {{
  display:inline-flex; align-items:center; justify-content:center;
  background:#ffffff; border:1px solid var(--border);
  border-radius:14px; box-shadow:var(--shadow);
}}
.k-logo-chip--text {{ padding:8px 14px; font-weight:800; color:var(--accent); }}

/* ── Sidebar nav links (st.navigation) ── */
[data-testid="stSidebarNav"] {{ padding-top:.25rem; }}
[data-testid="stSidebarNav"] ul {{ gap:2px; }}
[data-testid="stSidebarNav"] a {{
  border-radius:10px; padding:.5rem .7rem; margin:1px 0;
  transition:background .15s, color .15s;
}}
/* Force nav text to follow the active theme (Streamlit otherwise colors it
   from the static config, going invisible in dark mode). */
[data-testid="stSidebarNav"] a span,
[data-testid="stSidebarNav"] a p {{ color:var(--text)!important; }}
[data-testid="stSidebarNav"] a:hover {{ background:var(--chip-bg); }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{
  background:var(--accent)!important;
}}
[data-testid="stSidebarNav"] a[aria-current="page"] span,
[data-testid="stSidebarNav"] a[aria-current="page"] p {{ color:#fff!important; }}

/* ── Page header (big logo + title bar) ── */
.k-page-header {{
  display:flex; align-items:center; gap:20px; margin-bottom:.6rem;
  padding-bottom:18px; border-bottom:1px solid var(--border);
}}
.k-page-header__brand {{ flex:0 0 auto; }}
.k-page-header__body {{ flex:1 1 auto; min-width:0; }}
.k-page-header__row {{ display:flex; align-items:center; gap:14px; flex-wrap:wrap; }}
.k-page-header__title {{
  margin:0; font-size:1.9rem; font-weight:800; letter-spacing:-.01em; color:var(--text);
  display:inline-flex; align-items:center; gap:10px;
}}
.k-page-header__icon {{ font-size:1.6rem; }}
.k-page-header__sub {{
  color:var(--muted); margin:.4rem 0 0; font-size:1rem;
  /* Direction follows the text: Arabic → RTL (right-aligned), English → LTR. */
  unicode-bidi:plaintext; text-align:start;
}}
/* In an RTL header the title sits on the right beside the logo — pin the
   subtitle to the right too, even when it's English (plaintext would otherwise
   left-align it). */
.k-page-header[dir='rtl'] .k-page-header__sub {{ text-align:right; }}
.k-page-header[dir='rtl'] .k-page-header__row {{ justify-content:flex-start; }}

/* ── Hero (landing) ── */
.k-hero {{ text-align:center; padding:14px 16px 6px; }}
.k-hero h1 {{
  font-size:2.6rem; font-weight:800; letter-spacing:-.02em; margin:.4rem 0 .2rem;
  background:linear-gradient(90deg,var(--accent),var(--cyan));
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent;
}}
.k-hero .k-hero__ar {{ font-size:1.15rem; color:var(--text); font-weight:700; }}
.k-hero .k-hero__en {{ font-size:1rem; color:var(--muted); margin-top:2px; }}

/* ── Chips row ── */
.k-chips {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:center; margin:16px 0 6px; }}
.k-chip {{
  background:var(--chip-bg); color:var(--accent); border:1px solid var(--border);
  padding:6px 14px; border-radius:999px; font-size:.82rem; font-weight:600;
}}

/* ── Cards ── */
.k-card {{
  background:var(--surface); border:1px solid var(--border);
  border-radius:var(--radius); padding:22px 20px; box-shadow:var(--shadow);
  height:100%;
}}
.k-card h3 {{ margin:.1rem 0 .4rem; font-size:1.15rem; color:var(--text); display:flex; gap:8px; align-items:center; }}
.k-card p {{ color:var(--muted); margin:0; font-size:.92rem; line-height:1.6; }}

/* Clickable card (whole box is a link). Inner elements are inline <span>s
   styled as blocks — block tags inside <a> get split out by Streamlit's
   markdown sanitizer, which breaks the card into empty fragments. */
.k-card--link {{
  display:block; cursor:pointer; text-decoration:none !important;
  transition:transform .15s ease, box-shadow .15s ease, border-color .15s ease;
}}
.k-card--link:hover {{
  transform:translateY(-4px); border-color:var(--accent);
  box-shadow:0 16px 36px rgba(64,75,207,.20);
}}
.k-card__title, .k-card__desc, .k-card__cta {{ display:block; text-decoration:none !important; }}
.k-card__title {{
  font-size:1.15rem; font-weight:700; color:var(--text) !important; margin-bottom:8px;
}}
.k-card--link:hover .k-card__title {{ color:var(--accent) !important; }}
.k-card__desc {{ color:var(--muted) !important; font-size:.92rem; line-height:1.6; }}
.k-card__cta {{ margin-top:14px; color:var(--accent) !important; font-weight:700; font-size:.9rem; }}

/* ── KPI cards ── */
.kpi-card {{
  background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
  padding:18px 16px; text-align:center; box-shadow:var(--shadow);
  transition:transform .15s ease, box-shadow .15s ease;
}}
.kpi-card:hover {{ transform:translateY(-3px); }}
.kpi-icon  {{ font-size:1.5rem; }}
.kpi-value {{ font-size:1.9rem; font-weight:800; color:var(--accent); line-height:1.2; margin-top:2px; }}
.kpi-label {{ color:var(--muted); font-size:.8rem; margin-top:2px; }}

/* ── Badges ── */
.badge {{ display:inline-block; padding:4px 12px; border-radius:999px; font-size:.76rem; font-weight:700; }}
.badge-soft {{ background:var(--chip-bg); color:var(--accent); border:1px solid var(--border); }}
.badge-low  {{ background:rgba(46,160,67,.16);  color:#2ea043; }}
.badge-mid  {{ background:rgba(219,109,0,.16);  color:#db6d00; }}
.badge-high {{ background:rgba(207,34,46,.16);  color:#cf222e; }}

/* ── Buttons ── */
.stButton > button, .stFormSubmitButton > button {{
  border-radius:10px!important; border:1px solid var(--border)!important;
  background:var(--surface); color:var(--text); font-weight:600;
  transition:background .15s, color .15s, border-color .15s, transform .08s;
}}
.stButton > button:hover, .stFormSubmitButton > button:hover {{
  background:var(--accent)!important; color:#fff!important; border-color:var(--accent)!important;
}}
.stButton > button:active {{ transform:scale(.98); }}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background:var(--accent)!important; color:#fff!important; border-color:var(--accent)!important;
}}

/* ── Page links styled as cards/buttons ── */
[data-testid="stPageLink"] a {{
  border:1px solid var(--border); border-radius:12px; background:var(--accent);
  padding:.6rem 1rem; justify-content:center; transition:filter .15s, transform .08s;
}}
[data-testid="stPageLink"] a:hover {{ filter:brightness(1.08); transform:translateY(-1px); }}
[data-testid="stPageLink"] a span, [data-testid="stPageLink"] a p {{ color:#fff!important; font-weight:700; }}

/* ── Inputs ── */
.stTextInput input, .stTextArea textarea,
.stSelectbox div[data-baseweb="select"], [data-testid="stChatInput"] {{
  border-radius:10px!important;
}}
/* Bidi-aware fields: typed text (and its placeholder) follow their own
   direction — Arabic → RTL, English → LTR — mirroring the .k-msg chat output.
   `plaintext` resolves direction from the first strong character per line, so
   the same box flips correctly as the user switches language. */
.stTextInput input, .stTextArea textarea, [data-testid="stChatInput"] textarea {{
  unicode-bidi:plaintext !important; text-align:start !important;
}}

/* ── RTL form (Arabic-first lead capture) ── */
/* The lead form is wrapped in st.container(key="lead-form-rtl"), which Streamlit
   renders with a real `.st-key-lead-form-rtl` class — a reliable scope (the old
   empty-<span> + :has() marker got stripped by Streamlit's HTML sanitizer).
   Everything inside flips to RTL: labels right-align, the 2-col rows lay out
   right→left (name on the right via direction:rtl), and field text/placeholders
   start at the right edge. Scoped here so the composer / other pages stay LTR. */
.st-key-lead-form-rtl {{ direction:rtl; text-align:right; }}
/* Labels + help/tooltip → right-aligned */
.st-key-lead-form-rtl [data-testid="stWidgetLabel"] p,
.st-key-lead-form-rtl [data-testid="stWidgetLabel"] label,
.st-key-lead-form-rtl [data-testid="stTooltipIcon"],
.st-key-lead-form-rtl small {{
  text-align:right; width:100%;
}}
/* Field contents (typed text, placeholders, selectbox value) → start at the
   right edge. plaintext still lets an English email/phone read L-to-R inside. */
.st-key-lead-form-rtl input,
.st-key-lead-form-rtl textarea,
.st-key-lead-form-rtl div[data-baseweb="select"] > div {{
  text-align:right !important; unicode-bidi:plaintext !important;
}}
.st-key-lead-form-rtl input::placeholder,
.st-key-lead-form-rtl textarea::placeholder {{
  text-align:right; direction:rtl;
}}
/* Note: direction:rtl already lays the 2-column rows right→left (first field on
   the right), so we must NOT also flex-reverse them — that would cancel out. */

/* ── Chat — custom message bubbles ── */
/* Each message is its own st.markdown block: a flex row (.k-row) holding an
   avatar + a bubble. User rows reverse so the accent bubble sits on the right;
   assistant rows keep the avatar on the left. */
.k-row {{ display:flex; align-items:flex-end; gap:10px; margin:2px 0; animation:kIn .28s ease both; }}
.k-row--user {{ flex-direction:row-reverse; }}
.k-avatar {{
  flex:0 0 auto; width:34px; height:34px; border-radius:50%;
  background:#fff; border:1px solid var(--border); box-shadow:var(--shadow);
  display:flex; align-items:center; justify-content:center; overflow:hidden;
}}
.k-avatar img {{ width:24px; height:auto; display:block; }}
.k-avatar--emoji {{ font-size:1.1rem; }}
.k-bubble {{
  max-width:76%; padding:11px 15px 9px; border-radius:16px;
  box-shadow:var(--shadow); font-size:.97rem; line-height:1.7;
}}
.k-bubble--bot {{
  background:var(--surface); border:1px solid var(--border);
  color:var(--text); border-bottom-left-radius:5px;
}}
.k-bubble--user {{
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#fff; border-bottom-right-radius:5px;
}}
.k-bubble--user a {{ color:#fff; text-decoration:underline; }}
/* Bilingual RTL/LTR: `.k-msg dir="auto"` lets direction follow content;
   logical padding keeps Arabic bullets on the right edge. */
.k-msg p, .k-msg li, .k-msg h1, .k-msg h2, .k-msg h3, .k-msg h4 {{
  unicode-bidi:plaintext; text-align:start;
}}
.k-msg p:first-child {{ margin-top:0; }}
.k-msg p:last-child {{ margin-bottom:0; }}
.k-msg ul, .k-msg ol {{ padding-inline-start:1.3em; margin:.3em 0; }}
.k-time {{ display:block; font-size:.68rem; opacity:.6; margin-top:5px; text-align:end; }}
.k-bubble--user .k-time {{ color:#eaecff; opacity:.85; }}

@keyframes kIn {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:none; }} }}

/* Typing indicator (shown while the agent thinks, before the first token) */
.k-typing {{ display:inline-flex; gap:5px; align-items:center; padding:3px 2px; }}
.k-typing span {{
  width:7px; height:7px; border-radius:50%; background:var(--muted);
  animation:kBlink 1.2s infinite ease-in-out;
}}
.k-typing span:nth-child(2) {{ animation-delay:.2s; }}
.k-typing span:nth-child(3) {{ animation-delay:.4s; }}
@keyframes kBlink {{ 0%,80%,100% {{ opacity:.25; transform:translateY(0); }} 40% {{ opacity:1; transform:translateY(-3px); }} }}

/* Suggested follow-up chips label */
.k-suggest-label {{ color:var(--muted); font-size:.8rem; font-weight:600; margin:10px 2px 2px; }}

/* Ticket detail (CRM) — single-language, RTL, aligned rows */
.k-ticket {{
  background:var(--surface); border:1px solid var(--border); border-radius:12px;
  padding:14px 16px; box-shadow:var(--shadow); margin-bottom:8px;
}}
.k-ticket__group + .k-ticket__group {{ margin-top:14px; padding-top:12px; border-top:1px solid var(--border); }}
.k-ticket__head {{ font-weight:800; color:var(--accent); font-size:.95rem; margin-bottom:6px; }}
.k-ticket__row {{ display:flex; gap:12px; padding:5px 0; border-bottom:1px dashed var(--border); font-size:.9rem; }}
.k-ticket__row:last-child {{ border-bottom:none; }}
.k-ticket__label {{ flex:0 0 42%; color:var(--muted); font-weight:600; }}
.k-ticket__val {{ flex:1 1 auto; unicode-bidi:plaintext; color:var(--text); word-break:break-word; }}

/* Polished welcome / empty state */
.k-welcome {{ text-align:center; padding:24px 14px 6px; }}
.k-welcome__wave {{ font-size:2.6rem; display:inline-block; animation:kFloat 3s ease-in-out infinite; }}
.k-welcome h3 {{ margin:8px 0 4px; font-size:1.4rem; color:var(--text); font-weight:800; }}
.k-welcome p {{ color:var(--muted); margin:0; }}
@keyframes kFloat {{ 0%,100% {{ transform:translateY(0); }} 50% {{ transform:translateY(-6px); }} }}

/* ── Manager login ── */
.k-login {{ text-align:center; padding:26px 14px 8px; }}
.k-login__brand {{ display:flex; justify-content:center; margin-bottom:10px; }}
.k-login__title {{
  margin:.3rem 0 .1rem; font-size:1.5rem; font-weight:800; color:var(--text);
  unicode-bidi:plaintext;
}}
.k-login__sub {{ color:var(--muted); margin:0; font-size:.95rem; unicode-bidi:plaintext; }}
.k-gate-note {{
  background:var(--chip-bg); border:1px solid var(--border); border-radius:12px;
  padding:12px 16px; margin-bottom:14px; color:var(--text); font-weight:600;
  text-align:center; unicode-bidi:plaintext;
}}
.k-gate-note span {{ color:var(--muted); font-weight:500; font-size:.86rem; }}
.k-signed-in {{
  background:var(--chip-bg); border:1px solid var(--border); border-radius:10px;
  padding:8px 12px; margin:6px 0 4px; font-size:.86rem; color:var(--text);
}}
.k-signed-in span {{ color:var(--muted); }}

/* ── Misc ── */
hr {{ border-color:var(--border)!important; }}
[data-testid="stMetricValue"] {{ color:var(--accent); }}
.k-footer {{ text-align:center; color:var(--muted); font-size:.82rem; padding:26px 0 6px; }}
.k-footer a {{ color:var(--accent); text-decoration:none; }}
</style>
""",
        unsafe_allow_html=True,
    )
