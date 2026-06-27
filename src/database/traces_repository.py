"""Behavior traces — a lightweight event log, stamped with the end-user's id.

Each meaningful action (signup, login, message_sent, lead_captured, …) is recorded
in the `behavior_traces` collection keyed by `user_id` (and `conversation_id` when
relevant), with a free-form `props` dict for event-specific detail. This is the
raw material for funnels / engagement analytics in the manager dashboards.

Common events (not enforced): signup, login, logout, message_sent,
assistant_replied, lead_form_opened, lead_captured.
"""

import logging
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING

from .mongodb import get_db

logger = logging.getLogger(__name__)

_indexed = False


def _traces():
    return get_db()["behavior_traces"]


def _ensure_indexes() -> None:
    global _indexed
    if _indexed:
        return
    try:
        _traces().create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_time")
        _traces().create_index([("event", ASCENDING)], name="event")
    except Exception as e:
        logger.warning(f"Could not ensure traces index: {e}")
    _indexed = True


def record_trace(
    user_id: str,
    event: str,
    conversation_id: str = "",
    props: dict | None = None,
) -> str | None:
    """Persist one behavior event. Best-effort: never breaks the app on failure."""
    try:
        _ensure_indexes()
        doc = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "event": event,
            "props": props or {},
            "created_at": datetime.now(timezone.utc),
        }
        result = _traces().insert_one(doc)
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"record_trace failed ({event}): {e}")
        return None


# ── Aggregations (manager dashboard) ──────────────────────────────────────────
def get_event_counts() -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$event", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    return [{"event": d["_id"] or "—", "count": d["count"]}
            for d in _traces().aggregate(pipeline)]


def get_recent_traces(limit: int = 100) -> list[dict]:
    docs = _traces().find({}).sort("created_at", DESCENDING).limit(limit)
    out = []
    for d in docs:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out


def get_active_users() -> int:
    """Distinct users that produced at least one trace."""
    try:
        return len(_traces().distinct("user_id", {"user_id": {"$nin": ["", None]}}))
    except Exception:
        return 0
