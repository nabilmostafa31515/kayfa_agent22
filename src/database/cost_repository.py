"""LLM cost records, stamped with the end-user's id.

Every agent turn records its token usage and an estimated USD cost in the `costs`
collection, keyed by `user_id` and `conversation_id`. This makes spend
attributable per user/conversation/model for the manager dashboards.

Prices are USD per 1M tokens (input, output). They are ESTIMATES — adjust to your
provider's current rates. Each model's price is matched by substring so e.g.
"openai/gpt-oss-120b" matches the "gpt-oss-120b" entry.
"""

import logging
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING

from .mongodb import get_db

logger = logging.getLogger(__name__)

# model-substring -> (input_$/1M, output_$/1M)
PRICING: dict[str, tuple[float, float]] = {
    "gpt-oss-120b":     (0.15, 0.75),
    "gpt-oss-20b":      (0.10, 0.50),
    "llama-3.3-70b":    (0.59, 0.79),
    "llama-3.1-8b":     (0.05, 0.08),
    "llama-3.1-70b":    (0.59, 0.79),
    "gpt-4o-mini":      (0.15, 0.60),
    "gpt-4o":           (2.50, 10.00),
}
_DEFAULT_PRICE = (0.50, 1.50)

_indexed = False


def _costs():
    return get_db()["costs"]


def _ensure_indexes() -> None:
    global _indexed
    if _indexed:
        return
    try:
        _costs().create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_time")
    except Exception as e:
        logger.warning(f"Could not ensure costs index: {e}")
    _indexed = True


def _price_for(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    for key, price in PRICING.items():
        if key in m:
            return price
    return _DEFAULT_PRICE


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost estimate for one call."""
    p_in, p_out = _price_for(model)
    return round(input_tokens / 1_000_000 * p_in + output_tokens / 1_000_000 * p_out, 6)


def record_cost(
    user_id: str,
    conversation_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> str | None:
    """Persist one cost record. Best-effort: never breaks the chat on failure."""
    try:
        _ensure_indexes()
        cost = estimate_cost(model, input_tokens, output_tokens)
        doc = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "model": model,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "total_tokens": int(input_tokens) + int(output_tokens),
            "cost_usd": cost,
            "created_at": datetime.now(timezone.utc),
        }
        result = _costs().insert_one(doc)
        logger.info(
            "Cost: %s in / %s out (%s) = $%.6f [user=%s]",
            input_tokens, output_tokens, model, cost, user_id or "-",
        )
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"record_cost failed: {e}")
        return None


# ── Aggregations (manager dashboard) ──────────────────────────────────────────
def get_cost_summary() -> dict:
    pipeline = [{"$group": {
        "_id": None,
        "total_cost": {"$sum": "$cost_usd"},
        "total_tokens": {"$sum": "$total_tokens"},
        "calls": {"$sum": 1},
    }}]
    res = list(_costs().aggregate(pipeline))
    base = res[0] if res else {"total_cost": 0, "total_tokens": 0, "calls": 0}
    base.pop("_id", None)
    return base


def get_cost_by_model() -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$model",
                    "cost": {"$sum": "$cost_usd"},
                    "tokens": {"$sum": "$total_tokens"},
                    "calls": {"$sum": 1}}},
        {"$sort": {"cost": -1}},
    ]
    return [{"model": d["_id"] or "—", "cost": d["cost"],
             "tokens": d["tokens"], "calls": d["calls"]}
            for d in _costs().aggregate(pipeline)]


def get_cost_by_user(limit: int = 20) -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$user_id",
                    "cost": {"$sum": "$cost_usd"},
                    "tokens": {"$sum": "$total_tokens"},
                    "calls": {"$sum": 1}}},
        {"$sort": {"cost": -1}},
        {"$limit": limit},
    ]
    return [{"user_id": d["_id"] or "—", "cost": d["cost"],
             "tokens": d["tokens"], "calls": d["calls"]}
            for d in _costs().aggregate(pipeline)]


def get_cost_over_time() -> list[dict]:
    pipeline = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "cost": {"$sum": "$cost_usd"},
            "tokens": {"$sum": "$total_tokens"}}},
        {"$sort": {"_id": 1}},
    ]
    return [{"date": d["_id"], "cost": d["cost"], "tokens": d["tokens"]}
            for d in _costs().aggregate(pipeline)]
