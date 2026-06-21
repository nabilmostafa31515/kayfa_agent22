"""
Page 1 — Chat Assistant
Bilingual (Arabic / English) chat with modern message bubbles, streamed
responses, timestamps, suggested follow-ups, and lead capture.
"""

import re
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# TEMP DIAGNOSTIC — surface the real cause of the Streamlit Cloud ImportError
# directly on the page (the UI message is redacted). Remove once resolved.
try:
    from src.agents.lead_qualifier import (
        is_qualified, lead_temperature, detect_dialect,
        detect_current_level, detect_budget_sensitivity,
    )
except Exception as _imp_err:
    import traceback as _tb
    st.error(f"🩺 import failed → {type(_imp_err).__name__}: {_imp_err}")
    st.code("Python: " + sys.version)
    try:
        import importlib as _il
        _lq = _il.import_module("src.agents.lead_qualifier")
        st.code("lead_qualifier path: " + getattr(_lq, "__file__", "?"))
        st.code("names available: "
                + ", ".join(n for n in dir(_lq) if not n.startswith("_")))
    except Exception as _e2:
        st.code("module import error:\n" + _tb.format_exc())
    st.stop()
from src.database.crm_repository import create_lead
from src.ui.branding import page_header, logo_data_uri, inject_global_css

# Re-assert the global CSS from within the page itself. app.py injects it before
# nav.run(), but on a first/direct page load that pre-nav <style> doesn't stick
# until a rerun — injecting here guarantees the styling is present on first paint.
inject_global_css()

# NOTE: the agent (`stream_chat`) is imported lazily inside the response handler
# below — its dependency stack (langgraph + langchain + sentence-transformers)
# takes ~30s+ to import. Lazy import lets the chat UI appear instantly; the
# one-time cost is paid under the typing indicator on the first message.

AVATAR_URI = logo_data_uri()


def _now() -> str:
    return datetime.now().strftime("%H:%M")


# ── Message rendering (custom bubbles) ──────────────────────────────────────────
def _avatar_div() -> str:
    if AVATAR_URI:
        return f"<div class='k-avatar'><img src='{AVATAR_URI}' alt='Kayfa'></div>"
    return "<div class='k-avatar k-avatar--emoji'>🎓</div>"


def _row_html(role: str, content: str, ts: str = "") -> str:
    """Build one chat row. Content is wrapped in `.k-msg` with blank lines so
    Streamlit still renders it as markdown, and dir='auto' so direction follows
    the content (Arabic → RTL, English → LTR)."""
    time_html = f"<span class='k-time'>{ts}</span>" if ts else ""
    msg = f"<div class='k-msg' dir='auto'>\n\n{content}\n\n</div>"
    if role == "user":
        return ("<div class='k-row k-row--user'>"
                f"<div class='k-bubble k-bubble--user'>{msg}{time_html}</div>"
                "</div>")
    return ("<div class='k-row k-row--bot'>"
            f"{_avatar_div()}"
            f"<div class='k-bubble k-bubble--bot'>{msg}{time_html}</div>"
            "</div>")


def _typing_html() -> str:
    return ("<div class='k-row k-row--bot'>"
            f"{_avatar_div()}"
            "<div class='k-bubble k-bubble--bot'>"
            "<div class='k-typing'><span></span><span></span><span></span></div>"
            "</div></div>")


def _render_message(msg: dict):
    st.markdown(_row_html(msg["role"], msg["content"], msg.get("time", "")),
                unsafe_allow_html=True)


# ── Lead-form validation (bilingual messages) ───────────────────────────────────
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# E.164-style: a leading "+" then a country code (1–9) and 6–14 more digits.
# Requiring the "+" guarantees the country code is present.
_PHONE_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def _validate_lead(name: str, phone: str, email: str) -> list[str]:
    """Return a list of human-readable errors; empty list means valid."""
    errors = []
    if not name.strip():
        errors.append("الاسم مطلوب — Name is required")
    if not phone.strip():
        errors.append("رقم الهاتف مطلوب — Phone is required")
    elif not _PHONE_RE.match(re.sub(r"[\s\-()]", "", phone.strip())):
        # Must be an international number that includes the country code.
        errors.append("أدخل رقم هاتف دولي يشمل رمز الدولة، مثل ‎+20 10 1234 5678 — "
                      "Enter a valid international phone with country code (e.g. +20 10 1234 5678)")
    if not email.strip():
        errors.append("البريد الإلكتروني مطلوب — Email is required")
    elif not _EMAIL_RE.match(email.strip()):
        errors.append("بريد إلكتروني غير صالح — Enter a valid email address")
    return errors


# ── Suggested follow-ups (contextual, bilingual; no extra LLM call) ─────────────
FOLLOWUPS = {
    "browsing": {
        "arabic": ["ما المسارات المتاحة؟", "أنا مبتدئ، من أين أبدأ؟", "ما الفرق بين الكورس والمسار؟"],
        "english": ["What tracks are available?", "I'm a beginner — where do I start?", "Course vs. track?"],
    },
    "exploring": {
        "arabic": ["كم مدة الدراسة؟", "ما تفاصيل المحتوى؟", "هل أحصل على شهادة؟"],
        "english": ["How long is it?", "What's in the curriculum?", "Do I get a certificate?"],
    },
    "comparing": {
        "arabic": ["أيهما أنسب لي؟", "ما الفرق في السعر؟", "أيهما أسرع للتوظيف؟"],
        "english": ["Which fits me better?", "How do the prices differ?", "Which leads to a job faster?"],
    },
    "price_sensitive": {
        "arabic": ["هل يوجد خصم؟", "هل يمكن التقسيط؟", "ما طرق الدفع؟"],
        "english": ["Any discounts?", "Can I pay in installments?", "What payment methods?"],
    },
    "objecting": {
        "arabic": ["كم الوقت الأسبوعي المطلوب؟", "هل الدراسة مرنة؟", "هل يوجد دعم ومتابعة؟"],
        "english": ["How many hours a week?", "Is it flexible?", "Is there mentorship?"],
    },
    "ready": {
        "arabic": ["كيف أسجّل الآن؟", "ما الخطوة التالية؟", "متى تبدأ الدفعة القادمة؟"],
        "english": ["How do I enroll now?", "What's the next step?", "When does the next cohort start?"],
    },
}


def _queue_user_message(text: str):
    st.session_state.messages.append({"role": "user", "content": text, "time": _now()})
    st.rerun()


# ── Session state ──────────────────────────────────────────────────────────────
defaults = {
    "messages": [], "lead_score": 0.0, "intent_stage": "browsing",
    "language": "arabic", "lead_saved": False, "show_lead_form": False,
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# ── Header ─────────────────────────────────────────────────────────────────────
page_header(
    "المساعد الذكي",
    subtitle="اسألني عن الكورسات والمسارات والدبلومات — بالعربية أو الإنجليزية",
    badge="Kayfa AI Sales Agent",
)

# ── Status bar ────────────────────────────────────────────────────────────────
score = st.session_state.lead_score
score_class = "badge-high" if score >= 0.6 else ("badge-mid" if score >= 0.35 else "badge-low")
lang_label = "🇸🇦 Arabic" if st.session_state.language == "arabic" else "🇬🇧 English"

c1, c2, c3 = st.columns(3)
c1.markdown(f"<div style='text-align:center;'><small style='color:var(--muted);'>Lead Score</small><br>"
            f"<span class='badge {score_class}'>{score:.0%}</span></div>", unsafe_allow_html=True)
c2.markdown(f"<div style='text-align:center;'><small style='color:var(--muted);'>Intent</small><br>"
            f"<span class='badge badge-soft'>{st.session_state.intent_stage}</span></div>", unsafe_allow_html=True)
c3.markdown(f"<div style='text-align:center;'><small style='color:var(--muted);'>Language</small><br>"
            f"<span class='badge badge-soft'>{lang_label}</span></div>", unsafe_allow_html=True)

st.divider()

# ── Welcome / empty state ───────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown(
        "<div class='k-welcome'>"
        "<span class='k-welcome__wave'>👋</span>"
        "<h3>أهلاً بك في مساعد كيفا</h3>"
        "<p>اسألني عن أي كورس أو مسار تعليمي — Ask me anything about Kayfa's courses &amp; tracks.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='k-suggest-label'>جرّب أحد هذه الأسئلة — Try one of these</div>",
                unsafe_allow_html=True)

    starters = [
        ("🎓", "ما هي دبلومة الذكاء الاصطناعي؟"),
        ("🛣️", "اعرض لي المسارات التعليمية المتاحة"),
        ("🛡️", "What cybersecurity tracks do you offer?"),
        ("💡", "أنا مبتدئ، من أين أبدأ؟"),
    ]
    sc1, sc2 = st.columns(2)
    for i, (icon, text) in enumerate(starters):
        col = sc1 if i % 2 == 0 else sc2
        if col.button(f"{icon}  {text}", key=f"starter_{i}", width="stretch"):
            _queue_user_message(text)

# ── Chat history ────────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    _render_message(msg)

# ── Input ──────────────────────────────────────────────────────────────────────
prompt = st.chat_input("اكتب رسالتك هنا... | Type your message here…")
if prompt and prompt.strip():
    _queue_user_message(prompt.strip())

# ── Generate a streamed response for any pending user turn ──────────────────────
msgs = st.session_state.messages
if msgs and msgs[-1]["role"] == "user":
    placeholder = st.empty()
    placeholder.markdown(_typing_html(), unsafe_allow_html=True)  # typing dots
    meta: dict = {}
    acc = ""
    try:
        from src.agents.sales_agent import stream_chat  # lazy (heavy import)
        for token in stream_chat(msgs, meta):            # appends assistant turn
            acc += token
            placeholder.markdown(_row_html("assistant", acc), unsafe_allow_html=True)

        # stream_chat appended the assistant message; stamp it and sync metadata.
        if msgs and msgs[-1]["role"] == "assistant":
            msgs[-1]["time"] = _now()
        st.session_state.intent_stage = meta.get("intent_stage", st.session_state.intent_stage)
        st.session_state.language = meta.get("language", st.session_state.language)
        st.session_state.lead_score = meta.get("lead_score", st.session_state.lead_score)
        if is_qualified(st.session_state.lead_score) and not st.session_state.lead_saved:
            st.session_state.show_lead_form = True
    except Exception as e:
        if not (msgs and msgs[-1]["role"] == "assistant"):
            msgs.append({"role": "assistant",
                         "content": f"عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى.\n\n`{e}`",
                         "time": _now()})
    st.rerun()

# ── Suggested follow-ups (after an assistant reply, when not capturing a lead) ──
if (msgs and msgs[-1]["role"] == "assistant"
        and not st.session_state.show_lead_form and not st.session_state.lead_saved):
    lang = st.session_state.language if st.session_state.language in ("arabic", "english") else "arabic"
    suggestions = FOLLOWUPS.get(st.session_state.intent_stage, FOLLOWUPS["browsing"]).get(lang)
    if suggestions:
        st.markdown("<div class='k-suggest-label'>💡 أسئلة مقترحة — Suggested</div>",
                    unsafe_allow_html=True)
        cols = st.columns(len(suggestions))
        for i, (col, q) in enumerate(zip(cols, suggestions)):
            if col.button(q, key=f"sugg_{len(msgs)}_{i}", width="stretch"):
                _queue_user_message(q)

# ── Lead capture form ─────────────────────────────────────────────────────────
if st.session_state.show_lead_form and not st.session_state.lead_saved:
    with st.container(border=True):
        st.markdown(
            "<h3 style='margin-top:0;'>🌟 يبدو أنك مهتم بالانضمام!</h3>"
            "<p style='color:var(--muted);'>أكمل بياناتك وسيتواصل معك فريق كيفا في أقرب وقت.</p>",
            unsafe_allow_html=True,
        )

        with st.form("lead_form", clear_on_submit=False):
            # Who
            ca, cb = st.columns(2)
            name = ca.text_input("الاسم الكامل / Full Name *")
            phone = cb.text_input(
                "رقم الهاتف / واتساب — Phone / WhatsApp *",
                placeholder="+20 10 1234 5678",
                help="مع رمز الدولة، مثل ‎+20 — Include country code, e.g. +20",
            )
            email = st.text_input("البريد الإلكتروني / Email *")

            cc, cd = st.columns(2)
            location = cc.text_input("المدينة / الدولة — City / Country")
            best_time = cd.text_input("أفضل وقت للتواصل / Best time to contact")
            channel = st.selectbox(
                "قناة التواصل المفضلة / Preferred contact channel",
                ["", "whatsapp", "phone", "email"],
                format_func=lambda x: "— اختر / Select —" if x == "" else x.capitalize(),
            )

            # What they want
            interest = st.text_input(
                "ما الذي تريد تعلمه؟ / What do you want to learn?",
                help="كورسات أو مسارات أو دبلومات محددة — Specific courses, tracks, or diplomas",
            )
            goal = st.text_input("هدفك من التعلّم / Your goal or motivation")
            level = st.selectbox(
                "مستواك الحالي / Your current level",
                ["", "beginner", "intermediate", "advanced"],
                format_func=lambda x: "— اختر / Select —" if x == "" else x.capitalize(),
            )

            submitted = st.form_submit_button("📩 أرسل بياناتك | Submit",
                                              width="stretch", type="primary")

        if submitted:
            errors = _validate_lead(name, phone, email)
            if errors:
                # clear_on_submit=False keeps what the user typed; we only point
                # out what needs fixing instead of wiping the whole form.
                st.error("⚠️ يرجى مراجعة الحقول التالية — Please review:\n\n"
                         + "\n".join(f"- {e}" for e in errors))
            else:
                # Build the "what happened" half of the ticket from the conversation.
                user_turns = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
                convo_text = " ".join(user_turns)
                summary = " | ".join(t[:80] for t in user_turns[-6:])

                # Recommend the rep's next step from the detected intent stage.
                NEXT_ACTION = {
                    "ready": "العميل جاهز للتسجيل — أرسل رابط الدفع/التسجيل وتابع فوراً.",
                    "price_sensitive": "أرسل تفاصيل الأسعار وأي خصومات/أقساط متاحة.",
                    "objecting": "تابع لمعالجة التردد وقدّم ضمانات/قصص نجاح.",
                    "comparing": "أرسل مقارنة واضحة بين الخيارات التي يهتم بها.",
                    "exploring": "أرسل نظرة عامة على المسار المناسب ومحتواه.",
                    "browsing": "تواصل لتأهيل العميل وفهم احتياجه بدقة.",
                }
                stage = st.session_state.intent_stage
                try:
                    with st.spinner("جارٍ حفظ بياناتك… | Saving…"):
                        lead_id = create_lead(
                            name=name.strip(), phone=phone.strip(), email=email.strip(),
                            language=st.session_state.language,
                            interest_area=interest or stage,
                            recommended_product="",
                            lead_score=st.session_state.lead_score,
                            conversation_summary=summary,
                            # Who
                            location=location,
                            dialect=detect_dialect(convo_text) if st.session_state.language == "arabic" else "",
                            contact_channel=channel,
                            best_contact_time=best_time,
                            # What they want
                            products_of_interest=interest,
                            goal=goal,
                            current_level=level or detect_current_level(convo_text),
                            # How likely
                            temperature=lead_temperature(st.session_state.lead_score),
                            budget_sensitivity=detect_budget_sensitivity(convo_text),
                            objections="تردد محتمل" if stage == "objecting" else "",
                            # What happened
                            next_action=NEXT_ACTION.get(stage, NEXT_ACTION["browsing"]),
                        )
                    st.session_state.lead_saved = True
                    st.session_state.show_lead_form = False
                    st.toast("✅ تم إرسال بياناتك — Submitted!", icon="🎉")
                    st.success(f"✅ تم إرسال بياناتك بنجاح! سيتواصل معك الفريق قريباً. (ID: {lead_id})")
                except Exception as e:
                    st.error(f"تعذّر حفظ البيانات، حاول مرة أخرى — Couldn't save, please retry.\n\n`{e}`")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.markdown("**💡 أسئلة سريعة:**")
    quick_questions = [
        "ما هي دبلومة الـ AI؟",
        "كم سعر مسار Data Science؟",
        "ما الفرق بين الكورسات والمسارات؟",
        "What cybersecurity tracks do you have?",
        "هل يناسبني المسار إذا كنت مبتدئاً؟",
    ]
    for q in quick_questions:
        if st.button(q, width="stretch", key=f"quick_{q}"):
            _queue_user_message(q)

    st.divider()
    if st.button("🗑️ مسح المحادثة | Clear Chat", width="stretch"):
        st.session_state.messages = []
        st.session_state.lead_score = 0.0
        st.session_state.intent_stage = "browsing"
        st.session_state.lead_saved = False
        st.session_state.show_lead_form = False
        st.rerun()
