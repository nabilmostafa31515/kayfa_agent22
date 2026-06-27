"""Pydantic schemas for the monitoring layer.

Two persisted shapes:

* ``UsageLog``      — one document per LLM call (collection ``usage_logs``).
                      Carries the cost fields required by Part 2. Embedding
                      tokens/cost are attached to the first call of a message so
                      that SUM(total_cost) is exact at message/conversation/user
                      level.
* ``BehaviorTrace`` — one document per user message (collection ``behavior_logs``)
                      holding the full, replayable execution: prompt → reasoning
                      → retrieved context → sources → tool calls/args/results →
                      final response → latency → tokens → cost.

The nested records (``LLMCallRecord``, ``ToolCallRecord``, ``RetrievedChunk``)
are the per-step detail the Behaviour Trace page replays.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Step-level records ────────────────────────────────────────────────────────────
class RetrievedChunk(BaseModel):
    source: str = ""
    score: float | None = None
    preview: str = ""


class ToolCallRecord(BaseModel):
    sequence: int = 0
    name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str = ""
    latency_ms: float = 0.0
    error: str | None = None


class LLMCallRecord(BaseModel):
    index: int = 0
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    tool_calls: int = 0          # how many tool calls THIS llm turn requested
    content_preview: str = ""


# ── Persisted: usage log (one per LLM call) ──────────────────────────────────────
class UsageLog(BaseModel):
    message_id: str
    conversation_id: str = ""
    user_id: str = ""
    timestamp: datetime = Field(default_factory=utcnow)

    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    # Embedding usage (non-zero only on the first call of a message).
    embedding_tokens: int = 0
    embedding_provider: str = ""
    embedding_model: str = ""

    latency_ms: float = 0.0
    llm_call_index: int = 0
    tool_calls: int = 0

    # Cost breakdown. ``calculated_cost`` = chat-only; ``total_cost`` = chat + embedding.
    chat_cost: float = 0.0
    embedding_cost: float = 0.0
    calculated_cost: float = 0.0
    total_cost: float = 0.0

    def to_doc(self) -> dict:
        return self.model_dump()


# ── Persisted: behaviour trace (one per message) ─────────────────────────────────
class BehaviorTrace(BaseModel):
    message_id: str
    conversation_id: str = ""
    user_id: str = ""
    timestamp: datetime = Field(default_factory=utcnow)

    provider: str = ""
    model: str = ""

    # The replayable execution steps.
    user_prompt: str = ""
    reasoning_summary: str = ""
    retrieved_context: str = ""
    knowledge_sources: list[str] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    final_response: str = ""

    # Aggregates.
    retrieval_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    embedding_tokens: int = 0
    total_tokens: int = 0
    chat_cost: float = 0.0
    embedding_cost: float = 0.0
    total_cost: float = 0.0

    def to_doc(self) -> dict:
        data = self.model_dump()
        data["retrieved_chunks"] = [c.model_dump() for c in self.retrieved_chunks]
        data["llm_calls"] = [c.model_dump() for c in self.llm_calls]
        data["tool_calls"] = [c.model_dump() for c in self.tool_calls]
        return data
