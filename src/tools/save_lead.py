"""Tool: save and retrieve CRM leads from MongoDB."""

import logging
from langchain.tools import tool
from src.database.crm_repository import (
    create_lead, get_lead_by_id, update_lead_status
)

logger = logging.getLogger(__name__)


@tool
def save_lead(
    name: str,
    phone: str,
    email: str,
    language: str,
    interest_area: str,
    recommended_product: str,
    lead_score: float,
    conversation_summary: str,
) -> str:
    """
    Save a qualified lead to the CRM (MongoDB Atlas).
    Use this when the user has shown strong purchase intent:
    asked about pricing, enrollment, diploma details, or requested contact.
    lead_score should be between 0.0 and 1.0.
    Returns the created lead ID on success.
    """
    try:
        lead_id = create_lead(
            name=name,
            phone=phone,
            email=email,
            language=language,
            interest_area=interest_area,
            recommended_product=recommended_product,
            lead_score=lead_score,
            conversation_summary=conversation_summary,
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
