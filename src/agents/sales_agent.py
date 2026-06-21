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
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=0.4,
        streaming=True,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        # Bound completion length. Without this, ChatOpenAI requests the model's
        # full max (16k+), which some gateways/accounts (e.g. free OpenRouter
        # credit tiers) reject with HTTP 402. Tune via OPENAI_MAX_TOKENS.
        max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "1500")),
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
        docs = similarity_search(last_user, k=5)
        state["context"] = "\n\n---\n\n".join(d.page_content for d in docs)
    except Exception as e:
        logger.error(f"Knowledge retrieval failed: {e}")
        state["context"] = ""
    return state


def agent_node(state: AgentState) -> AgentState:
    """Call the LLM with system prompt, context, and conversation history."""
    llm = get_llm()

    system_content = SYSTEM_PROMPT.format(
        context=state["context"],
        chat_history="\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in state["messages"][:-1]
        )
    )

    lc_messages = [SystemMessage(content=system_content)]
    for m in state["messages"]:
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
