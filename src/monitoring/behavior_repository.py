"""Persistence + replay reads for the ``behavior_logs`` collection.

One document per user message holding the full execution trace. The Behaviour
Trace page lists conversations, then replays a conversation's messages
step-by-step so the admin can audit reasoning, retrieved context, sources, tool
calls and the final response — making hallucinations easy to spot (answer text
that isn't supported by the retrieved context / sources).
"""

from __future__ import annotations

import logging

from pymongo import ASCENDING, DESCENDING

from src.database.mongodb import get_db
from .models import BehaviorTrace

logger = logging.getLogger(__name__)

_indexed = False


def _col():
    return get_db()["behavior_logs"]


def _ensure_indexes() -> None:
    global _indexed
    if _indexed:
        return
    try:
        c = _col()
        c.create_index([("conversation_id", ASCENDING), ("timestamp", ASCENDING)],
                       name="conversation_time")
        c.create_index([("message_id", ASCENDING)], name="message", unique=False)
        c.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)], name="user_time")
    except Exception as e:
        logger.warning("Could not ensure behavior_logs indexes: %s", e)
    _indexed = True


# ── Write ─────────────────────────────────────────────────────────────────────────
def record_trace(trace: BehaviorTrace) -> str | None:
    try:
        _ensure_indexes()
        result = _col().insert_one(trace.to_doc())
        return str(result.inserted_id)
    except Exception as e:
        logger.error("record_trace (behavior) failed: %s", e)
        return None


# ── Reads (replay) ──────────────────────────────────────────────────────────────
def list_conversations(limit: int = 100) -> list[dict]:
    """Conversation summaries, most recently active first."""
    pipeline = [
        {"$group": {
            "_id": "$conversation_id",
            "user_id": {"$first": "$user_id"},
            "messages": {"$sum": 1},
            "tool_calls": {"$sum": {"$size": "$tool_calls"}},
            "total_cost": {"$sum": "$total_cost"},
            "total_tokens": {"$sum": "$total_tokens"},
            "avg_latency": {"$avg": "$total_latency_ms"},
            "last_time": {"$max": "$timestamp"},
            "first_prompt": {"$first": "$user_prompt"},
        }},
        {"$sort": {"last_time": -1}},
        {"$limit": limit},
    ]
    out = []
    for d in _col().aggregate(pipeline):
        out.append({
            "conversation_id": d["_id"] or "—",
            "user_id": d.get("user_id", "") or "anonymous",
            "messages": d.get("messages", 0),
            "tool_calls": d.get("tool_calls", 0),
            "total_cost": d.get("total_cost", 0.0) or 0.0,
            "total_tokens": d.get("total_tokens", 0) or 0,
            "avg_latency": round(d.get("avg_latency", 0.0) or 0.0, 1),
            "last_time": d.get("last_time"),
            "first_prompt": d.get("first_prompt", "") or "",
        })
    return out


def get_conversation_trace(conversation_id: str) -> list[dict]:
    """All message traces in a conversation, in chronological order (replay)."""
    docs = _col().find({"conversation_id": conversation_id}).sort("timestamp", ASCENDING)
    out = []
    for d in docs:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out


def get_trace(message_id: str) -> dict | None:
    d = _col().find_one({"message_id": message_id})
    if d:
        d["_id"] = str(d["_id"])
    return d


def list_recent_traces(limit: int = 200) -> list[dict]:
    docs = _col().find({}).sort("timestamp", DESCENDING).limit(limit)
    out = []
    for d in docs:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out
