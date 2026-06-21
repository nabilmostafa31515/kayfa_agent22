"""Build and persist the FAISS vector store from all KB documents."""

import logging
from pathlib import Path
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from .loader import load_all_documents
from .chunker import chunk_documents
from .embeddings import get_embeddings

logger = logging.getLogger(__name__)

# vectorstore.py lives at kayfa_agent/src/rag/vectorstore.py →
# parents[2] = kayfa_agent (project root)
FAISS_PATH = Path(__file__).resolve().parents[2] / "faiss_index"

_vectorstore: FAISS | None = None


def build_vectorstore(force_rebuild: bool = False) -> FAISS:
    """Build FAISS index from KB docs. Loads from disk if already built."""
    global _vectorstore

    if _vectorstore is not None and not force_rebuild:
        return _vectorstore

    embeddings = get_embeddings()

    if FAISS_PATH.exists() and not force_rebuild:
        logger.info("Loading FAISS index from disk…")
        _vectorstore = FAISS.load_local(
            str(FAISS_PATH), embeddings, allow_dangerous_deserialization=True
        )
        logger.info("FAISS index loaded from disk")
        return _vectorstore

    logger.info("Building FAISS index from scratch…")
    raw_docs = load_all_documents()
    chunks = chunk_documents(raw_docs)
    logger.info(f"Total chunks: {len(chunks)}")

    _vectorstore = FAISS.from_documents(chunks, embeddings)
    FAISS_PATH.mkdir(parents=True, exist_ok=True)
    _vectorstore.save_local(str(FAISS_PATH))
    logger.info(f"FAISS index saved to {FAISS_PATH}")
    return _vectorstore


def get_retriever(k: int = 5):
    """Return a LangChain retriever from the vector store."""
    vs = build_vectorstore()
    return vs.as_retriever(search_kwargs={"k": k})


def similarity_search(query: str, k: int = 5) -> list[Document]:
    vs = build_vectorstore()
    return vs.similarity_search(query, k=k)
