"""Tool: search courses and roadmaps from the vector store."""

import logging
from langchain.tools import tool
from src.rag.vectorstore import similarity_search

logger = logging.getLogger(__name__)


@tool
def search_courses(query: str) -> str:
    """
    Search Kayfa's course catalog for courses matching the user's query.
    Use this when the user asks about specific courses, topics, or learning paths.
    Returns relevant course details including name, level, duration, and link.
    """
    try:
        docs = similarity_search(query, k=4)
        course_docs = [d for d in docs if d.metadata.get("type") == "course"]
        if not course_docs:
            course_docs = docs[:3]
        return "\n\n---\n\n".join(d.page_content for d in course_docs)
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
        docs = similarity_search(query, k=4)
        roadmap_docs = [d for d in docs if d.metadata.get("type") in ("roadmap", "markdown")]
        if not roadmap_docs:
            roadmap_docs = docs[:3]
        return "\n\n---\n\n".join(d.page_content for d in roadmap_docs)
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
        docs = similarity_search(query, k=3)
        policy_docs = [d for d in docs if "polic" in d.metadata.get("source", "").lower()
                       or "faq" in d.metadata.get("source", "").lower()]
        if not policy_docs:
            policy_docs = docs[:2]
        return "\n\n---\n\n".join(d.page_content for d in policy_docs)
    except Exception as e:
        logger.error(f"retrieve_policy error: {e}")
        return "لم أتمكن من استرجاع السياسات حالياً."
