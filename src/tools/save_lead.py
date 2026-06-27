"""Tool: save and retrieve CRM leads from MongoDB."""

import logging
from langchain.tools import tool
from src.database.crm_repository import (
    create_lead, get_lead_by_id, update_lead_status
)
from src.runtime_context import get_current_user_id

logger = logging.getLogger(__name__)


@tool
def save_lead(
    name: str,
    phone: str,
    email: str,
    language: str = "arabic",
    interest_area: str = "",
    recommended_product: str = "",
    lead_score: float = 0.0,
    conversation_summary: str = "",
    location: str = "",
    dialect: str = "",
    contact_channel: str = "",
    best_contact_time: str = "",
    products_of_interest: str = "",
    goal: str = "",
    current_level: str = "",
    prerequisites: str = "",
    temperature: str = "",
    buying_signals: str = "",
    budget_sensitivity: str = "",
    objections: str = "",
    next_action: str = "",
) -> str:
    """
    Save a qualified lead / sales ticket to the CRM (MongoDB Atlas).
    Use this when the user has shown strong purchase intent: asked about
    pricing, enrollment, diploma details, or requested contact.

    Fill in as many fields as the conversation revealed — leave the rest blank.
    A great ticket captures:
      WHO          — name, phone (WhatsApp), email, location (city/country),
                     language, dialect (e.g. مصري/خليجي/شامي), contact_channel
                     (whatsapp|phone|email), best_contact_time.
      WHAT THEY WANT — interest_area, products_of_interest (specific courses/
                     tracks/diplomas, comma-separated), recommended_product,
                     goal (their motivation), current_level (beginner|
                     intermediate|advanced), prerequisites discussed.
      HOW LIKELY   — lead_score (0.0–1.0), temperature (hot|warm|cold),
                     buying_signals (comma-separated), budget_sensitivity
                     (low|medium|high), objections raised.
      WHAT HAPPENED — conversation_summary (a SHORT summary IN ARABIC),
                     next_action (the recommended next step for the rep).

    Returns the created lead ID on success.
    """
    try:
        lead_id = create_lead(
            user_id=get_current_user_id(),
            name=name,
            phone=phone,
            email=email,
            language=language,
            interest_area=interest_area,
            recommended_product=recommended_product,
            lead_score=lead_score,
            conversation_summary=conversation_summary,
            location=location,
            dialect=dialect,
            contact_channel=contact_channel,
            best_contact_time=best_contact_time,
            products_of_interest=products_of_interest,
            goal=goal,
            current_level=current_level,
            prerequisites=prerequisites,
            temperature=temperature,
            buying_signals=buying_signals,
            budget_sensitivity=budget_sensitivity,
            objections=objections,
            next_action=next_action,
        )
        logger.info(f"Lead saved: {lead_id}")
        return f"تم حفظ بياناتك بنجاح! رقم المرجع: {lead_id}"
    except Exception as e:
        logger.error(f"save_lead error: {e}")
        return "حدث خطأ أثناء حفظ البيانات. يرجى المحاولة مرة أخرى."


@tool
def get_lead(lead_id: str) -> str:
    """Retrieve a lead from CRM by its ID."""
    try:
        lead = get_lead_by_id(lead_id)
        if not lead:
            return "لم يتم العثور على هذا العميل."
        return str(lead)
    except Exception as e:
        logger.error(f"get_lead error: {e}")
        return "حدث خطأ أثناء استرجاع البيانات."


@tool
def update_lead(lead_id: str, status: str) -> str:
    """
    Update a lead's status in the CRM.
    Valid statuses: new, contacted, qualified, converted, lost
    """
    try:
        success = update_lead_status(lead_id, status)
        if success:
            return f"تم تحديث حالة العميل إلى: {status}"
        return "لم يتم العثور على العميل أو لم يتم تحديثه."
    except Exception as e:
        logger.error(f"update_lead error: {e}")
        return "حدث خطأ أثناء التحديث."
