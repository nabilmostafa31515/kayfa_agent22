"""Per-request runtime context.

Carries the current end-user id into code paths that can't take it as an
argument — notably the LangChain `save_lead` tool, whose arguments are filled by
the LLM. The chat layer sets it before running the agent; create_lead reads it so
every captured lead is stamped with the user who was chatting.

Implemented with a contextvar so concurrent Streamlit sessions don't leak ids
into each other.
"""

import contextvars

_current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "kayfa_current_user_id", default=""
)


def set_current_user_id(user_id: str) -> None:
    _current_user_id.set(user_id or "")


def get_current_user_id() -> str:
    return _current_user_id.get()
