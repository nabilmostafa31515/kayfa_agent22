"""Per-file FAISS indexes ("channels") + query routing.

Instead of one global index where chunks from every KB file are mixed together
(and unrelated files can bleed into an answer), we build a *separate* FAISS
index per source file — one "channel" each:

    kayfa_ai_diploma.md   ->  channel "kayfa_ai_diploma_md"
    kayfa_courses.json    ->  channel "kayfa_courses_json"
    ... (one per KB file)

On a query we first ROUTE: score the query against every channel and keep only
the most relevant file(s), then retrieve chunks from those channels only. This
keeps answers tightly grounded in the right file and avoids cross-file noise.
"""

import logging
import re
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from .loader import load_all_documents
from .chunker import chunk_documents
from .embeddings import get_embeddings
from .aliases import expand_query

logger = logging.getLogger(__name__)

# vectorstore.py lives at kayfa_agent/src/rag/vectorstore.py →
# parents[2] = kayfa_agent (project root). Each channel is a sub-folder here.
FAISS_ROOT = Path(__file__).resolve().parents[2] / "faiss_index"

# How many files (channels) a single query may pull from. 2 keeps answers
# grounded in the most relevant file(s) while allowing a closely-related file
# (e.g. a diploma page + the policies page) to contribute.
DEFAULT_CHANNELS = 2

_channels: dict[str, FAISS] | None = None


def channel_key(source: str) -> str:
    """Filesystem-safe channel id derived from a source filename.

    e.g. "kayfa_ai_diploma.md" -> "kayfa_ai_diploma_md". This is both the dict
    key and the on-disk folder name, so build/load/lookup all agree.
    """
    return re.sub(r"[^0-9A-Za-z]+", "_", source).strip("_").lower()


# ── Build / load ────────────────────────────────────────────────────────────────

def build_channels(force_rebuild: bool = False) -> dict[str, FAISS]:
    """Return {channel_key: FAISS}. Loads per-channel indexes from disk when
    present, otherwise builds one index per KB source file and persists each."""
    global _channels

    if _channels is not None and not force_rebuild:
        return _channels

    embeddings = get_embeddings()

    # Load from disk: each sub-folder of FAISS_ROOT is one channel.
    if FAISS_ROOT.exists() and not force_rebuild:
        loaded: dict[str, FAISS] = {}
        for sub in FAISS_ROOT.iterdir():
            if not sub.is_dir():
                continue
            try:
                loaded[sub.name] = FAISS.load_local(
                    str(sub), embeddings, allow_dangerous_deserialization=True
                )
            except Exception as e:
                logger.error(f"Failed to load channel {sub.name}: {e}")
        if loaded:
            logger.info(f"Loaded {len(loaded)} retrieval channels from disk")
            _channels = loaded
            return _channels

    # Build from scratch: group docs by source file, then index each group.
    logger.info("Building per-file retrieval channels from scratch…")
    raw_docs = load_all_documents()

    by_source: dict[str, list[Document]] = {}
    for d in raw_docs:
        by_source.setdefault(d.metadata.get("source", "unknown"), []).append(d)

    channels: dict[str, FAISS] = {}
    for source, docs in by_source.items():
        key = channel_key(source)
        chunks = chunk_documents(docs)
        if not chunks:
            continue
        index = FAISS.from_documents(chunks, embeddings)
        index.save_local(str(FAISS_ROOT / key))
        channels[key] = index
        logger.info(f"Channel '{key}' ({source}): {len(chunks)} chunks")

    logger.info(f"Built {len(channels)} retrieval channels")
    _channels = channels
    return _channels


# ── Routing ─────────────────────────────────────────────────────────────────────

def route(query: str, n_channels: int = DEFAULT_CHANNELS) -> list[str]:
    """Return the channel keys most relevant to the query, best first.

    Scores the query against every channel (best single-chunk distance, lower =
    closer with the normalized embeddings) and keeps the top `n_channels`.
    """
    channels = build_channels()
    # Embed once and route by vector — embedding on CPU is the slow part, so we
    # never re-embed per channel.
    emb = get_embeddings().embed_query(expand_query(query))
    return _route_by_vector(emb, channels, n_channels)


def _route_by_vector(emb, channels: dict[str, FAISS], n_channels: int) -> list[str]:
    """Rank channels by their best match to a pre-computed query embedding."""
    scored: list[tuple[str, float]] = []
    for key, index in channels.items():
        try:
            hits = index.similarity_search_with_score_by_vector(emb, k=1)
        except Exception as e:
            logger.error(f"Routing scan failed for channel {key}: {e}")
            continue
        if hits:
            scored.append((key, hits[0][1]))
    scored.sort(key=lambda kv: kv[1])
    chosen = [key for key, _ in scored[:n_channels]]
    if chosen:
        logger.info(f"Routed query to channels: {chosen}")
    return chosen


# ── Search ──────────────────────────────────────────────────────────────────────

def similarity_search(
    query: str,
    k: int = 5,
    n_channels: int = DEFAULT_CHANNELS,
    sources: list[str] | None = None,
) -> list[Document]:
    """Retrieve the top-k chunks for `query`.

    By default the query is routed to the most relevant file(s) and chunks are
    pulled only from those channels. Pass `sources` (KB filenames) to force
    specific channels — used by the topic-specific tools (courses / roadmaps /
    policies) so each tool reads from its own file(s).
    """
    channels = build_channels()
    if not channels:
        return []

    # Embed the (alias-expanded) query ONCE, then reuse the vector for both
    # routing and the per-channel search. Re-embedding per channel made a single
    # message embed the query ~16× on CPU — the main source of slow replies.
    emb = get_embeddings().embed_query(expand_query(query))

    if sources:
        names = [channel_key(s) for s in sources]
        names = [n for n in names if n in channels]
    else:
        names = _route_by_vector(emb, channels, n_channels)

    if not names:  # routing came back empty — fall back to all channels
        names = list(channels.keys())

    hits: list[tuple[Document, float]] = []
    for name in names:
        try:
            hits.extend(channels[name].similarity_search_with_score_by_vector(emb, k=k))
        except Exception as e:
            logger.error(f"Search failed in channel {name}: {e}")

    hits.sort(key=lambda ds: ds[1])
    return [doc for doc, _ in hits[:k]]
