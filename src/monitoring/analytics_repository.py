"""Dashboard KPIs + the ``analytics`` snapshot collection.

KPIs are computed live from the data Part 1 already produces (``messages``,
``users``, ``leads``) plus the Part 2 ``usage_logs``/``behavior_logs``. A
snapshot of the current KPIs can be saved to ``analytics`` so the team can track
how the headline numbers move over time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo import DESCENDING

from src.database.mongodb import get_db
from . import usage_repository as usage

logger = logging.getLogger(__name__)


def _db():
    return get_db()


def _count(collection: str) -> int:
    try:
        return _db()[collection].count_documents({})
    except Exception:
        return 0


def _distinct_count(collection: str, field: str) -> int:
    try:
        vals = _db()[collection].distinct(field, {field: {"$nin": ["", None]}})
        return len(vals)
    except Exception:
        return 0


def get_dashboard_kpis() -> dict:
    """Headline KPIs for the Monitoring Home page.

    Total Users · Total Conversations · Total Messages · Total Cost ·
    Avg Cost / Conversation · Avg Latency · Total Tool Calls.
    """
    totals = usage.get_totals()

    # Total users: registered accounts (Part 1 `users`), falling back to distinct
    # users seen in usage logs if the users collection is empty.
    total_users = _count("users") or totals.get("users", 0)

    # Conversations / messages: prefer the rich behaviour logs, fall back to the
    # Part 1 `messages` collection so the number is meaningful even before any
    # monitored turns exist.
    total_conversations = (
        _distinct_count("behavior_logs", "conversation_id")
        or _distinct_count("messages", "conversation_id")
        or totals.get("conversations", 0)
    )
    total_messages = _count("messages") or _count("behavior_logs")

    conv_for_avg = totals.get("conversations", 0) or total_conversations
    avg_cost_per_conversation = (
        totals["total_cost"] / conv_for_avg if conv_for_avg else 0.0
    )

    return {
        "total_users": total_users,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "total_cost": totals["total_cost"],
        "avg_cost_per_conversation": avg_cost_per_conversation,
        "avg_latency": totals["avg_latency"],
        "total_tool_calls": totals["tool_calls"],
        # Useful extras surfaced on the home page.
        "total_tokens": totals["total_tokens"],
        "llm_calls": totals["llm_calls"],
        "chat_cost": totals["chat_cost"],
        "embedding_cost": totals["embedding_cost"],
    }


# ── Snapshots (the `analytics` collection) ───────────────────────────────────────
def save_snapshot() -> str | None:
    """Persist the current KPIs as a dated snapshot."""
    try:
        kpis = get_dashboard_kpis()
        kpis["created_at"] = datetime.now(timezone.utc)
        result = _db()["analytics"].insert_one(kpis)
        return str(result.inserted_id)
    except Exception as e:
        logger.error("save_snapshot failed: %s", e)
        return None


def get_snapshots(limit: int = 100) -> list[dict]:
    try:
        docs = _db()["analytics"].find({}).sort("created_at", DESCENDING).limit(limit)
        out = []
        for d in docs:
            d["_id"] = str(d["_id"])
            out.append(d)
        return out
    except Exception as e:
        logger.error("get_snapshots failed: %s", e)
        return []
