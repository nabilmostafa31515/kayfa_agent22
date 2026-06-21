"""CRUD operations for the leads collection."""

import logging
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import DESCENDING
from .mongodb import get_db

logger = logging.getLogger(__name__)


def _db():
    return get_db()["leads"]


# ── CREATE ─────────────────────────────────────────────────────────────────────

def create_lead(
    name: str,
    phone: str,
    email: str,
    language: str,
    interest_area: str,
    recommended_product: str,
    lead_score: float,
    conversation_summary: str,
) -> str:
    """Insert a new lead and return its inserted_id as string."""
    doc = {
        "name": name,
        "phone": phone,
        "email": email,
        "language": language,
        "interest_area": interest_area,
        "recommended_product": recommended_product,
        "lead_score": round(lead_score, 2),
        "conversation_summary": conversation_summary,
        "status": "new",
        "created_at": datetime.now(timezone.utc),
    }
    result = _db().insert_one(doc)
    logger.info(f"Lead created: {result.inserted_id}")
    return str(result.inserted_id)


# ── READ ───────────────────────────────────────────────────────────────────────

def get_all_leads(limit: int = 200) -> list[dict]:
    """Return all leads sorted by newest first."""
    docs = _db().find({}, {"_id": 1, "name": 1, "phone": 1, "email": 1,
                           "language": 1, "interest_area": 1,
                           "recommended_product": 1, "lead_score": 1,
                           "conversation_summary": 1, "status": 1,
                           "created_at": 1}
                      ).sort("created_at", DESCENDING).limit(limit)
    results = []
    for d in docs:
        d["_id"] = str(d["_id"])
        results.append(d)
    return results


def get_lead_by_id(lead_id: str) -> dict | None:
    doc = _db().find_one({"_id": ObjectId(lead_id)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def search_leads(query: str) -> list[dict]:
    """Simple text search on name / email / interest_area."""
    regex = {"$regex": query, "$options": "i"}
    cursor = _db().find(
        {"$or": [{"name": regex}, {"email": regex}, {"interest_area": regex}]}
    ).sort("created_at", DESCENDING)
    results = []
    for d in cursor:
        d["_id"] = str(d["_id"])
        results.append(d)
    return results


# ── UPDATE ─────────────────────────────────────────────────────────────────────

def update_lead_status(lead_id: str, status: str) -> bool:
    """Update lead status: new | contacted | qualified | converted | lost."""
    result = _db().update_one(
        {"_id": ObjectId(lead_id)},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
    )
    return result.modified_count > 0


def update_lead(lead_id: str, fields: dict) -> bool:
    fields["updated_at"] = datetime.now(timezone.utc)
    result = _db().update_one({"_id": ObjectId(lead_id)}, {"$set": fields})
    return result.modified_count > 0


# ── DELETE ─────────────────────────────────────────────────────────────────────

def delete_lead(lead_id: str) -> bool:
    result = _db().delete_one({"_id": ObjectId(lead_id)})
    return result.deleted_count > 0


# ── ANALYTICS ─────────────────────────────────────────────────────────────────

def get_lead_stats() -> dict:
    """Return aggregated stats for the CRM dashboard."""
    pipeline = [
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "avg_score": {"$avg": "$lead_score"},
            "qualified": {"$sum": {"$cond": [{"$gte": ["$lead_score", 0.6]}, 1, 0]}},
        }}
    ]
    result = list(_db().aggregate(pipeline))
    base = result[0] if result else {"total": 0, "avg_score": 0, "qualified": 0}

    # top interest area
    top_pipeline = [
        {"$group": {"_id": "$interest_area", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 1},
    ]
    top = list(_db().aggregate(top_pipeline))
    base["top_interest"] = top[0]["_id"] if top else "—"
    base.pop("_id", None)
    return base


def get_leads_by_interest() -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$interest_area", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    return [{"interest_area": d["_id"], "count": d["count"]}
            for d in _db().aggregate(pipeline)]


def get_leads_by_status() -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    return [{"status": d["_id"], "count": d["count"]}
            for d in _db().aggregate(pipeline)]


def get_leads_by_language() -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$language", "count": {"$sum": 1}}},
    ]
    return [{"language": d["_id"], "count": d["count"]}
            for d in _db().aggregate(pipeline)]


def get_score_distribution() -> list[float]:
    return [d["lead_score"] for d in _db().find({}, {"lead_score": 1, "_id": 0})]


def get_leads_over_time() -> list[dict]:
    """Return daily lead counts for the trend chart."""
    pipeline = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}},
    ]
    return [{"date": d["_id"], "count": d["count"]}
            for d in _db().aggregate(pipeline)]
