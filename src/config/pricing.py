"""Cross-provider pricing for chat and embedding models.

The monitoring layer must cost a turn even when the chat model and the embedding
model come from *different* providers (e.g. a Groq chat model + an OpenAI
embedding model, or — as today — a Groq chat model + a free local HuggingFace
embedding model). This module is the single source of truth for those prices.

Prices are USD per 1,000,000 tokens. They are ESTIMATES — tune them to your
provider's current rates, either by editing the tables below or, without touching
code, via the ``MONITORING_PRICING_JSON`` environment variable, e.g.::

    MONITORING_PRICING_JSON='{"chat": {"gpt-4o": [2.5, 10.0]},
                              "embedding": {"text-embedding-3-small": 0.02}}'

Models are matched by **substring** (longest match wins) so
``openai/gpt-oss-120b:free`` resolves to the ``gpt-oss-120b`` entry.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


# ── Default price tables (USD per 1M tokens) ─────────────────────────────────────
# chat model substring -> (input_$/1M, output_$/1M)
_CHAT_PRICING: dict[str, tuple[float, float]] = {
    "gpt-oss-120b":      (0.15, 0.75),
    "gpt-oss-20b":       (0.10, 0.50),
    "llama-3.3-70b":     (0.59, 0.79),
    "llama-3.1-70b":     (0.59, 0.79),
    "llama-3.1-8b":      (0.05, 0.08),
    "llama3-70b":        (0.59, 0.79),
    "llama3-8b":         (0.05, 0.08),
    "mixtral-8x7b":      (0.24, 0.24),
    "gemma2-9b":         (0.20, 0.20),
    "gpt-4o-mini":       (0.15, 0.60),
    "gpt-4o":            (2.50, 10.00),
    "gpt-4-turbo":       (10.00, 30.00),
    "gpt-3.5-turbo":     (0.50, 1.50),
}
_DEFAULT_CHAT_PRICE: tuple[float, float] = (0.50, 1.50)

# embedding model substring -> $/1M tokens
_EMBEDDING_PRICING: dict[str, float] = {
    # Local / self-hosted (SentenceTransformers) — free to run, tokens still tracked.
    "paraphrase-multilingual": 0.0,
    "minilm":                  0.0,
    "all-mpnet":               0.0,
    "bge-":                    0.0,
    "e5-":                     0.0,
    # OpenAI hosted embeddings.
    "text-embedding-3-small":  0.02,
    "text-embedding-3-large":  0.13,
    "text-embedding-ada-002":  0.10,
    # Cohere.
    "embed-english":           0.10,
    "embed-multilingual":      0.10,
}
_DEFAULT_EMBEDDING_PRICE: float = 0.0


# ── Optional env override (applied once at import) ────────────────────────────────
def _apply_env_overrides() -> None:
    raw = os.getenv("MONITORING_PRICING_JSON")
    if not raw:
        return
    try:
        data = json.loads(raw)
        for k, v in (data.get("chat") or {}).items():
            _CHAT_PRICING[k.lower()] = (float(v[0]), float(v[1]))
        for k, v in (data.get("embedding") or {}).items():
            _EMBEDDING_PRICING[k.lower()] = float(v)
        logger.info("Applied MONITORING_PRICING_JSON overrides")
    except Exception as e:  # bad JSON must never crash the app
        logger.warning("Ignoring invalid MONITORING_PRICING_JSON: %s", e)


_apply_env_overrides()


# ── Lookups (longest-substring match wins) ───────────────────────────────────────
def _match(table: dict, model: str):
    m = (model or "").lower()
    best_key, best_len = None, -1
    for key in table:
        if key in m and len(key) > best_len:
            best_key, best_len = key, len(key)
    return table[best_key] if best_key is not None else None


def chat_price(model: str) -> tuple[float, float]:
    """Return (input_$/1M, output_$/1M) for a chat model."""
    return _match(_CHAT_PRICING, model) or _DEFAULT_CHAT_PRICE


def embedding_price(model: str) -> float:
    """Return $/1M tokens for an embedding model."""
    price = _match(_EMBEDDING_PRICING, model)
    return _DEFAULT_EMBEDDING_PRICE if price is None else price


# ── Cost calculators ─────────────────────────────────────────────────────────────
def chat_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost of one chat completion call."""
    p_in, p_out = chat_price(model)
    cost = (input_tokens or 0) / 1_000_000 * p_in + (output_tokens or 0) / 1_000_000 * p_out
    return round(cost, 8)


def embedding_cost(model: str, tokens: int) -> float:
    """USD cost of embedding ``tokens`` with ``model`` (0.0 for local models)."""
    return round((tokens or 0) / 1_000_000 * embedding_price(model), 8)


# ── Provider inference ───────────────────────────────────────────────────────────
def infer_chat_provider(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """Best-effort provider name from the endpoint, then the key prefix.

    Mirrors the auto-routing in ``sales_agent.get_llm`` so usage logs are
    attributed to the same provider that actually served the request.
    """
    b = (base_url or "").lower()
    if "groq.com" in b:
        return "groq"
    if "openrouter.ai" in b:
        return "openrouter"
    if "api.openai.com" in b:
        return "openai"
    if api_key:
        if api_key.startswith("gsk_"):
            return "groq"
        if api_key.startswith("sk-or-"):
            return "openrouter"
        if api_key.startswith("sk-"):
            return "openai"
    if b:  # some other custom gateway host
        host = b.split("//")[-1].split("/")[0]
        return host or "custom"
    return "openai"
