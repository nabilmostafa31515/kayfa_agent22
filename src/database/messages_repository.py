"""Persistence for chat messages, stamped with the end-user's id.

Every user and assistant turn is stored in the `messages` collection keyed by
`user_id` (and grouped by `conversation_id`), so a user's conversation history is
attributable and queryable later (analytics, behavior traces, support).
"""

import logging
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING

from .mongodb import get_db

logger = logging.getLogger(__name__)

_indexed = False


def _messages():
    return get_db()["messages"]


def _ensure_indexes() -> None:
    global _indexed
    if _indexed:
        return
    try:
        _messages().create_index(
            [("user_id", ASCENDING), ("conversation_id", ASCENDING), ("created_at", ASCENDING)],
            name="user_convo_time",
        )
    except Exception as e:
        logger.warning(f"Could not ensure messages index: {e}")
    _indexed = True


def save_message(user_id: str, role: str, content: str, conversation_id: str = "") -> str | None:
    """Persist one chat turn. Best-effort: logs and returns None on failure so a
    DB hiccup never breaks the live chat."""
    try:
        _ensure_indexes()
        result = _messages().insert_one({
            "user_id": user_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": datetime.now(timezone.utc),
        })
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"save_message failed: {e}")
        return None


def get_user_messages(user_id: str, limit: int = 200) -> list[dict]:
    """Return a user's messages, newest first (for history / analytics)."""
    docs = _messages().find({"user_id": user_id}).sort("created_at", DESCENDING).limit(limit)
    out = []
    for d in docs:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out
