"""
Page 1 — Chat Assistant
Bilingual (Arabic / English) chat with modern message bubbles, streamed
responses, timestamps, suggested follow-ups, and lead capture.
"""

import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.lead_qualifier import (
    is_qualified, lead_temperature, detect_dialect,
    detect_current_level, detect_budget_sensitivity,
)
from src.database.crm_repository import create_lead
from src.database.messages_repository import save_message
from src.database.traces_repository import record_trace
from src.utils.geo import is_recognized_country
from src.ui.branding import page_header, logo_data_uri, inject_global_css
from src.auth.user_auth import require_user, current_user_id, logout_button

# Re-assert the global CSS from within the page itself. app.py injects it before
# nav.run(), but on a first/direct page load that pre-nav <style> doesn't stick
# until a rerun — injecting here guarantees the styling is present on first paint.
inject_global_css()

# Gate the chat behind end-user sign-in. require_user() renders the login/sign-up
# screen and halts the page when no user session is open; otherwise it returns the
# signed-in user, whose id is stamped on every message and captured lead.
USER = require_user()

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
    # User text is plain — keep the line breaks they typed (markdown would
    # otherwise collapse single newlines, putting everything on one line).
    # Assistant text is already markdown, so leave its structure intact.
    if role == "user":
        content = content.replace("\n", "<br>")
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
# E.164-style: a leading "+", a country-code digit (1–9), then 9–14 more digits.
# Requiring the "+" guarantees the country code is present; the 10–15 total-digit
# bound rejects too-short / mistyped numbers (e.g. +201123457402 → 12 digits ✓).
_PHONE_RE = re.compile(r"^\+[1-9]\d{9,14}$")


def _validate_lead(name: str, phone: str, email: str, location: str = "") -> list[str]:
    """Return a list of human-readable errors; empty list means valid."""
    errors = []
    if not name.strip():
        errors.append("الاسم مطلوب — Name is required")
    if not phone.strip():
        errors.append("رقم الهاتف مطلوب — Phone is required")
    elif not _PHONE_RE.match(re.sub(r"[\s\-()]", "", phone.strip())):
        # Must be an international number that includes the country code and has
        # a valid length (10–15 digits total).
        errors.append("أدخل رقم هاتف دولي صحيح يشمل رمز الدولة (10–15 رقمًا)، مثل ‎+201123457402 — "
                      "Enter a valid international phone with country code, 10–15 digits (e.g. +201123457402)")
    if not email.strip():
        errors.append("البريد الإلكتروني مطلوب — Email is required")
    elif not _EMAIL_RE.match(email.strip()):
        errors.append("بريد إلكتروني غير صالح — Enter a valid email address")
    # Location is optional, but if provided it must contain a real country name
    # so gibberish like "Maghr" never reaches the database.
    if location.strip() and not is_recognized_country(location):
        errors.append("اسم الدولة غير معروف — اكتب اسم دولة صحيح، مثل: مصر / Egypt — "
                      "Unrecognized country — enter a valid country (e.g. Egypt, السعودية)")
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
    # Persist the user turn + behavior trace, stamped with the signed-in user's id.
    uid = current_user_id()
    convo = st.session_state.get("conversation_id", "")
    save_message(uid, "user", text, convo)
    record_trace(uid, "message_sent", convo, props={"len": len(text)})
    st.rerun()


# ── Session state ──────────────────────────────────────────────────────────────
defaults = {
    "messages": [], "lead_score": 0.0, "intent_stage": "browsing",
    "language": "arabic", "lead_saved": False, "show_lead_form": False,
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# One conversation id per chat session — groups this user's messages together.
if not st.session_state.get("conversation_id"):
    st.session_state.conversation_id = uuid.uuid4().hex

# ── Header ─────────────────────────────────────────────────────────────────────
page_header(
    "المساعد الذكي",
    subtitle="اسألني عن الكورسات والمسارات والدبلومات — بالعربية أو الإنجليزية",
    badge="Kayfa AI Sales Agent",
    rtl=True,
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

# Dedicated registration button — lets the client open the capture form at any
# time, not only once the lead score crosses the qualification threshold.
st.write("")
rc1, rc2, rc3 = st.columns([1, 2, 1])
with rc2:
    if not st.session_state.lead_saved:
        if st.button("📝 سجّل بياناتك الآن  ·  Register now",
                     width="stretch", type="primary", key="open_reg_main"):
            st.session_state.show_lead_form = True
            record_trace(current_user_id(), "lead_form_opened",
                         st.session_state.get("conversation_id", ""),
                         props={"source": "main_button"})
            st.rerun()
    else:
        st.success("✅ تم تسجيل بياناتك — Your details are registered.")

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

# ── Generate a streamed response for any pending user turn ──────────────────────
msgs = st.session_state.messages
if msgs and msgs[-1]["role"] == "user":
    placeholder = st.empty()
    placeholder.markdown(_typing_html(), unsafe_allow_html=True)  # typing dots
    meta: dict = {}
    acc = ""
    try:
        from src.agents.sales_agent import stream_chat  # lazy (heavy import)
        uid = current_user_id()
        convo = st.session_state.get("conversation_id", "")
        # Pass the signed-in user's id + conversation so the agent stamps any
        # captured lead and records this turn's token cost.
        for token in stream_chat(msgs, meta, user_id=uid, conversation_id=convo):
            acc += token
            placeholder.markdown(_row_html("assistant", acc), unsafe_allow_html=True)

        # stream_chat appended the assistant message; stamp it, persist it
        # (with the user's id), trace it, and sync metadata.
        if msgs and msgs[-1]["role"] == "assistant":
            msgs[-1]["time"] = _now()
            save_message(uid, "assistant", msgs[-1]["content"], convo)
            record_trace(uid, "assistant_replied", convo, props={
                "intent_stage": meta.get("intent_stage"),
                "lead_score": meta.get("lead_score"),
                "input_tokens": meta.get("input_tokens"),
                "output_tokens": meta.get("output_tokens"),
            })
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
    # key="lead-form-rtl" → Streamlit adds a `.st-key-lead-form-rtl` class on this
    # container, which branding.py uses to flip the whole form to RTL (Arabic-first).
    with st.container(border=True, key="lead-form-rtl"):
        st.markdown(
            "<div dir='rtl'><h3 style='margin-top:0;'>🌟 يبدو أنك مهتم بالانضمام!</h3>"
            "<p style='color:var(--muted);'>أكمل بياناتك وسيتواصل معك فريق كيفا في أقرب وقت.</p></div>",
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
            location = cc.text_input(
                "المدينة / الدولة — City / Country",
                placeholder="مثال: القاهرة، مصر · e.g. Cairo, Egypt",
                help="اذكر اسم الدولة · Include the country name",
            )
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
            errors = _validate_lead(name, phone, email, location)
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
                            user_id=current_user_id(),
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
                    record_trace(current_user_id(), "lead_captured",
                                 st.session_state.get("conversation_id", ""),
                                 props={"lead_id": lead_id,
                                        "lead_score": st.session_state.lead_score,
                                        "intent_stage": stage})
                    st.toast("✅ تم إرسال بياناتك — Submitted!", icon="🎉")
                    st.success(f"✅ تم إرسال بياناتك بنجاح! سيتواصل معك الفريق قريباً. (ID: {lead_id})")
                except Exception as e:
                    st.error(f"تعذّر حفظ البيانات، حاول مرة أخرى — Couldn't save, please retry.\n\n`{e}`")

# ── Composer (multi-line input, pinned at the bottom) ───────────────────────────
# A text area instead of st.chat_input so the user can add line breaks (Enter)
# and send multi-line messages. The form submits on the ➤ button or Ctrl+Enter;
# clear_on_submit empties the box after sending.
with st.form("composer", clear_on_submit=True):
    ic, bc = st.columns([6, 1])
    user_text = ic.text_area(
        "message",
        height=80,
        label_visibility="collapsed",
        placeholder="اكتب رسالتك هنا… (Enter لسطر جديد · للإرسال: زر ➤ أو Ctrl+Enter)\n"
                    "Type here — Enter for a new line · Send with ➤ or Ctrl+Enter",
    )
    sent = bc.form_submit_button("➤", width="stretch", type="primary")
if sent and user_text.strip():
    _queue_user_message(user_text.strip())

# ── Sidebar ────────────────────────────────────────────────────────────────────
# Signed-in account + sign-out at the top of the sidebar.
logout_button()

with st.sidebar:
    st.divider()
    if not st.session_state.lead_saved:
        if st.button("📝 سجّل بياناتك | Register", width="stretch",
                     type="primary", key="open_reg_side"):
            st.session_state.show_lead_form = True
            record_trace(current_user_id(), "lead_form_opened",
                         st.session_state.get("conversation_id", ""),
                         props={"source": "sidebar_button"})
            st.rerun()

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
        st.session_state.conversation_id = uuid.uuid4().hex  # start a new conversation
        st.rerun()
