"""Embedding model — uses SentenceTransformers (free, no API key needed)."""

import logging
from langchain_huggingface import HuggingFaceEmbeddings

logger = logging.getLogger(__name__)

# paraphrase-multilingual supports Arabic + English
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_embeddings = None


def get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        logger.info(f"Loading embedding model: {MODEL_NAME}")
        _embeddings = HuggingFaceEmbeddings(
            model_name=MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info("Embedding model ready")
    return _embeddings
