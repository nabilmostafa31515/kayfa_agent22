"""Token counting helpers.

Authoritative chat token counts come from the provider's streamed
``usage_metadata`` (captured in the recorder). This module is for the cases
where the provider does NOT report usage — chiefly the **local embedding model**,
whose token count we must estimate ourselves to price/track it.

Uses ``tiktoken`` (already a project dependency) when available, with a
character-based fallback tuned to behave reasonably on mixed Arabic/English text.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:  # tiktoken is in requirements; degrade gracefully if it ever isn't present
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception as e:  # pragma: no cover - environment dependent
    _ENC = None
    logger.warning("tiktoken unavailable, using heuristic token counting: %s", e)


def count_tokens(text: str) -> int:
    """Estimate the number of tokens in ``text``.

    tiktoken's cl100k encoding is a good proxy across providers; the fallback
    (~4 characters per token) keeps counts sane when it's missing.
    """
    if not text:
        return 0
    if _ENC is not None:
        try:
            return len(_ENC.encode(text))
        except Exception:
            pass
    return max(1, len(text) // 4)


def count_message_tokens(texts: list[str]) -> int:
    """Sum estimated tokens across a list of strings (e.g. a prompt's parts)."""
    return sum(count_tokens(t) for t in texts if t)
