"""Persistence for the ``optimization_reports`` collection.

Saved reports let the Before-vs-After page compare optimization runs over time
(e.g. a baseline before applying recommendations vs. a later run after).
"""

from __future__ import annotations

import logging

from pymongo import DESCENDING

from src.database.mongodb import get_db
from .analyzer import OptimizationReport

logger = logging.getLogger(__name__)


def _col():
    return get_db()["optimization_reports"]


def save_report(report: OptimizationReport, label: str = "") -> str | None:
    try:
        doc = report.to_doc()
        doc["label"] = label or report.generated_at.strftime("%Y-%m-%d %H:%M")
        result = _col().insert_one(doc)
        return str(result.inserted_id)
    except Exception as e:
        logger.error("save_report failed: %s", e)
        return None


def list_reports(limit: int = 50) -> list[dict]:
    try:
        docs = _col().find({}).sort("generated_at", DESCENDING).limit(limit)
        out = []
        for d in docs:
            d["_id"] = str(d["_id"])
            out.append(d)
        return out
    except Exception as e:
        logger.error("list_reports failed: %s", e)
        return []


def get_report(report_id: str) -> dict | None:
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        d = _col().find_one({"_id": ObjectId(report_id)})
    except (InvalidId, TypeError):
        return None
    if d:
        d["_id"] = str(d["_id"])
    return d
