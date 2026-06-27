"""Persistence + aggregations for the ``usage_logs`` collection.

One document per LLM call (see models.UsageLog). All writes are best-effort: a
DB hiccup must never break the live chat. Aggregations power the Cost Monitor and
the Dashboard KPIs (cost per message / conversation / user, over time, by
provider / model, token usage, latency, tool calls).
"""

from __future__ import annotations

import logging

from pymongo import ASCENDING, DESCENDING

from src.database.mongodb import get_db
from .models import UsageLog

logger = logging.getLogger(__name__)

_indexed = False


def _col():
    return get_db()["usage_logs"]


def _ensure_indexes() -> None:
    global _indexed
    if _indexed:
        return
    try:
        c = _col()
        c.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)], name="user_time")
        c.create_index([("conversation_id", ASCENDING)], name="conversation")
        c.create_index([("message_id", ASCENDING)], name="message")
        c.create_index([("timestamp", DESCENDING)], name="time")
    except Exception as e:
        logger.warning("Could not ensure usage_logs indexes: %s", e)
    _indexed = True


# ── Writes ────────────────────────────────────────────────────────────────────────
def record_usage(usage: UsageLog) -> str | None:
    try:
        _ensure_indexes()
        result = _col().insert_one(usage.to_doc())
        return str(result.inserted_id)
    except Exception as e:
        logger.error("record_usage failed: %s", e)
        return None


def record_usage_many(usages: list[UsageLog]) -> int:
    if not usages:
        return 0
    try:
        _ensure_indexes()
        result = _col().insert_many([u.to_doc() for u in usages])
        return len(result.inserted_ids)
    except Exception as e:
        logger.error("record_usage_many failed: %s", e)
        return 0


# ── Summary / KPIs ────────────────────────────────────────────────────────────────
def get_totals() -> dict:
    """Headline totals across all usage logs."""
    pipeline = [{"$group": {
        "_id": None,
        "total_cost": {"$sum": "$total_cost"},
        "chat_cost": {"$sum": "$chat_cost"},
        "embedding_cost": {"$sum": "$embedding_cost"},
        "input_tokens": {"$sum": "$input_tokens"},
        "output_tokens": {"$sum": "$output_tokens"},
        "embedding_tokens": {"$sum": "$embedding_tokens"},
        "total_tokens": {"$sum": {"$add": ["$input_tokens", "$output_tokens"]}},
        "llm_calls": {"$sum": 1},
        "tool_calls": {"$sum": "$tool_calls"},
        "avg_latency": {"$avg": "$latency_ms"},
        "conversations": {"$addToSet": "$conversation_id"},
        "messages": {"$addToSet": "$message_id"},
        "users": {"$addToSet": "$user_id"},
    }}]
    res = list(_col().aggregate(pipeline))
    if not res:
        return {
            "total_cost": 0.0, "chat_cost": 0.0, "embedding_cost": 0.0,
            "input_tokens": 0, "output_tokens": 0, "embedding_tokens": 0,
            "total_tokens": 0, "llm_calls": 0, "tool_calls": 0,
            "avg_latency": 0.0, "conversations": 0, "messages": 0, "users": 0,
        }
    d = res[0]
    return {
        "total_cost": d.get("total_cost", 0.0) or 0.0,
        "chat_cost": d.get("chat_cost", 0.0) or 0.0,
        "embedding_cost": d.get("embedding_cost", 0.0) or 0.0,
        "input_tokens": d.get("input_tokens", 0) or 0,
        "output_tokens": d.get("output_tokens", 0) or 0,
        "embedding_tokens": d.get("embedding_tokens", 0) or 0,
        "total_tokens": d.get("total_tokens", 0) or 0,
        "llm_calls": d.get("llm_calls", 0) or 0,
        "tool_calls": d.get("tool_calls", 0) or 0,
        "avg_latency": round(d.get("avg_latency", 0.0) or 0.0, 1),
        "conversations": len([c for c in d.get("conversations", []) if c]),
        "messages": len([m for m in d.get("messages", []) if m]),
        "users": len([u for u in d.get("users", []) if u]),
    }


# ── Cost on three levels (per user / conversation / message) ─────────────────────
def get_cost_per_user(limit: int = 50) -> list[dict]:
    pipeline = [
        {"$group": {
            "_id": "$user_id",
            "total_cost": {"$sum": "$total_cost"},
            "total_tokens": {"$sum": {"$add": ["$input_tokens", "$output_tokens"]}},
            "llm_calls": {"$sum": 1},
            "messages": {"$addToSet": "$message_id"},
            "conversations": {"$addToSet": "$conversation_id"},
        }},
        {"$sort": {"total_cost": -1}},
        {"$limit": limit},
    ]
    out = []
    for d in _col().aggregate(pipeline):
        out.append({
            "user_id": d["_id"] or "anonymous",
            "total_cost": d.get("total_cost", 0.0) or 0.0,
            "total_tokens": d.get("total_tokens", 0) or 0,
            "llm_calls": d.get("llm_calls", 0) or 0,
            "messages": len([m for m in d.get("messages", []) if m]),
            "conversations": len([c for c in d.get("conversations", []) if c]),
        })
    return out


def get_cost_per_conversation(limit: int = 50) -> list[dict]:
    pipeline = [
        {"$group": {
            "_id": "$conversation_id",
            "user_id": {"$first": "$user_id"},
            "total_cost": {"$sum": "$total_cost"},
            "total_tokens": {"$sum": {"$add": ["$input_tokens", "$output_tokens"]}},
            "llm_calls": {"$sum": 1},
            "tool_calls": {"$sum": "$tool_calls"},
            "messages": {"$addToSet": "$message_id"},
            "last_time": {"$max": "$timestamp"},
        }},
        {"$sort": {"total_cost": -1}},
        {"$limit": limit},
    ]
    out = []
    for d in _col().aggregate(pipeline):
        out.append({
            "conversation_id": d["_id"] or "—",
            "user_id": d.get("user_id", "") or "anonymous",
            "total_cost": d.get("total_cost", 0.0) or 0.0,
            "total_tokens": d.get("total_tokens", 0) or 0,
            "llm_calls": d.get("llm_calls", 0) or 0,
            "tool_calls": d.get("tool_calls", 0) or 0,
            "messages": len([m for m in d.get("messages", []) if m]),
            "last_time": d.get("last_time"),
        })
    return out


def get_cost_per_message(limit: int = 100) -> list[dict]:
    pipeline = [
        {"$group": {
            "_id": "$message_id",
            "conversation_id": {"$first": "$conversation_id"},
            "user_id": {"$first": "$user_id"},
            "total_cost": {"$sum": "$total_cost"},
            "input_tokens": {"$sum": "$input_tokens"},
            "output_tokens": {"$sum": "$output_tokens"},
            "tool_calls": {"$sum": "$tool_calls"},
            "latency_ms": {"$sum": "$latency_ms"},
            "timestamp": {"$max": "$timestamp"},
        }},
        {"$sort": {"timestamp": -1}},
        {"$limit": limit},
    ]
    out = []
    for d in _col().aggregate(pipeline):
        out.append({
            "message_id": d["_id"] or "—",
            "conversation_id": d.get("conversation_id", "") or "—",
            "user_id": d.get("user_id", "") or "anonymous",
            "total_cost": d.get("total_cost", 0.0) or 0.0,
            "input_tokens": d.get("input_tokens", 0) or 0,
            "output_tokens": d.get("output_tokens", 0) or 0,
            "tool_calls": d.get("tool_calls", 0) or 0,
            "latency_ms": round(d.get("latency_ms", 0.0) or 0.0, 1),
            "timestamp": d.get("timestamp"),
        })
    return out


# ── Time series + breakdowns (charts) ────────────────────────────────────────────
def get_cost_over_time() -> list[dict]:
    pipeline = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "cost": {"$sum": "$total_cost"},
            "tokens": {"$sum": {"$add": ["$input_tokens", "$output_tokens"]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    return [{"date": d["_id"], "cost": d["cost"], "tokens": d["tokens"]}
            for d in _col().aggregate(pipeline)]


def get_token_usage_over_time() -> list[dict]:
    pipeline = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "input_tokens": {"$sum": "$input_tokens"},
            "output_tokens": {"$sum": "$output_tokens"},
            "embedding_tokens": {"$sum": "$embedding_tokens"},
        }},
        {"$sort": {"_id": 1}},
    ]
    return [{"date": d["_id"],
             "input_tokens": d["input_tokens"],
             "output_tokens": d["output_tokens"],
             "embedding_tokens": d["embedding_tokens"]}
            for d in _col().aggregate(pipeline)]


def get_cost_by_provider() -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$provider",
                    "cost": {"$sum": "$total_cost"},
                    "tokens": {"$sum": {"$add": ["$input_tokens", "$output_tokens"]}},
                    "calls": {"$sum": 1}}},
        {"$sort": {"cost": -1}},
    ]
    return [{"provider": d["_id"] or "—", "cost": d["cost"],
             "tokens": d["tokens"], "calls": d["calls"]}
            for d in _col().aggregate(pipeline)]


def get_cost_by_model() -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$model",
                    "cost": {"$sum": "$total_cost"},
                    "tokens": {"$sum": {"$add": ["$input_tokens", "$output_tokens"]}},
                    "calls": {"$sum": 1}}},
        {"$sort": {"cost": -1}},
    ]
    return [{"model": d["_id"] or "—", "cost": d["cost"],
             "tokens": d["tokens"], "calls": d["calls"]}
            for d in _col().aggregate(pipeline)]


def get_latency_over_time() -> list[dict]:
    pipeline = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "avg_latency": {"$avg": "$latency_ms"},
            "max_latency": {"$max": "$latency_ms"},
        }},
        {"$sort": {"_id": 1}},
    ]
    return [{"date": d["_id"],
             "avg_latency": round(d["avg_latency"] or 0.0, 1),
             "max_latency": round(d["max_latency"] or 0.0, 1)}
            for d in _col().aggregate(pipeline)]


def get_recent_usage(limit: int = 1000) -> list[dict]:
    """Raw recent usage rows (newest first) — used by the optimizer."""
    docs = _col().find({}).sort("timestamp", DESCENDING).limit(limit)
    out = []
    for d in docs:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out
