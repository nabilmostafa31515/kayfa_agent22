"""LangChain callback handler for automatic LLM usage logging.

The chat agent uses :class:`TurnRecorder` (richer: it also captures retrieval,
tools and the final answer into ``behavior_logs``). This callback is the
general-purpose hook for **any other** LangChain LLM call site — attach it once
and every ``invoke``/``stream`` on that model writes a ``usage_logs`` row with
provider, model, tokens, latency and cost, with no manual logging.

Attach it per call to avoid double-counting the chat path::

    from src.monitoring.callbacks import UsageCallbackHandler
    llm.invoke(messages, config={"callbacks": [
        UsageCallbackHandler(user_id, conversation_id, provider, model)
    ]})
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from src.config import pricing
from src.config.monitoring import get_config
from .models import UsageLog
from . import usage_repository

logger = logging.getLogger(__name__)


class UsageCallbackHandler(BaseCallbackHandler):
    """Writes one ``usage_logs`` row per completed LLM call."""

    def __init__(
        self,
        user_id: str = "",
        conversation_id: str = "",
        provider: str = "",
        model: str = "",
        message_id: str | None = None,
    ):
        self.user_id = user_id or ""
        self.conversation_id = conversation_id or ""
        self.provider = provider or ""
        self.model = model or ""
        self.message_id = message_id or uuid.uuid4().hex
        self._index = 0
        self._starts: dict[str, float] = {}

    # ── lifecycle ─────────────────────────────────────────────────────────────────
    def on_llm_start(self, serialized, prompts, *, run_id=None, **kwargs: Any) -> None:
        self._starts[str(run_id)] = time.perf_counter()

    def on_chat_model_start(self, serialized, messages, *, run_id=None, **kwargs: Any) -> None:
        self._starts[str(run_id)] = time.perf_counter()

    def on_llm_end(self, response, *, run_id=None, **kwargs: Any) -> None:
        try:
            start = self._starts.pop(str(run_id), None)
            latency_ms = round((time.perf_counter() - start) * 1000.0, 1) if start else 0.0
            in_tok, out_tok = self._extract_tokens(response)
            model = self._extract_model(response) or self.model
            c_cost = pricing.chat_cost(model, in_tok, out_tok)
            cfg = get_config()
            usage_repository.record_usage(UsageLog(
                message_id=self.message_id,
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                provider=self.provider,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                embedding_provider=cfg.embedding_provider,
                embedding_model=cfg.embedding_model,
                latency_ms=latency_ms,
                llm_call_index=self._index,
                chat_cost=round(c_cost, 8),
                calculated_cost=round(c_cost, 8),
                total_cost=round(c_cost, 8),
            ))
            self._index += 1
        except Exception as e:
            logger.error("UsageCallbackHandler.on_llm_end failed: %s", e)

    # ── helpers ───────────────────────────────────────────────────────────────────
    @staticmethod
    def _extract_tokens(response) -> tuple[int, int]:
        # LangChain surfaces usage in a few shapes depending on provider.
        try:
            out = response.llm_output or {}
            tu = out.get("token_usage") or out.get("usage") or {}
            if tu:
                return (int(tu.get("prompt_tokens", 0) or 0),
                        int(tu.get("completion_tokens", 0) or 0))
        except Exception:
            pass
        try:
            for gens in response.generations:
                for gen in gens:
                    msg = getattr(gen, "message", None)
                    um = getattr(msg, "usage_metadata", None) if msg else None
                    if um:
                        return (int(um.get("input_tokens", 0) or 0),
                                int(um.get("output_tokens", 0) or 0))
        except Exception:
            pass
        return (0, 0)

    @staticmethod
    def _extract_model(response) -> str:
        try:
            out = response.llm_output or {}
            return out.get("model_name") or out.get("model") or ""
        except Exception:
            return ""
