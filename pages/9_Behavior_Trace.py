"""
Page 9 — Behavior Trace (manager-only)
Full, replayable execution trace for every AI response. Pick a conversation and
replay each message step-by-step:

    user prompt → reasoning → retrieved context → sources → tool calls
    (args/results) → final response → latency → tokens → cost

Putting the retrieved context beside the final answer makes hallucinations easy
to spot: claims in the answer that aren't supported by the retrieved sources.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth.manager_auth import require_manager, logout_button
from src.database.mongodb import ping
from src.ui.branding import page_header, inject_global_css
from src.monitoring import behavior_repository as behavior
from src.dashboard.components import (
    fmt_usd, fmt_int, fmt_ms, resolve_user_label, short_id,
)

inject_global_css()
require_manager()
logout_button()

page_header(
    "تتبّع السلوك",
    subtitle="Behavior Trace — replay any conversation step-by-step",
    rtl=True,
)

if not ping():
    st.error("❌ MongoDB connection failed — check your .env file")
    st.stop()

conversations = behavior.list_conversations(100)
if not conversations:
    st.info("لا توجد تتبّعات بعد — ابدأ محادثات في المساعد.\n\n"
            "No traces yet — chat in the Assistant to record execution traces.")
    st.stop()


def _conv_label(c: dict) -> str:
    when = c["last_time"].strftime("%Y-%m-%d %H:%M") if c.get("last_time") else "—"
    prompt = (c.get("first_prompt") or "").strip().replace("\n", " ")
    if len(prompt) > 45:
        prompt = prompt[:45] + "…"
    return (f"{when} · {resolve_user_label(c['user_id'])} · "
            f"{c['messages']} msg · {fmt_usd(c['total_cost'], 5)} · {prompt}")


# ── Conversation picker ──────────────────────────────────────────────────────────
labels = [_conv_label(c) for c in conversations]
idx = st.selectbox("اختر محادثة · Select a conversation", range(len(conversations)),
                   format_func=lambda i: labels[i])
conv = conversations[idx]

m = st.columns(5)
m[0].metric("Messages", fmt_int(conv["messages"]))
m[1].metric("Tool calls", fmt_int(conv["tool_calls"]))
m[2].metric("Total cost", fmt_usd(conv["total_cost"], 5))
m[3].metric("Tokens", fmt_int(conv["total_tokens"]))
m[4].metric("Avg latency", fmt_ms(conv["avg_latency"]))

st.caption(f"Conversation ID: `{conv['conversation_id']}` · "
           f"User: {resolve_user_label(conv['user_id'])}")

st.divider()

# ── Replay each message ──────────────────────────────────────────────────────────
traces = behavior.get_conversation_trace(conv["conversation_id"])

for n, t in enumerate(traces, start=1):
    prompt_preview = (t.get("user_prompt") or "").strip().replace("\n", " ")
    if len(prompt_preview) > 70:
        prompt_preview = prompt_preview[:70] + "…"
    header = (f"▶︎ Message {n} — {prompt_preview}  ·  "
              f"{fmt_usd(t.get('total_cost', 0), 5)} · {fmt_ms(t.get('total_latency_ms', 0))}")
    with st.expander(header, expanded=(n == 1)):

        # 1) User prompt
        st.markdown("**1 · 🧑 User Prompt**")
        st.markdown(f"<div class='k-msg' dir='auto'>{t.get('user_prompt','')}</div>",
                    unsafe_allow_html=True)

        # 2) Internal reasoning (synthesised summary of observed steps)
        st.markdown("**2 · 🧠 Reasoning Step** *(synthesised summary — the model's "
                    "hidden reasoning is not exposed by the provider)*")
        st.info(t.get("reasoning_summary", "—"))

        # 3 + 4) Retrieved context & knowledge sources
        st.markdown("**3 · 📚 Retrieved Context & Sources**")
        sources = t.get("knowledge_sources", []) or []
        if sources:
            st.caption("Knowledge sources used: " + " · ".join(f"`{s}`" for s in sources))
        chunks = t.get("retrieved_chunks", []) or []
        if chunks:
            for i, ch in enumerate(chunks, start=1):
                score = ch.get("score")
                score_txt = f" · score {score:.3f}" if isinstance(score, (int, float)) else ""
                st.markdown(f"<small><b>Chunk {i}</b> — `{ch.get('source','?')}`{score_txt}</small>",
                            unsafe_allow_html=True)
                st.markdown(f"<div class='k-msg' dir='auto' style='font-size:.85rem;opacity:.9'>"
                            f"{ch.get('preview','')}</div>", unsafe_allow_html=True)
        else:
            st.caption("No KB context retrieved for this turn.")

        # 5 + 6 + 7) Tool calls, arguments, results
        st.markdown("**4 · 🛠️ Tool Calls**")
        tool_calls = t.get("tool_calls", []) or []
        if tool_calls:
            for tc in tool_calls:
                st.markdown(f"`{tc.get('name','?')}` · {fmt_ms(tc.get('latency_ms',0))}"
                            + (f" · ⚠️ error" if tc.get("error") else ""))
                tcc1, tcc2 = st.columns(2)
                with tcc1:
                    st.caption("Arguments")
                    st.json(tc.get("arguments", {}))
                with tcc2:
                    st.caption("Result")
                    if tc.get("error"):
                        st.error(tc.get("error"))
                    st.code((tc.get("result") or "")[:1500] or "—")
        else:
            st.caption("No tool calls — answered from injected context.")

        # 8) Final response (beside sources for hallucination checks)
        st.markdown("**5 · 💬 Final Response**")
        st.markdown(f"<div class='k-msg' dir='auto'>{t.get('final_response','')}</div>",
                    unsafe_allow_html=True)
        if t.get("final_response") and not sources and not tool_calls:
            st.warning("⚠️ This answer used **no retrieved context and no tools** — verify "
                       "it isn't hallucinated.")

        # 9 + 10 + 11) Latency, token usage, cost
        st.markdown("**6 · 📊 Latency · Tokens · Cost**")
        s = st.columns(6)
        s[0].metric("Total latency", fmt_ms(t.get("total_latency_ms", 0)))
        s[1].metric("Retrieval", fmt_ms(t.get("retrieval_latency_ms", 0)))
        s[2].metric("Input tok", fmt_int(t.get("input_tokens", 0)))
        s[3].metric("Output tok", fmt_int(t.get("output_tokens", 0)))
        s[4].metric("Embed tok", fmt_int(t.get("embedding_tokens", 0)))
        s[5].metric("Cost", fmt_usd(t.get("total_cost", 0), 5))
        st.caption(f"LLM round-trips: {len(t.get('llm_calls', []) or [])} · "
                   f"Chat {fmt_usd(t.get('chat_cost', 0), 6)} · "
                   f"Embedding {fmt_usd(t.get('embedding_cost', 0), 6)} · "
                   f"Model `{t.get('model','')}` ({t.get('provider','')})")
