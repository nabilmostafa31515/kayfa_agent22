"""
Page 1 — Chat Assistant
Bilingual (Arabic / English) chat interface with lead capture form.
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.lead_qualifier import (
    is_qualified, lead_temperature, detect_dialect,
    detect_current_level, detect_budget_sensitivity,
)
from src.database.crm_repository import create_lead
from src.ui.branding import page_header, LOGO_PATH

# NOTE: `chat` (the LangGraph agent) is imported lazily inside the response
# handler below — its dependency stack (langgraph + langchain + sentence-
# transformers) takes ~30s+ to import. Importing it at module top-level would
# block the whole page from rendering on first open. Lazy import lets the chat
# UI appear instantly; the one-time cost is paid under the "Thinking…" spinner.

USER_AVATAR = "🧑"
try:
    from PIL import Image
    ASSISTANT_AVATAR = Image.open(LOGO_PATH)
except Exception:
    ASSISTANT_AVATAR = "🎓"

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

# ── Chat history ──────────────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown(f"""
    <div style='text-align:center; padding:18px 10px 6px;'>
      <div style='font-size:2.4rem;'>👋</div>
      <h3 style='margin:6px 0 4px;'>أهلاً بك في مساعد كيفا</h3>
      <p style='color:var(--muted); margin:0;'>
        اسألني عن أي كورس أو مسار تعليمي — Ask me anything about Kayfa's courses & tracks.
      </p>
      <p style='color:var(--muted); font-size:.85rem; margin-top:10px;'>جرّب أحد هذه الأسئلة:</p>
    </div>
    """, unsafe_allow_html=True)

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
            st.session_state.messages.append({"role": "user", "content": text})
            st.rerun()

for msg in st.session_state.messages:
    avatar = ASSISTANT_AVATAR if msg["role"] == "assistant" else USER_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
        # Render as real markdown so headings/bold/lists from the model display.
        # Wrap in `dir="auto"` so each message picks its own direction from its
        # content (Arabic → RTL, English → LTR). This is what actually flips the
        # CSS `direction` property — without it, Arabic text right-aligns but
        # list bullets/numbers strand on the wrong (left) side. The blank lines
        # let Streamlit's markdown render inside the wrapper. RTL list spacing is
        # handled by the `.k-msg` rules in branding.py.
        st.markdown(f"<div dir='auto' class='k-msg'>\n\n{msg['content']}\n\n</div>",
                    unsafe_allow_html=True)

# ── Input ──────────────────────────────────────────────────────────────────────
prompt = st.chat_input("اكتب رسالتك هنا... | Type your message here…")
if prompt and prompt.strip():
    st.session_state.messages.append({"role": "user", "content": prompt.strip()})
    st.rerun()

# ── Generate a response for any pending user turn (chat input or quick question) ─
msgs = st.session_state.messages
if msgs and msgs[-1]["role"] == "user":
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        with st.spinner("كيفا AI يفكر… | Thinking…"):
            try:
                from src.agents.sales_agent import chat  # lazy (heavy import)
                result = chat(msgs)  # appends the assistant reply to msgs
                st.session_state.intent_stage = result["intent_stage"]
                st.session_state.language = result["language"]
                st.session_state.lead_score = result["lead_score"]
                if is_qualified(result["lead_score"]) and not st.session_state.lead_saved:
                    st.session_state.show_lead_form = True
            except Exception as e:
                msgs.append({"role": "assistant",
                             "content": f"عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى.\n\n`{e}`"})
    st.rerun()

# ── Lead capture form ─────────────────────────────────────────────────────────
if st.session_state.show_lead_form and not st.session_state.lead_saved:
    with st.container(border=True):
        st.markdown(f"""
        <h3 style='margin-top:0;'>🌟 يبدو أنك مهتم بالانضمام!</h3>
        <p style='color:var(--muted);'>أكمل بياناتك وسيتواصل معك فريق كيفا في أقرب وقت.</p>
        """, unsafe_allow_html=True)

        with st.form("lead_form", clear_on_submit=True):
            # Who
            ca, cb = st.columns(2)
            name = ca.text_input("الاسم الكامل / Full Name *")
            phone = cb.text_input("رقم الهاتف / واتساب — Phone / WhatsApp *")
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
            if name and phone and email:
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
                    lead_id = create_lead(
                        name=name, phone=phone, email=email,
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
                    st.success(f"✅ تم إرسال بياناتك بنجاح! سيتواصل معك الفريق قريباً. (ID: {lead_id})")
                    st.session_state.lead_saved = True
                    st.session_state.show_lead_form = False
                except Exception as e:
                    st.error(f"خطأ في الحفظ: {e}")
            else:
                st.warning("يرجى ملء جميع الحقول المطلوبة *")

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
            st.session_state.messages.append({"role": "user", "content": q})
            st.rerun()

    st.divider()
    if st.button("🗑️ مسح المحادثة | Clear Chat", width="stretch"):
        st.session_state.messages = []
        st.session_state.lead_score = 0.0
        st.session_state.intent_stage = "browsing"
        st.session_state.lead_saved = False
        st.session_state.show_lead_form = False
        st.rerun()