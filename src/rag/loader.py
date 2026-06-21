"""Load all knowledge-base documents into LangChain Document objects."""

import json
import logging
from pathlib import Path
from langchain_core.documents import Document
logger = logging.getLogger(__name__)

# loader.py lives at kayfa_agent/src/rag/loader.py →
# parents[0]=rag  parents[1]=src  parents[2]=kayfa_agent (project root)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_markdown_files() -> list[Document]:
    docs = []
    for md_file in (DATA_DIR / "text").glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        docs.append(Document(
            page_content=text,
            metadata={"source": md_file.name, "type": "markdown"}
        ))
        logger.info(f"Loaded markdown: {md_file.name}")
    return docs


def load_courses_json() -> list[Document]:
    path = DATA_DIR / "json" / "kayfa_courses.json"
    courses = json.loads(path.read_text(encoding="utf-8"))
    docs = []
    for c in courses:
        text = (
            f"Course: {c.get('name','')}\n"
            f"Track: {c.get('track','')}\n"
            f"Level: {c.get('level','')}\n"
            f"Duration: {c.get('duration','')}\n"
            f"Summary: {c.get('summary','')}\n"
            f"Prerequisites: {c.get('prerequisites','')}\n"
            f"Roadmaps: {', '.join(c.get('roadmaps') or [])}\n"
            f"Link: {c.get('link','')}\n"
            f"Provider: {c.get('provider','')} | Host: {c.get('host','')}"
        )
        docs.append(Document(
            page_content=text,
            metadata={"source": "kayfa_courses.json", "type": "course",
                      "name": c.get("name", ""), "track": c.get("track", ""),
                      "level": c.get("level", ""), "link": c.get("link", "")}
        ))
    logger.info(f"Loaded {len(docs)} courses")
    return docs


def load_roadmaps_json() -> list[Document]:
    path = DATA_DIR / "json" / "kayfa_roadmaps.json"
    roadmaps = json.loads(path.read_text(encoding="utf-8"))
    docs = []
    for r in roadmaps:
        text = (
            f"Roadmap: {r.get('name','')}\n"
            f"Track: {r.get('track','')}\n"
            f"Duration: {r.get('duration','')}\n"
            f"Courses Count: {r.get('courses_count','')}\n"
            f"Summary: {r.get('summary','')}\n"
            f"Skills: {', '.join(r.get('skills') or [])}\n"
            f"Tools: {', '.join(r.get('tools') or [])}\n"
            f"Courses: {', '.join(r.get('courses_list') or [])}\n"
            f"Link: {r.get('link','')}\n"
            f"Provider: {r.get('provider','')} | Host: {r.get('host','')}"
        )
        docs.append(Document(
            page_content=text,
            metadata={"source": "kayfa_roadmaps.json", "type": "roadmap",
                      "name": r.get("name", ""), "track": r.get("track", ""),
                      "link": r.get("link", "")}
        ))
    logger.info(f"Loaded {len(docs)} roadmaps")
    return docs


def load_all_documents() -> list[Document]:
    """Return all documents from all knowledge-base sources."""
    docs = []
    docs.extend(load_markdown_files())
    docs.extend(load_courses_json())
    docs.extend(load_roadmaps_json())
    logger.info(f"Total documents loaded: {len(docs)}")
    return docs
