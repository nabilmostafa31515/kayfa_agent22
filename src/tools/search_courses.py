"""Tools: search courses / roadmaps / policies, each from its own KB channel."""

import logging
from langchain.tools import tool
from src.rag.vectorstore import similarity_search

logger = logging.getLogger(__name__)

# KB files backing each tool — retrieval is forced to these channels so every
# tool answers strictly from the file(s) that own that information.
_COURSE_SOURCES = ["kayfa_courses.json", "kayfa_paid_individual_courses.md"]
_ROADMAP_SOURCES = ["kayfa_roadmaps.json", "kayfa_paid_educational_tracks.md"]
_POLICY_SOURCES = ["kayfa_policies_and_faqs.md", "kayfa_privacy_policy.md"]


@tool
def search_courses(query: str) -> str:
    """
    Search Kayfa's course catalog for courses matching the user's query.
    Use this when the user asks about specific courses, topics, or learning paths.
    Returns relevant course details including name, level, duration, and link.
    """
    try:
        docs = similarity_search(query, k=4, sources=_COURSE_SOURCES)
        if not docs:
            return "لم أجد كورساً مطابقاً في قاعدة كيفا."
        return "\n\n---\n\n".join(d.page_content for d in docs)
    except Exception as e:
        logger.error(f"search_courses error: {e}")
        return "لم أتمكن من البحث في قاعدة البيانات حالياً."


@tool
def search_roadmaps(query: str) -> str:
    """
    Search Kayfa's learning roadmaps and tracks for the user's goal.
    Use this when the user asks about career paths, tracks, diplomas, or roadmaps.
    Returns roadmap details including skills, tools, duration, and included courses.
    """
    try:
        docs = similarity_search(query, k=4, sources=_ROADMAP_SOURCES)
        if not docs:
            return "لم أجد مساراً مطابقاً في قاعدة كيفا."
        return "\n\n---\n\n".join(d.page_content for d in docs)
    except Exception as e:
        logger.error(f"search_roadmaps error: {e}")
        return "لم أتمكن من البحث في قاعدة البيانات حالياً."


@tool
def retrieve_policy(query: str) -> str:
    """
    Retrieve Kayfa's policies, FAQs, or privacy policy information.
    Use this when the user asks about refunds, enrollment conditions, certificates, or privacy.
    """
    try:
        docs = similarity_search(query, k=3, sources=_POLICY_SOURCES)
        if not docs:
            return "لم أجد هذه المعلومة في سياسات كيفا."
        return "\n\n---\n\n".join(d.page_content for d in docs)
    except Exception as e:
        logger.error(f"retrieve_policy error: {e}")
        return "لم أتمكن من استرجاع السياسات حالياً."
