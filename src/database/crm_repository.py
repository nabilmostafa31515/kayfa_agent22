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

def _temperature_from_score(score: float) -> str:
    """hot ≥ 0.6 · warm ≥ 0.35 · cold otherwise (mirrors the chat badges)."""
    if score >= 0.6:
        return "hot"
    if score >= 0.35:
        return "warm"
    return "cold"


def create_lead(
    name: str,
    phone: str,
    email: str,
    language: str = "arabic",
    interest_area: str = "",
    recommended_product: str = "",
    lead_score: float = 0.0,
    conversation_summary: str = "",
    *,
    # ── Attribution ──────────────────────────────────────────────────────────
    user_id: str = "",
    # ── Who ──────────────────────────────────────────────────────────────────
    whatsapp: str = "",
    location: str = "",
    dialect: str = "",
    contact_channel: str = "",
    best_contact_time: str = "",
    # ── What they want ───────────────────────────────────────────────────────
    products_of_interest: list[str] | str | None = None,
    goal: str = "",
    current_level: str = "",
    prerequisites: str = "",
    # ── How likely ───────────────────────────────────────────────────────────
    temperature: str = "",
    buying_signals: list[str] | str | None = None,
    budget_sensitivity: str = "",
    objections: str = "",
    # ── What happened ────────────────────────────────────────────────────────
    next_action: str = "",
    status: str = "new",
) -> str:
    """Insert a new lead/ticket and return its inserted_id as string.

    Only name/phone/email are truly required; every other field of the "good
    ticket" is optional so partial captures still persist. ``temperature`` is
    derived from ``lead_score`` when not provided. List-typed fields accept a
    comma-joined string too (the agent often passes one)."""

    def _as_list(v):
        if v is None:
            return []
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return list(v)

    doc = {
        # Attribution — the signed-in user this lead came from ("" if anonymous)
        "user_id": user_id,
        # Who
        "name": name,
        "phone": phone,
        "whatsapp": whatsapp or phone,
        "email": email,
        "location": location,
        "language": language,
        "dialect": dialect,
        "contact_channel": contact_channel,
        "best_contact_time": best_contact_time,
        # What they want
        "interest_area": interest_area,
        "products_of_interest": _as_list(products_of_interest),
        "recommended_product": recommended_product,
        "goal": goal,
        "current_level": current_level,
        "prerequisites": prerequisites,
        # How likely
        "lead_score": round(lead_score, 2),
        "temperature": temperature or _temperature_from_score(lead_score),
        "buying_signals": _as_list(buying_signals),
        "budget_sensitivity": budget_sensitivity,
        "objections": objections,
        # What happened
        "conversation_summary": conversation_summary,
        "next_action": next_action,
        "status": status,
        "created_at": datetime.now(timezone.utc),
    }
    result = _db().insert_one(doc)
    logger.info(f"Lead created: {result.inserted_id} ({doc['temperature']})")
    return str(result.inserted_id)


# ── READ ───────────────────────────────────────────────────────────────────────

def get_all_leads(limit: int = 200) -> list[dict]:
    """Return all leads (full ticket) sorted by newest first."""
    docs = _db().find({}).sort("created_at", DESCENDING).limit(limit)
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


def get_leads_by_temperature() -> list[dict]:
    """Count leads by hot / warm / cold. Falls back to deriving the label from
    lead_score for legacy leads saved before the field existed."""
    pipeline = [
        {"$group": {
            "_id": {"$ifNull": ["$temperature", {
                "$switch": {
                    "branches": [
                        {"case": {"$gte": ["$lead_score", 0.6]}, "then": "hot"},
                        {"case": {"$gte": ["$lead_score", 0.35]}, "then": "warm"},
                    ],
                    "default": "cold",
                }
            }]},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    return [{"temperature": d["_id"], "count": d["count"]}
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


# ── PERFORMANCE / IMPROVEMENT ──────────────────────────────────────────────────
# Powers the manager's "monitor improvement" dashboard.

# new → contacted → qualified → converted (lost sits outside the funnel).
FUNNEL_STAGES = ["new", "contacted", "qualified", "converted"]


def get_conversion_funnel() -> list[dict]:
    """Counts per pipeline stage in funnel order, padding missing stages with 0.

    Funnel semantics: each stage counts leads that reached *at least* that stage,
    so the bars are monotonically non-increasing. We derive reached-counts from
    the raw per-status tallies (a 'converted' lead has also been 'qualified',
    'contacted' and 'new')."""
    by_status = {d["status"]: d["count"] for d in get_leads_by_status()}
    # raw count currently sitting in each status (lost excluded from the funnel)
    raw = {s: by_status.get(s, 0) for s in FUNNEL_STAGES}
    reached, running = {}, 0
    # walk from the deepest stage up, accumulating everyone who got that far
    for stage in reversed(FUNNEL_STAGES):
        running += raw[stage]
        reached[stage] = running
    return [{"stage": s, "count": reached[s]} for s in FUNNEL_STAGES]


def get_conversion_summary() -> dict:
    """Overall funnel headline numbers used for KPI cards."""
    by_status = {d["status"]: d["count"] for d in get_leads_by_status()}
    total = sum(by_status.values())
    converted = by_status.get("converted", 0)
    qualified = by_status.get("qualified", 0) + converted
    lost = by_status.get("lost", 0)
    return {
        "total": total,
        "converted": converted,
        "qualified": qualified,
        "lost": lost,
        "conversion_rate": (converted / total) if total else 0.0,
        "qualified_rate": (qualified / total) if total else 0.0,
    }


def get_weekly_performance() -> list[dict]:
    """Per ISO-week metrics for improvement trends (oldest → newest).

    Each row: week ("%G-W%V"), week_start (ISO date of the first lead that
    week), total, avg_score, qualified (score ≥ 0.6) and converted counts."""
    pipeline = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%G-W%V", "date": "$created_at"}},
            "total": {"$sum": 1},
            "avg_score": {"$avg": "$lead_score"},
            "qualified": {"$sum": {"$cond": [{"$gte": ["$lead_score", 0.6]}, 1, 0]}},
            "converted": {"$sum": {"$cond": [{"$eq": ["$status", "converted"]}, 1, 0]}},
            "week_start": {"$min": "$created_at"},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = []
    for d in _db().aggregate(pipeline):
        total = d["total"] or 0
        converted = d.get("converted", 0)
        rows.append({
            "week": d["_id"],
            "week_start": d.get("week_start"),
            "total": total,
            "avg_score": round(d.get("avg_score") or 0.0, 3),
            "qualified": d.get("qualified", 0),
            "converted": converted,
            "conversion_rate": round((converted / total), 3) if total else 0.0,
        })
    return rows
