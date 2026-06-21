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

load_dotenv()
logger = logging.getLogger(__name__)

# ── Tools ──────────────────────────────────────────────────────────────────────

TOOLS = [search_courses, search_roadmaps, retrieve_policy, save_lead, get_lead, update_lead]
TOOL_MAP = {t.name: t for t in TOOLS}
MAX_TOOL_ITERATIONS = 5

# ── LLM ───────────────────────────────────────────────────────────────────────

def get_llm():
    # Supports OpenAI and OpenAI-compatible gateways (e.g. OpenRouter) via
    # OPENAI_BASE_URL / OPENAI_MODEL. Falls back to OpenAI's gpt-4o.
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    model = os.getenv("OPENAI_MODEL", "gpt-4o")

    # An OpenRouter key (sk-or-…) MUST hit OpenRouter, not OpenAI's default
    # endpoint, or it 401s ("Incorrect API key"). If the base URL wasn't
    # configured on the deploy, auto-route OpenRouter keys and pick a sane
    # OpenRouter-formatted default model so a bare "gpt-4o" doesn't 404.
    if base_url is None and api_key and api_key.startswith("sk-or-"):
        base_url = "https://openrouter.ai/api/v1"
        if not os.getenv("OPENAI_MODEL"):
            # Default to a FREE OpenRouter model so an unconfigured deploy
            # doesn't silently spend credits on a paid model (e.g. gpt-4o).
            model = "openai/gpt-oss-120b:free"

    return ChatOpenAI(
        model=model,
        temperature=0.4,
        streaming=True,
        openai_api_key=api_key,
        base_url=base_url,
        # Bound completion length. Without this, ChatOpenAI requests the model's
        # full max (16k+), which some gateways/accounts (e.g. free OpenRouter
        # credit tiers) reject with HTTP 402. Default kept low so it fits a free
        # OpenRouter balance; raise via OPENAI_MAX_TOKENS once you add credits.
        max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "512")),
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
        docs = similarity_search(last_user, k=3)
        state["context"] = "\n\n---\n\n".join(d.page_content for d in docs)[:1200]
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
    graph.add_conditional_edges("lead_check", should_save_lead)

    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def stream_chat(messages: list[dict], meta: dict):
    """Generator variant of `chat` for live token streaming in the UI.

    Yields the assistant's reply in text chunks as the model generates them.
    `meta` is a dict the caller passes in; it is populated immediately (before
    the first token) with intent_stage / language / lead_score, and with
    `response` once streaming completes. The assistant turn is appended to
    `messages` at the end (without a timestamp — the UI owns that).

    Intent scoring and KB retrieval run up front (rule-based / fast), then the
    tool-calling loop streams each LLM turn; tool-call turns emit little or no
    visible text, and the final answer streams naturally.
    """
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    meta["intent_stage"] = detect_intent_stage(messages)
    meta["language"] = extract_language(last_user)
    meta["lead_score"] = compute_lead_score(messages)

    try:
        # k=3 (not 5) and a hard length cap keep the prompt within tight
        # input-token budgets (e.g. free OpenRouter tiers ~2.4k tokens).
        docs = similarity_search(last_user, k=3)
        context = "\n\n---\n\n".join(d.page_content for d in docs)[:1200]
    except Exception as e:
        logger.error(f"Knowledge retrieval failed: {e}")
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
    for _ in range(MAX_TOOL_ITERATIONS):
        gathered = None  # AIMessageChunks accumulate (incl. tool_calls) via +
        for chunk in llm.stream(lc_messages):
            gathered = chunk if gathered is None else gathered + chunk
            if chunk.content:
                final_text += chunk.content
                yield chunk.content

        tool_calls = getattr(gathered, "tool_calls", None)
        if not tool_calls:
            break

        lc_messages.append(gathered)
        for call in tool_calls:
            tool = TOOL_MAP.get(call["name"])
            try:
                output = tool.invoke(call["args"]) if tool else f"Unknown tool: {call['name']}"
            except Exception as e:
                logger.error(f"Tool {call['name']} failed: {e}")
                output = f"Tool error: {e}"
            lc_messages.append(ToolMessage(content=str(output), tool_call_id=call["id"]))

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
