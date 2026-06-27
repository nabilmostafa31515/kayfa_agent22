"""Monitoring layer (Part 2): automatic usage logging + behaviour tracing.

Public surface:
    TurnRecorder            — instrument one agent turn (used by sales_agent)
    UsageCallbackHandler    — LangChain callback (defense-in-depth LLM capture)
    models                  — Pydantic schemas for usage logs & behaviour traces
    usage_repository        — persist/aggregate `usage_logs`
    behavior_repository     — persist/replay `behavior_logs`
    analytics_repository    — cross-collection KPIs + `analytics` snapshots
"""

from .recorder import TurnRecorder  # noqa: F401
