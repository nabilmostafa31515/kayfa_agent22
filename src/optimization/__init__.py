"""Optimization module (Part 2).

Analyses the collected ``usage_logs`` / ``behavior_logs`` to detect expensive
behaviours and emit concrete, costed recommendations (current cost → suggested
improvement → estimated savings). Reports persist to ``optimization_reports`` so
the Before-vs-After page can compare runs over time.
"""

from .analyzer import analyze, OptimizationReport, OptimizationRecommendation  # noqa: F401
