"""TurnRecorder — automatic per-turn usage logging + behaviour tracing.

The sales agent's chat loop is hand-rolled (manual streaming + tool loop), so the
most reliable, lowest-touch way to capture a complete, accurate trace is to let
the loop hand its events to a recorder as they happen. From the application's
point of view this is fully automatic: the chat page already calls
``stream_chat`` — it never logs anything itself.

Usage::

    rec = TurnRecorder(user_id, conversation_id, provider, model,
                       embedding_provider, embedding_model)
    rec.set_prompt(text)
    with rec.time_retrieval():
        docs = similarity_search(...)
    rec.record_retrieval(query, docs)
    for _ in range(MAX):
        with rec.llm_call() as call:
            ... stream ...
            call.set_usage(in, out); call.set_content(text); call.mark_tool_calls(n)
        for tc in tool_calls:
            with rec.tool_call(name, args) as t:
                ... ; t.set_result(out)   # or t.set_error(msg)
    rec.set_final_response(text)
    rec.finalize()

``finalize`` computes chat + embedding cost (cross-provider), writes one
``usage_logs`` row per LLM call (embedding attached to the first) and one
``behavior_logs`` row for the message. Everything is best-effort.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager

from src.config import pricing
from src.config.monitoring import get_config
from .models import (
    BehaviorTrace, LLMCallRecord, RetrievedChunk, ToolCallRecord, UsageLog,
)
from .tokens import count_tokens
from . import usage_repository, behavior_repository

logger = logging.getLogger(__name__)

_PREVIEW = 280  # chars kept for content/result previews in the trace


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


class _LLMCallHandle:
    """Mutable handle the chat loop fills in for one streamed LLM call."""

    def __init__(self, index: int, provider: str, model: str):
        self.record = LLMCallRecord(index=index, provider=provider, model=model)

    def set_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.record.input_tokens = int(input_tokens or 0)
        self.record.output_tokens = int(output_tokens or 0)

    def set_content(self, text: str) -> None:
        self.record.content_preview = (text or "")[:_PREVIEW]

    def mark_tool_calls(self, n: int) -> None:
        self.record.tool_calls = int(n or 0)


class _ToolCallHandle:
    """Mutable handle for one tool execution."""

    def __init__(self, sequence: int, name: str, arguments: dict):
        self.record = ToolCallRecord(
            sequence=sequence, name=name or "", arguments=arguments or {},
        )

    def set_result(self, result) -> None:
        self.record.result = str(result)[:_PREVIEW] if result is not None else ""

    def set_error(self, message: str) -> None:
        self.record.error = str(message)


class TurnRecorder:
    def __init__(
        self,
        user_id: str,
        conversation_id: str,
        provider: str,
        model: str,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
        message_id: str | None = None,
    ):
        cfg = get_config()
        self.user_id = user_id or ""
        self.conversation_id = conversation_id or ""
        self.provider = provider or ""
        self.model = model or ""
        self.embedding_provider = embedding_provider or cfg.embedding_provider
        self.embedding_model = embedding_model or cfg.embedding_model
        self.message_id = message_id or uuid.uuid4().hex

        self.user_prompt = ""
        self.final_response = ""
        self.retrieved_context = ""
        self.knowledge_sources: list[str] = []
        self.retrieved_chunks: list[RetrievedChunk] = []
        self.embedding_tokens = 0
        self.retrieval_latency_ms = 0.0

        self.llm_calls: list[LLMCallRecord] = []
        self.tool_calls: list[ToolCallRecord] = []

        self._turn_start = _now_ms()
        self.total_latency_ms = 0.0

    # ── Inputs ────────────────────────────────────────────────────────────────────
    def set_prompt(self, text: str) -> None:
        self.user_prompt = text or ""

    def set_final_response(self, text: str) -> None:
        self.final_response = text or ""

    # ── Retrieval ───────────────────────────────────────────────────────────────
    @contextmanager
    def time_retrieval(self):
        start = _now_ms()
        try:
            yield
        finally:
            self.retrieval_latency_ms = round(_now_ms() - start, 1)

    def record_retrieval(self, query: str, docs) -> None:
        """Capture retrieved context, knowledge sources, and embedding tokens.

        ``docs`` is the list returned by ``similarity_search`` (LangChain
        Documents). Embedding tokens are estimated from the alias-expanded query —
        the exact text the embedder receives — so cost tracks reality even though
        the local embedder reports no usage.
        """
        sources, chunks = [], []
        for d in (docs or []):
            meta = getattr(d, "metadata", {}) or {}
            src = meta.get("source", "") or meta.get("file", "") or "unknown"
            if src not in sources:
                sources.append(src)
            content = getattr(d, "page_content", "") or ""
            chunks.append(RetrievedChunk(
                source=src,
                score=meta.get("score"),
                preview=content[:_PREVIEW],
            ))
        self.knowledge_sources = sources
        self.retrieved_chunks = chunks
        self.retrieved_context = "\n\n---\n\n".join(
            getattr(d, "page_content", "") or "" for d in (docs or [])
        )

        # Embedding token estimate — use the same alias expansion the RAG uses.
        try:
            from src.rag.aliases import expand_query
            embed_text = expand_query(query or "")
        except Exception:
            embed_text = query or ""
        self.embedding_tokens = count_tokens(embed_text)

    # ── LLM calls ─────────────────────────────────────────────────────────────────
    @contextmanager
    def llm_call(self):
        handle = _LLMCallHandle(len(self.llm_calls), self.provider, self.model)
        start = _now_ms()
        try:
            yield handle
        finally:
            handle.record.latency_ms = round(_now_ms() - start, 1)
            self.llm_calls.append(handle.record)

    # ── Tool calls ────────────────────────────────────────────────────────────────
    @contextmanager
    def tool_call(self, name: str, arguments: dict):
        handle = _ToolCallHandle(len(self.tool_calls), name, arguments)
        start = _now_ms()
        try:
            yield handle
        finally:
            handle.record.latency_ms = round(_now_ms() - start, 1)
            self.tool_calls.append(handle.record)

    # ── Reasoning summary (honest synthesis of observed events) ──────────────────
    def _build_reasoning_summary(self) -> str:
        parts = []
        if self.knowledge_sources:
            parts.append(
                f"Retrieved {len(self.retrieved_chunks)} chunk(s) from "
                f"{len(self.knowledge_sources)} source(s): "
                + ", ".join(self.knowledge_sources)
            )
        else:
            parts.append("No knowledge-base context retrieved for this turn.")
        if self.tool_calls:
            names = ", ".join(t.name for t in self.tool_calls)
            parts.append(f"Executed {len(self.tool_calls)} tool call(s): {names}")
        else:
            parts.append("Answered directly from injected context (no tool calls).")
        parts.append(f"Completed in {len(self.llm_calls)} LLM round-trip(s).")
        return " | ".join(parts)

    # ── Persist ──────────────────────────────────────────────────────────────────
    def finalize(self) -> None:
        """Compute costs and persist usage logs + the behaviour trace.

        Best-effort: any failure is logged and swallowed so chat is never broken.
        """
        try:
            self.total_latency_ms = round(_now_ms() - self._turn_start, 1)
            emb_cost_total = pricing.embedding_cost(self.embedding_model, self.embedding_tokens)

            usage_logs: list[UsageLog] = []
            chat_cost_total = 0.0
            in_total = out_total = 0
            for i, call in enumerate(self.llm_calls):
                c_cost = pricing.chat_cost(call.model, call.input_tokens, call.output_tokens)
                chat_cost_total += c_cost
                in_total += call.input_tokens
                out_total += call.output_tokens
                # Attach embedding usage/cost to the first call only (retrieval is
                # once per message), so per-message/conversation/user sums are exact.
                e_tokens = self.embedding_tokens if i == 0 else 0
                e_cost = emb_cost_total if i == 0 else 0.0
                usage_logs.append(UsageLog(
                    message_id=self.message_id,
                    conversation_id=self.conversation_id,
                    user_id=self.user_id,
                    provider=call.provider or self.provider,
                    model=call.model or self.model,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                    embedding_tokens=e_tokens,
                    embedding_provider=self.embedding_provider if i == 0 else "",
                    embedding_model=self.embedding_model if i == 0 else "",
                    latency_ms=call.latency_ms,
                    llm_call_index=call.index,
                    tool_calls=call.tool_calls,
                    chat_cost=round(c_cost, 8),
                    embedding_cost=round(e_cost, 8),
                    calculated_cost=round(c_cost, 8),
                    total_cost=round(c_cost + e_cost, 8),
                ))

            usage_repository.record_usage_many(usage_logs)

            trace = BehaviorTrace(
                message_id=self.message_id,
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                provider=self.provider,
                model=self.model,
                user_prompt=self.user_prompt,
                reasoning_summary=self._build_reasoning_summary(),
                retrieved_context=self.retrieved_context,
                knowledge_sources=self.knowledge_sources,
                retrieved_chunks=self.retrieved_chunks,
                llm_calls=self.llm_calls,
                tool_calls=self.tool_calls,
                final_response=self.final_response,
                retrieval_latency_ms=self.retrieval_latency_ms,
                total_latency_ms=self.total_latency_ms,
                input_tokens=in_total,
                output_tokens=out_total,
                embedding_tokens=self.embedding_tokens,
                total_tokens=in_total + out_total,
                chat_cost=round(chat_cost_total, 8),
                embedding_cost=round(emb_cost_total, 8),
                total_cost=round(chat_cost_total + emb_cost_total, 8),
            )
            behavior_repository.record_trace(trace)
            logger.info(
                "Monitored turn %s: %s LLM call(s), %s tool call(s), $%.6f",
                self.message_id, len(self.llm_calls), len(self.tool_calls),
                trace.total_cost,
            )
        except Exception as e:
            logger.error("TurnRecorder.finalize failed: %s", e)
