"""
Kayfa AI Sales Agent — LangGraph workflow.

Workflow:
    User Message
        ↓
    Intent Detection (lead_qualifier)
        ↓
    Knowledge Retrieval (FAISS RAG)
        ↓
    Agent Node (OpenAI + tools)
        ↓
    Lead Qualification Check
        ↓
    CRM Save (if qualified)
        ↓
    Final Response

Part 2 (monitoring): ``stream_chat`` is instrumented with a ``TurnRecorder`` that
automatically writes a per-LLM-call ``usage_logs`` row and a per-message
``behavior_logs`` trace (prompt → reasoning → retrieved context → sources → tool
calls/args/results → final response → latency → tokens → cost). This is purely
additive — the chat behaviour and outputs are identical to Part 1.
"""

import logging
import os
from typing import TypedDict, Annotated
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    SystemMessage, HumanMessage, AIMessage, ToolMessage,
)
from langgraph.graph import StateGraph, END

from src.rag.vectorstore import similarity_search
from src.tools.search_courses import search_courses, search_roadmaps, retrieve_policy
from src.tools.save_lead import save_lead, get_lead, update_lead
from src.agents.lead_qualifier import (
    compute_lead_score, is_qualified, detect_intent_stage, extract_language
)
from src.prompts.system_prompt import SYSTEM_PROMPT
from src.runtime_context import set_current_user_id
from src.database.cost_repository import record_cost
from src.config.pricing import infer_chat_provider
from src.config.monitoring import get_config
from src.monitoring.recorder import TurnRecorder

load_dotenv()
logger = logging.getLogger(__name__)

# ── Tools ──────────────────────────────────────────────────────────────────────

TOOLS = [search_courses, search_roadmaps, retrieve_policy, save_lead, get_lead, update_lead]
TOOL_MAP = {t.name: t for t in TOOLS}
# Cap on tool round-trips. The KB context is injected up front, so the model
# usually answers in one turn; 3 bounds worst-case latency without hurting
# accuracy (each extra iteration is a full LLM round-trip).
MAX_TOOL_ITERATIONS = 3

# ── LLM ───────────────────────────────────────────────────────────────────────

class LLMConfigError(RuntimeError):
    """The chat LLM is not configured. Raised so a misconfigured deploy fails
    loudly with an actionable message instead of silently falling back to a
    rate-limited free model (which surfaces later as a confusing upstream 429).
    """


def _get_secret(key: str, default: str | None = None) -> str | None:
    """Read config from st.secrets FIRST (Streamlit Cloud), then the process
    environment / .env. Mirrors src.auth.user_auth._get_secret.

    Why secrets-first: on Streamlit Cloud the Secrets panel is the source of
    truth, but a stale or platform-provided OPENAI_API_KEY can linger in
    os.environ and shadow it. Reading os.getenv alone meant the LLM picked up
    that stale (OpenRouter) key while the user's Groq value in Secrets was
    ignored — so the deploy kept routing to OpenRouter no matter what.
    """
    try:
        import streamlit as st  # available in the Streamlit runtime
        if key in st.secrets:
            val = str(st.secrets[key]).strip()
            if val:
                return val
    except Exception:
        pass  # no Streamlit context / no secrets.toml (e.g. local CLI) — use env
    return os.getenv(key, default)


def resolve_llm_config() -> tuple[str, str | None, str, str]:
    """Resolve (api_key, base_url, model, provider) for the chat LLM.

    Supports OpenAI and OpenAI-compatible gateways (Groq, OpenRouter) via
    OPENAI_BASE_URL / OPENAI_MODEL. A provider key MUST hit its own endpoint, not
    OpenAI's default, or it 401s; if the base URL wasn't configured we auto-route
    by key prefix and pick a sane default model. ``provider`` is inferred for
    usage-log attribution and mirrors the routing below.

    Raises ``LLMConfigError`` when the deploy is unconfigured — no API key, or an
    OpenRouter key with no explicit model (we refuse to default to the free,
    rate-limited model and mask the misconfiguration). On Streamlit Cloud, set
    these in Settings → Secrets and reboot the app.
    """
    api_key = _get_secret("OPENAI_API_KEY")
    base_url = _get_secret("OPENAI_BASE_URL") or None
    model_env = _get_secret("OPENAI_MODEL")
    model = model_env or "gpt-4o"

    if not api_key:
        raise LLMConfigError(
            "No LLM API key configured: OPENAI_API_KEY is empty. Set it (recommended: "
            "a Groq key — OPENAI_API_KEY=gsk_..., OPENAI_BASE_URL=https://api.groq.com/openai/v1, "
            "OPENAI_MODEL=openai/gpt-oss-120b). For a Streamlit Cloud deploy, add these in "
            "Settings → Secrets and reboot the app."
        )

    if base_url is None and api_key.startswith("gsk_"):
        # Groq — fast, OpenAI-compatible. https://console.groq.com/keys
        base_url = "https://api.groq.com/openai/v1"
        if not model_env:
            # gpt-oss-120b streams tool calls reliably on Groq (the Llama-3.3
            # models malform streamed tool calls). Fast + strong at grounding.
            model = "openai/gpt-oss-120b"
    elif base_url is None and api_key.startswith("sk-or-"):
        base_url = "https://openrouter.ai/api/v1"
        if not model_env:
            # Refuse to silently default to the FREE OpenRouter model: it is
            # rate-limited upstream and a deploy that lands here looks "working"
            # until it 429s under any real traffic. Make the operator choose.
            raise LLMConfigError(
                "OpenRouter key detected but OPENAI_MODEL is not set. Refusing to default "
                "to the free, rate-limited 'openai/gpt-oss-120b:free' model. Either set "
                "OPENAI_MODEL explicitly (and add OpenRouter credits), or switch to Groq "
                "(OPENAI_API_KEY=gsk_..., OPENAI_BASE_URL=https://api.groq.com/openai/v1, "
                "OPENAI_MODEL=openai/gpt-oss-120b). On Streamlit Cloud, set this in "
                "Settings → Secrets and reboot the app."
            )

    provider = infer_chat_provider(model, base_url, api_key)
    return api_key, base_url, model, provider


def get_llm():
    api_key, base_url, model, _provider = resolve_llm_config()

    return ChatOpenAI(
        model=model,
        temperature=0.4,
        streaming=True,
        # Ask the gateway to include token usage in the streamed response so we
        # can record per-turn cost (works on OpenAI + Groq's compatible API).
        stream_usage=True,
        openai_api_key=api_key,
        base_url=base_url,
        # Bound completion length. Without this, ChatOpenAI requests the model's
        # full max (16k+), which some gateways/accounts (e.g. free OpenRouter
        # credit tiers) reject with HTTP 402. Default kept low so it fits a free
        # OpenRouter balance; raise via OPENAI_MAX_TOKENS once you add credits.
        max_tokens=int(_get_secret("OPENAI_MAX_TOKENS", "512")),
    ).bind_tools(TOOLS)


# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: list[dict]          # {"role": str, "content": str}
    context: str                  # retrieved KB context
    intent_stage: str
    language: str
    lead_score: float
    lead_saved: bool
    final_response: str


# ── Nodes ─────────────────────────────────────────────────────────────────────

def intent_detection_node(state: AgentState) -> AgentState:
    """Compute intent stage, language, and lead score."""
    messages = state["messages"]
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    state["intent_stage"] = detect_intent_stage(messages)
    state["language"] = extract_language(last_user)
    state["lead_score"] = compute_lead_score(messages)
    logger.info(f"Intent: {state['intent_stage']} | Lang: {state['language']} | Score: {state['lead_score']}")
    return state


def knowledge_retrieval_node(state: AgentState) -> AgentState:
    """Retrieve relevant KB chunks for the latest user message."""
    messages = state["messages"]
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    try:
        docs = similarity_search(last_user, k=4)
        state["context"] = "\n\n---\n\n".join(d.page_content for d in docs)[:2200]
    except Exception as e:
        logger.error(f"Knowledge retrieval failed: {e}")
        state["context"] = ""
    return state


def agent_node(state: AgentState) -> AgentState:
    """Call the LLM with system prompt, context, and conversation history."""
    llm = get_llm()

    # History is sent as the message list below, not duplicated in the prompt.
    system_content = SYSTEM_PROMPT.format(context=state["context"], chat_history="")

    lc_messages = [SystemMessage(content=system_content)]
    for m in state["messages"][-6:]:
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))

    # Tool-calling loop: the model may request one or more tools before
    # producing its final answer. Execute them and feed results back until the
    # model returns content (or we hit the iteration cap).
    response = llm.invoke(lc_messages)
    for _ in range(MAX_TOOL_ITERATIONS):
        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            break
        lc_messages.append(response)
        for call in tool_calls:
            tool = TOOL_MAP.get(call["name"])
            try:
                output = tool.invoke(call["args"]) if tool else f"Unknown tool: {call['name']}"
            except Exception as e:
                logger.error(f"Tool {call['name']} failed: {e}")
                output = f"Tool error: {e}"
            lc_messages.append(ToolMessage(content=str(output), tool_call_id=call["id"]))
        response = llm.invoke(lc_messages)

    state["final_response"] = response.content
    state["messages"].append({"role": "assistant", "content": response.content})
    return state


def lead_check_node(state: AgentState) -> AgentState:
    """Nothing to do here — routing happens in the edge function."""
    return state


# ── Routing ───────────────────────────────────────────────────────────────────

def should_save_lead(state: AgentState) -> str:
    if is_qualified(state["lead_score"]) and not state.get("lead_saved", False):
        return "prompt_lead_capture"
    return END


# ── Graph ─────────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("intent_detection", intent_detection_node)
    graph.add_node("knowledge_retrieval", knowledge_retrieval_node)
    graph.add_node("agent", agent_node)
    graph.add_node("lead_check", lead_check_node)

    graph.set_entry_point("intent_detection")
    graph.add_edge("intent_detection", "knowledge_retrieval")
    graph.add_edge("knowledge_retrieval", "agent")
    graph.add_edge("agent", "lead_check")
    graph.add_conditional_edges("lead_check", should_save_lead, {
        # Both branches terminate: lead capture is handled by the chat UI form;
        # the graph itself simply ends after the agent has answered.
        "prompt_lead_capture": END,
        END: END,
    })

    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def stream_chat(messages: list[dict], meta: dict, user_id: str = "", conversation_id: str = ""):
    """Generator variant of `chat` for live token streaming in the UI.

    Yields the assistant's reply in text chunks as the model generates them.
    `meta` is a dict the caller passes in; it is populated immediately (before
    the first token) with intent_stage / language / lead_score, and with
    `response` once streaming completes. The assistant turn is appended to
    `messages` at the end (without a timestamp — the UI owns that).

    `user_id` is the signed-in user; it's published to the runtime context so the
    save_lead tool stamps any captured lead with this user, and used (with
    `conversation_id`) to record this turn's token cost.

    Part 2: every step is captured by a ``TurnRecorder``, which persists a usage
    log per LLM call and a full behaviour trace for the message. Recording is
    best-effort and never affects the streamed reply.
    """
    set_current_user_id(user_id)
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    meta["intent_stage"] = detect_intent_stage(messages)
    meta["language"] = extract_language(last_user)
    meta["lead_score"] = compute_lead_score(messages)

    # ── Monitoring: open a recorder for this turn (Part 2) ───────────────────────
    api_key, base_url, model, provider = resolve_llm_config()
    cfg = get_config()
    recorder = TurnRecorder(
        user_id=user_id, conversation_id=conversation_id,
        provider=provider, model=model,
        embedding_provider=cfg.embedding_provider,
        embedding_model=cfg.embedding_model,
    )
    recorder.set_prompt(last_user)

    try:
        # Routed, alias-expanded retrieval (see vectorstore.similarity_search).
        # k=4 + a generous cap gives the model richer grounding now that Groq's
        # gpt-oss-120b has ample input budget (no free-tier token squeeze).
        with recorder.time_retrieval():
            docs = similarity_search(last_user, k=4)
        recorder.record_retrieval(last_user, docs)
        context = "\n\n---\n\n".join(d.page_content for d in docs)[:2200]
    except Exception as e:
        logger.error(f"Knowledge retrieval failed: {e}")
        docs = []
        recorder.record_retrieval(last_user, docs)
        context = ""

    # Don't embed the history in the system prompt — it's already sent as the
    # message list below, and duplicating it roughly doubled the prompt size.
    system_content = SYSTEM_PROMPT.format(context=context, chat_history="")
    lc_messages = [SystemMessage(content=system_content)]
    for m in messages[-6:]:   # last few turns only — bounds prompt growth
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))

    llm = get_llm()
    final_text = ""
    in_tokens = out_tokens = 0      # summed across the tool-loop round-trips
    for _ in range(MAX_TOOL_ITERATIONS):
        tool_calls = None
        with recorder.llm_call() as call:
            gathered = None  # AIMessageChunks accumulate (incl. tool_calls) via +
            for chunk in llm.stream(lc_messages):
                gathered = chunk if gathered is None else gathered + chunk
                if chunk.content:
                    final_text += chunk.content
                    yield chunk.content

            usage = getattr(gathered, "usage_metadata", None)
            if usage:
                ci = usage.get("input_tokens", 0) or 0
                co = usage.get("output_tokens", 0) or 0
                in_tokens += ci
                out_tokens += co
                call.set_usage(ci, co)
            call.set_content(getattr(gathered, "content", "") or "")

            tool_calls = getattr(gathered, "tool_calls", None)
            call.mark_tool_calls(len(tool_calls) if tool_calls else 0)

        if not tool_calls:
            break

        lc_messages.append(gathered)
        for tc in tool_calls:
            tool = TOOL_MAP.get(tc["name"])
            with recorder.tool_call(tc["name"], tc.get("args", {})) as tctx:
                try:
                    output = tool.invoke(tc["args"]) if tool else f"Unknown tool: {tc['name']}"
                except Exception as e:
                    logger.error(f"Tool {tc['name']} failed: {e}")
                    output = f"Tool error: {e}"
                    tctx.set_error(str(e))
                tctx.set_result(output)
            lc_messages.append(ToolMessage(content=str(output), tool_call_id=tc["id"]))

    # Record this turn's token cost (best-effort), attributed to the user.
    model_name = getattr(llm, "model_name", None) or os.getenv("OPENAI_MODEL", "")
    meta["input_tokens"] = in_tokens
    meta["output_tokens"] = out_tokens
    if in_tokens or out_tokens:
        record_cost(user_id, conversation_id, model_name, in_tokens, out_tokens)

    # Persist the full monitoring trace + per-call usage logs (Part 2).
    recorder.set_final_response(final_text)
    recorder.finalize()
    meta["message_id"] = recorder.message_id

    meta["response"] = final_text
    messages.append({"role": "assistant", "content": final_text})


def chat(messages: list[dict]) -> dict:
    """
    Run one turn of the sales agent.

    Args:
        messages: full conversation history as list of {"role", "content"}

    Returns:
        dict with keys: response, intent_stage, language, lead_score, lead_saved
    """
    graph = get_graph()
    # Pass a copy so graph-internal mutations never depend on / corrupt the
    # caller's list; we append the assistant reply explicitly below.
    initial_state: AgentState = {
        "messages": list(messages),
        "context": "",
        "intent_stage": "browsing",
        "language": "arabic",
        "lead_score": 0.0,
        "lead_saved": False,
        "final_response": "",
    }
    result = graph.invoke(initial_state)
    messages.append({"role": "assistant", "content": result["final_response"]})
    return {
        "response": result["final_response"],
        "intent_stage": result["intent_stage"],
        "language": result["language"],
        "lead_score": result["lead_score"],
        "lead_saved": result["lead_saved"],
    }
