"""Tunable configuration for the monitoring & optimization layer.

A single Pydantic model that reads sane defaults from the environment. It carries
the embedding identity (provider/model — needed to price embedding tokens) and
the thresholds the optimizer uses to flag expensive behaviour.

Nothing here changes Part 1 behaviour; it only describes how the new layer reads,
prices, and analyses the data Part 1 already produces.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class OptimizationThresholds(BaseModel):
    """Above these, the optimizer raises a recommendation."""

    max_tool_calls_per_message: int = 2
    max_input_tokens_per_call: int = 1500     # "large prompt"
    max_retrieved_chunks: int = 5             # "excessive retrieved chunks"
    max_history_messages: int = 6             # "long conversation history"
    max_total_tokens_per_message: int = 2500  # "high token usage"
    high_latency_ms: float = 6000.0           # "slow / sequential calls"
    # FAQ detection: a normalized prompt seen at least this many times is a
    # repeat-question candidate for a cheaper model / cache.
    faq_repeat_threshold: int = 3


class MonitoringConfig(BaseModel):
    """Resolved monitoring configuration for the running process."""

    # Embedding identity — used to count and price embedding tokens. Defaults
    # match src/rag/embeddings.py (local, free), but can be repointed at a paid
    # provider via env without touching the RAG code.
    embedding_provider: str = Field(default="huggingface")
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    # Default retrieval breadth (mirrors stream_chat's k=4) — the optimizer
    # compares observed chunk counts against this to suggest reductions.
    default_retrieval_k: int = 4

    # A cheaper model the optimizer can recommend for FAQ / low-complexity turns.
    cheap_chat_model: str = "gpt-oss-20b"

    # How many of the most recent usage rows the optimizer scans by default.
    analysis_window: int = 1000

    thresholds: OptimizationThresholds = Field(default_factory=OptimizationThresholds)


_config: MonitoringConfig | None = None


def get_config() -> MonitoringConfig:
    """Build (once) the monitoring config from the environment."""
    global _config
    if _config is None:
        _config = MonitoringConfig(
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "huggingface"),
            embedding_model=os.getenv(
                "EMBEDDING_MODEL",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            ),
            default_retrieval_k=_env_int("RETRIEVAL_K", 4),
            cheap_chat_model=os.getenv("CHEAP_CHAT_MODEL", "gpt-oss-20b"),
            analysis_window=_env_int("OPTIMIZATION_WINDOW", 1000),
            thresholds=OptimizationThresholds(
                max_tool_calls_per_message=_env_int("OPT_MAX_TOOL_CALLS", 2),
                max_input_tokens_per_call=_env_int("OPT_MAX_INPUT_TOKENS", 1500),
                max_retrieved_chunks=_env_int("OPT_MAX_CHUNKS", 5),
                max_history_messages=_env_int("OPT_MAX_HISTORY", 6),
                max_total_tokens_per_message=_env_int("OPT_MAX_TOTAL_TOKENS", 2500),
                high_latency_ms=_env_float("OPT_HIGH_LATENCY_MS", 6000.0),
                faq_repeat_threshold=_env_int("OPT_FAQ_REPEATS", 3),
            ),
        )
    return _config
