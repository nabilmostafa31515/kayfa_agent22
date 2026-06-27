"""Cost/behaviour analyzer → automatic optimization recommendations.

Reads recent ``behavior_logs`` (rich per-message detail) and ``usage_logs``
(authoritative cost), computes behaviour metrics, compares them to configurable
thresholds, and emits costed recommendations:

    current cost  →  suggested improvement  →  estimated savings

Detected behaviours: excessive retrieved chunks, large prompts, too many tool
calls, long conversation history, sequential tool calls that can be parallelised,
high token usage, repeated FAQ questions on an expensive model, and (when the
embedder is paid) un-cached embeddings.

Savings are ESTIMATES derived from the observed token/cost mix; each is labelled
as such in the UI.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from src.config import pricing
from src.config.monitoring import get_config
from src.rag.aliases import normalize_ar
from src.monitoring import behavior_repository, usage_repository

logger = logging.getLogger(__name__)

# Share of input tokens attributable to retrieved context vs. conversation
# history — used to attribute savings to the right lever. Tunable assumptions.
_CONTEXT_SHARE = 0.6
_HISTORY_SHARE = 0.3


class OptimizationRecommendation(BaseModel):
    id: str
    category: str
    severity: str               # high | medium | low
    title: str
    detail: str                 # the actionable recommendation text
    current_value: str = ""
    suggested_value: str = ""
    current_cost: float = 0.0       # cost basis the lever acts on (USD, window)
    estimated_savings: float = 0.0  # USD over the analysed window
    estimated_savings_pct: float = 0.0
    latency_note: str = ""


class OptimizationReport(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window: int = 0                  # rows analysed
    messages: int = 0
    metrics: dict = Field(default_factory=dict)
    total_cost: float = 0.0          # total cost over the window
    total_estimated_savings: float = 0.0
    projected_cost: float = 0.0
    recommendations: list[OptimizationRecommendation] = Field(default_factory=list)

    def to_doc(self) -> dict:
        data = self.model_dump()
        data["recommendations"] = [r.model_dump() for r in self.recommendations]
        return data


# ── Metrics ───────────────────────────────────────────────────────────────────────
def _compute_metrics(traces: list[dict], usage_rows: list[dict]) -> dict:
    n_msgs = len(traces)
    n_calls = len(usage_rows)

    # Cost basis (recomputed from tokens + pricing so input/output split is exact).
    total_cost = sum(r.get("total_cost", 0.0) or 0.0 for r in usage_rows)
    input_cost = output_cost = 0.0
    for r in usage_rows:
        p_in, p_out = pricing.chat_price(r.get("model", ""))
        input_cost += (r.get("input_tokens", 0) or 0) / 1e6 * p_in
        output_cost += (r.get("output_tokens", 0) or 0) / 1e6 * p_out

    # Behaviour aggregates from the rich traces.
    chunk_counts = [len(t.get("retrieved_chunks", []) or []) for t in traces]
    tool_counts = [len(t.get("tool_calls", []) or []) for t in traces]
    total_tokens = [t.get("total_tokens", 0) or 0 for t in traces]
    latencies = [t.get("total_latency_ms", 0.0) or 0.0 for t in traces]

    # Largest single input prompt across all llm calls.
    max_input = 0
    parallelizable = 0   # llm turns that asked for >1 tool (sequential today)
    for t in traces:
        for c in (t.get("llm_calls", []) or []):
            max_input = max(max_input, c.get("input_tokens", 0) or 0)
            if (c.get("tool_calls", 0) or 0) > 1:
                parallelizable += 1

    def _avg(xs):
        return (sum(xs) / len(xs)) if xs else 0.0

    return {
        "messages": n_msgs,
        "llm_calls": n_calls,
        "total_cost": round(total_cost, 8),
        "input_cost": round(input_cost, 8),
        "output_cost": round(output_cost, 8),
        "avg_chunks": round(_avg(chunk_counts), 2),
        "avg_tool_calls": round(_avg(tool_counts), 2),
        "avg_total_tokens": round(_avg(total_tokens), 1),
        "max_input_tokens": max_input,
        "avg_latency_ms": round(_avg(latencies), 1),
        "max_latency_ms": round(max(latencies) if latencies else 0.0, 1),
        "avg_cost_per_message": round((total_cost / n_msgs) if n_msgs else 0.0, 8),
        "avg_cost_per_call": round((total_cost / n_calls) if n_calls else 0.0, 8),
        "parallelizable_turns": parallelizable,
    }


def _faq_repeats(traces: list[dict], threshold: int) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    samples: dict[str, str] = {}
    for t in traces:
        prompt = (t.get("user_prompt", "") or "").strip()
        if not prompt:
            continue
        key = normalize_ar(prompt)[:120]
        counts[key] = counts.get(key, 0) + 1
        samples.setdefault(key, prompt)
    repeats = [(samples[k], c) for k, c in counts.items() if c >= threshold]
    repeats.sort(key=lambda kc: kc[1], reverse=True)
    return repeats


# ── Analysis ───────────────────────────────────────────────────────────────────────
def analyze(window: int | None = None) -> OptimizationReport:
    """Build an optimization report from the most recent activity."""
    cfg = get_config()
    th = cfg.thresholds
    window = window or cfg.analysis_window

    traces = behavior_repository.list_recent_traces(window)
    usage_rows = usage_repository.get_recent_usage(window)
    metrics = _compute_metrics(traces, usage_rows)

    total_cost = metrics["total_cost"]
    recs: list[OptimizationRecommendation] = []

    def pct(saving: float) -> float:
        return round((saving / total_cost * 100.0), 2) if total_cost else 0.0

    # 1) Excessive retrieved chunks → reduce k.
    if metrics["avg_chunks"] > th.max_retrieved_chunks and metrics["avg_chunks"] > 0:
        target = cfg.default_retrieval_k
        reduction = max(0.0, (metrics["avg_chunks"] - target) / metrics["avg_chunks"])
        saving = round(metrics["input_cost"] * _CONTEXT_SHARE * reduction, 8)
        recs.append(OptimizationRecommendation(
            id="reduce_chunks", category="Retrieval", severity="high",
            title="Reduce retrieved chunks",
            detail=(f"Average retrieval pulls {metrics['avg_chunks']} chunks per message. "
                    f"Reduce retrieved chunks from {round(metrics['avg_chunks'])} to {target} "
                    "to shrink the prompt with negligible answer-quality impact."),
            current_value=f"{metrics['avg_chunks']} chunks",
            suggested_value=f"{target} chunks",
            current_cost=round(metrics["input_cost"], 8),
            estimated_savings=saving, estimated_savings_pct=pct(saving),
        ))

    # 2) Large prompts → summarise old messages / trim history.
    if metrics["max_input_tokens"] > th.max_input_tokens_per_call:
        over = (metrics["max_input_tokens"] - th.max_input_tokens_per_call)
        reduction = min(0.6, over / max(metrics["max_input_tokens"], 1))
        saving = round(metrics["input_cost"] * _HISTORY_SHARE * reduction, 8)
        recs.append(OptimizationRecommendation(
            id="trim_prompt", category="Prompt", severity="medium",
            title="Summarise old messages (large prompts)",
            detail=(f"Largest prompt reached {metrics['max_input_tokens']} input tokens "
                    f"(limit {th.max_input_tokens_per_call}). Summarise old messages and "
                    "keep only the last few turns to cap prompt growth."),
            current_value=f"{metrics['max_input_tokens']} input tokens (peak)",
            suggested_value=f"≤ {th.max_input_tokens_per_call} input tokens",
            current_cost=round(metrics["input_cost"], 8),
            estimated_savings=saving, estimated_savings_pct=pct(saving),
        ))

    # 3) Too many tool calls → batch / lean on injected context.
    if metrics["avg_tool_calls"] > th.max_tool_calls_per_message:
        extra = metrics["avg_tool_calls"] - th.max_tool_calls_per_message
        # Each extra tool call costs roughly one extra LLM round-trip.
        saving = round(metrics["avg_cost_per_call"] * extra * metrics["messages"], 8)
        recs.append(OptimizationRecommendation(
            id="reduce_tool_calls", category="Tools", severity="high",
            title="Batch tool calls",
            detail=(f"Messages average {metrics['avg_tool_calls']} tool calls "
                    f"(target ≤ {th.max_tool_calls_per_message}). Batch tool calls and rely on "
                    "the pre-injected KB context to cut extra LLM round-trips."),
            current_value=f"{metrics['avg_tool_calls']} tool calls / msg",
            suggested_value=f"≤ {th.max_tool_calls_per_message} / msg",
            current_cost=total_cost,
            estimated_savings=saving, estimated_savings_pct=pct(saving),
        ))

    # 4) Sequential tool calls that can be parallelised (latency).
    if metrics["parallelizable_turns"] > 0:
        recs.append(OptimizationRecommendation(
            id="parallel_tools", category="Latency", severity="medium",
            title="Parallelise independent tool calls",
            detail=(f"{metrics['parallelizable_turns']} turn(s) requested multiple tools that "
                    "run sequentially today. Execute independent tool calls in parallel to cut latency."),
            current_value=f"{metrics['parallelizable_turns']} sequential multi-tool turns",
            suggested_value="parallel execution",
            current_cost=0.0, estimated_savings=0.0, estimated_savings_pct=0.0,
            latency_note=f"Up to ~{metrics['parallelizable_turns']} turns could shave a tool round-trip each.",
        ))

    # 5) High token usage → cap completion length.
    if metrics["avg_total_tokens"] > th.max_total_tokens_per_message:
        reduction = min(0.4, (metrics["avg_total_tokens"] - th.max_total_tokens_per_message)
                        / max(metrics["avg_total_tokens"], 1))
        saving = round(total_cost * reduction, 8)
        recs.append(OptimizationRecommendation(
            id="high_tokens", category="Tokens", severity="medium",
            title="Reduce high token usage",
            detail=(f"Average {metrics['avg_total_tokens']} tokens per message "
                    f"(limit {th.max_total_tokens_per_message}). Lower OPENAI_MAX_TOKENS and tighten the "
                    "system prompt to reduce spend."),
            current_value=f"{metrics['avg_total_tokens']} tokens / msg",
            suggested_value=f"≤ {th.max_total_tokens_per_message} / msg",
            current_cost=total_cost,
            estimated_savings=saving, estimated_savings_pct=pct(saving),
        ))

    # 6) FAQ repeats → cheaper model + cache.
    repeats = _faq_repeats(traces, th.faq_repeat_threshold)
    if repeats:
        faq_msgs = sum(c for _, c in repeats)
        # Price delta between the current model and the cheaper model, on the
        # average per-message token mix.
        cur_model = usage_rows[0].get("model", "") if usage_rows else ""
        cur_in, cur_out = pricing.chat_price(cur_model)
        ch_in, ch_out = pricing.chat_price(cfg.cheap_chat_model)
        avg_in = (metrics["avg_total_tokens"] * 0.7)
        avg_out = (metrics["avg_total_tokens"] * 0.3)
        delta = max(0.0, (avg_in / 1e6 * (cur_in - ch_in)) + (avg_out / 1e6 * (cur_out - ch_out)))
        saving = round(delta * faq_msgs, 8)
        recs.append(OptimizationRecommendation(
            id="faq_cheaper_model", category="Routing", severity="high",
            title="Switch FAQ questions to a cheaper model",
            detail=(f"{len(repeats)} question(s) repeat ≥{th.faq_repeat_threshold}× "
                    f"({faq_msgs} messages). Route these FAQs to {cfg.cheap_chat_model} and cache answers."),
            current_value=f"{cur_model or 'current model'} for FAQs",
            suggested_value=f"{cfg.cheap_chat_model} + answer cache",
            current_cost=total_cost,
            estimated_savings=saving, estimated_savings_pct=pct(saving),
        ))

    # 7) Cache embedding results (only a $ saving on a paid embedder).
    emb_cost = sum(r.get("embedding_cost", 0.0) or 0.0 for r in usage_rows)
    if repeats and emb_cost > 0:
        repeat_share = sum(c - 1 for _, c in repeats) / max(metrics["messages"], 1)
        saving = round(emb_cost * min(repeat_share, 0.9), 8)
        recs.append(OptimizationRecommendation(
            id="cache_embeddings", category="Embeddings", severity="medium",
            title="Cache embedding results",
            detail="Repeated questions re-embed identical text. Cache embedding results "
                   "(keyed by normalised query) to avoid paying to embed the same query twice.",
            current_value=f"${emb_cost:.6f} embedding spend",
            suggested_value="cache hits on repeats",
            current_cost=round(emb_cost, 8),
            estimated_savings=saving, estimated_savings_pct=pct(saving),
        ))
    elif metrics["avg_chunks"] > 0 and emb_cost == 0:
        # Local embedder: no $ saving, but caching still cuts latency.
        recs.append(OptimizationRecommendation(
            id="cache_embeddings_latency", category="Embeddings", severity="low",
            title="Cache embedding results (latency)",
            detail="Embeddings run locally (no $ cost), but caching results for repeated "
                   "queries still removes redundant CPU work and lowers reply latency.",
            current_value="re-embed every query",
            suggested_value="cache by normalised query",
            current_cost=0.0, estimated_savings=0.0, estimated_savings_pct=0.0,
            latency_note="Removes redundant CPU embedding on repeat questions.",
        ))

    # 8) High latency overall.
    if metrics["avg_latency_ms"] > th.high_latency_ms:
        recs.append(OptimizationRecommendation(
            id="high_latency", category="Latency", severity="medium",
            title="Reduce response latency",
            detail=(f"Average turn latency is {metrics['avg_latency_ms']:.0f} ms "
                    f"(target ≤ {th.high_latency_ms:.0f} ms). Reduce chunks/tool round-trips, "
                    "cache embeddings, and consider a faster model tier."),
            current_value=f"{metrics['avg_latency_ms']:.0f} ms avg",
            suggested_value=f"≤ {th.high_latency_ms:.0f} ms",
            current_cost=0.0, estimated_savings=0.0, estimated_savings_pct=0.0,
            latency_note="Composite of retrieval + LLM + tool round-trips.",
        ))

    # Cap total savings to a sane fraction of spend (estimates are heuristic).
    total_savings = round(min(sum(r.estimated_savings for r in recs), total_cost * 0.85), 8)
    recs.sort(key=lambda r: r.estimated_savings, reverse=True)

    return OptimizationReport(
        window=len(usage_rows),
        messages=metrics["messages"],
        metrics=metrics,
        total_cost=total_cost,
        total_estimated_savings=total_savings,
        projected_cost=round(max(0.0, total_cost - total_savings), 8),
        recommendations=recs,
    )
