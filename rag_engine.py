"""
rag_engine.py — VaultMind v1.2
Real semantic RAG using sentence-transformers + numpy cosine similarity.

UPGRADE from v0.6:
  Before: TF-IDF keyword overlap — "exit" never finds "termination"
  After:  Semantic embeddings — "exit" finds "termination", "cessation", "end of agreement"

Model: all-MiniLM-L6-v2
  - 80 MB download (one time)
  - ~50ms per document index on CPU
  - ~5ms per query on CPU
  - Supports English + Hindi + 50 other languages
  - Runs fine on 8GB RAM

Graceful fallback:
  If sentence-transformers not installed → falls back to keyword TF-IDF (v0.6 behaviour).
  The rest of the app works unchanged. Install with:
    pip install sentence-transformers

Architecture:
  index_document(text) → DocumentIndex (with semantic vectors)
  retrieve(index, query, n) → top N semantically similar chunks
  get_context(index, query) → context string ready for AI prompt
"""

import re
import math
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────

CHUNK_SIZE          = 800    # chars per chunk — slightly larger for semantic model
CHUNK_OVERLAP       = 200    # overlap between chunks
MAX_CHUNKS_PER_QUERY = 5     # chunks sent to AI per question
MAX_CONTEXT_CHARS   = 3200   # total chars sent to AI
SEMANTIC_MODEL      = "all-MiniLM-L6-v2"   # 80MB, multilingual capable, CPU-fast
FALLBACK_MODEL      = "paraphrase-multilingual-MiniLM-L12-v2"  # better Hindi if needed

# ── Semantic model (lazy-loaded) ──────────────────────────────────────────────

_model = None
_model_name_loaded = None
_use_semantic = None   # None = not yet checked


def _get_model():
    """Lazy-load the sentence-transformer model. Only loads once."""
    global _model, _use_semantic, _model_name_loaded
    if _use_semantic is not None:
        return _model

    try:
        from sentence_transformers import SentenceTransformer
        print(f"[RAG] Loading semantic model: {SEMANTIC_MODEL}...")
        _model = SentenceTransformer(SEMANTIC_MODEL)
        _model_name_loaded = SEMANTIC_MODEL
        _use_semantic = True
        print(f"[RAG] Semantic RAG ready — real vector search enabled.")
    except ImportError:
        _use_semantic = False
        print("[RAG] sentence-transformers not installed — using keyword fallback.")
        print("[RAG] For better results: pip install sentence-transformers")
    except Exception as e:
        _use_semantic = False
        print(f"[RAG] Model load failed ({e}) — using keyword fallback.")

    return _model


def is_semantic_available() -> bool:
    """Check whether semantic RAG is available (for status display)."""
    _get_model()
    return _use_semantic is True


# ── Stop words (used by keyword fallback) ─────────────────────────────────────

_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "this", "that", "these",
    "those", "i", "you", "he", "she", "it", "we", "they", "what", "which",
    "who", "when", "where", "why", "how", "all", "any", "both", "each",
    "no", "not", "only", "same", "so", "than", "too", "very", "can",
    "just", "as", "its", "their", "our", "your", "if", "into", "through",
    "before", "after", "above", "below", "between", "out", "over", "under",
    "again", "here", "there", "once", "also", "up", "about", "per", "within"
}


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Chunk:
    id:        int
    text:      str
    page:      Optional[int]
    keywords:  dict              # for fallback scoring
    vector:    Optional[np.ndarray] = None  # semantic embedding


@dataclass
class DocumentIndex:
    chunks:       list            = field(default_factory=list)
    total_pages:  int             = 0
    total_words:  int             = 0
    file_name:    str             = ""
    full_text:    str             = ""
    is_semantic:  bool            = False
    is_ocr:       bool            = False   # flag if text came from OCR


# ── Keyword helpers (fallback) ────────────────────────────────────────────────

def _extract_keywords(text: str) -> dict:
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    freq = {}
    for w in words:
        if w not in _STOP_WORDS:
            freq[w] = freq.get(w, 0) + 1
    return freq


def _is_legal_term(word: str) -> bool:
    legal_terms = {
        "liability", "indemnif", "terminat", "breach", "warrant",
        "confidential", "intellectual", "property", "arbitration",
        "governing", "jurisdiction", "penalty", "damages", "obligation",
        "covenant", "represent", "disclaim", "payment", "clause",
        "agreement", "contract", "party", "parties", "effective",
        "expir", "renew", "notice", "default", "assign", "force",
    }
    return any(word.startswith(t) for t in legal_terms)


def _score_keyword(chunk: Chunk, query_keywords: dict) -> float:
    if not query_keywords or not chunk.keywords:
        return 0.0
    score = 0.0
    chunk_total = sum(chunk.keywords.values()) or 1
    for qword, qfreq in query_keywords.items():
        if qword in chunk.keywords:
            tf    = chunk.keywords[qword] / chunk_total
            boost = 2.0 if _is_legal_term(qword) else 1.0
            score += tf * qfreq * boost
    length_bonus = min(len(chunk.text) / CHUNK_SIZE, 1.0) * 0.1
    return score + length_bonus


# ── Chunking ──────────────────────────────────────────────────────────────────

def _split_into_chunks(text: str) -> list[tuple[str, Optional[int]]]:
    """Split text into overlapping chunks at sentence boundaries."""
    page_pattern  = re.compile(r'\[Page (\d+)\]')
    current_page  = None
    full_clean    = []
    page_map      = []
    pos           = 0

    segments = page_pattern.split(text)
    if len(segments) == 1:
        full_clean = [text]
        page_map   = [(0, None)]
    else:
        i = 0
        while i < len(segments):
            if i % 2 == 0:
                full_clean.append(segments[i])
                page_map.append((pos, current_page))
                pos += len(segments[i])
            else:
                current_page = int(segments[i])
            i += 1

    combined  = "".join(full_clean)
    sentences = re.split(r'(?<=[.!?।])\s+|\n\n', combined)  # ।  = Hindi full stop

    chunks       = []
    current_chunk = []
    current_len  = 0
    char_pos     = 0

    def get_page(p):
        pg = None
        for start, pnum in page_map:
            if start <= p:
                pg = pnum
        return pg

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        if current_len + len(sent) > CHUNK_SIZE and current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append((chunk_text, get_page(char_pos)))

            # Overlap — keep last few sentences
            overlap, overlap_len = [], 0
            for s in reversed(current_chunk):
                if overlap_len + len(s) < CHUNK_OVERLAP:
                    overlap.insert(0, s)
                    overlap_len += len(s)
                else:
                    break
            current_chunk = overlap
            current_len   = overlap_len

        current_chunk.append(sent)
        current_len += len(sent)
        char_pos    += len(sent)

    if current_chunk:
        chunks.append((" ".join(current_chunk), get_page(char_pos)))

    return chunks


# ── Core indexing ─────────────────────────────────────────────────────────────

def index_document(text: str, file_name: str = "", total_pages: int = 0,
                   is_ocr: bool = False) -> DocumentIndex:
    """
    Build a semantic (or keyword fallback) index for a document.

    Call once on upload — store result in _doc_cache in app.py.
    For a 50-page contract: ~2 seconds to index, ~50ms per query.
    """
    model = _get_model()

    raw_chunks = _split_into_chunks(text)
    chunks     = []

    chunk_texts = [ct for ct, _ in raw_chunks if ct.strip()]

    # Batch embed all chunks at once — much faster than one at a time
    vectors = None
    if model is not None and _use_semantic:
        try:
            vectors = model.encode(
                chunk_texts,
                batch_size=32,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,  # L2-normalize for cosine = dot product
            )
        except Exception as e:
            print(f"[RAG] Embedding failed: {e} — falling back to keywords")
            vectors = None

    valid_i = 0
    for i, (chunk_text, page) in enumerate(raw_chunks):
        if not chunk_text.strip():
            continue

        vec = None
        if vectors is not None and valid_i < len(vectors):
            vec = vectors[valid_i]
        valid_i += 1

        chunks.append(Chunk(
            id       = i,
            text     = chunk_text,
            page     = page,
            keywords = _extract_keywords(chunk_text),
            vector   = vec,
        ))

    return DocumentIndex(
        chunks      = chunks,
        total_pages = total_pages,
        total_words = len(text.split()),
        file_name   = file_name,
        full_text   = text,
        is_semantic = (vectors is not None),
        is_ocr      = is_ocr,
    )


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve(index: DocumentIndex, query: str,
             n: int = MAX_CHUNKS_PER_QUERY) -> list[Chunk]:
    """
    Find the N most semantically relevant chunks for a query.

    Semantic mode: embed the query → cosine similarity against all chunks.
    Keyword mode:  TF-IDF keyword overlap scoring (fallback).

    Always ensures first + last chunk are included if < 2 results found
    (parties at start, signatures/dates at end of contracts).
    """
    if not index.chunks:
        return []

    # ── Semantic retrieval ────────────────────────────────────────────────────
    if index.is_semantic and _use_semantic:
        model = _get_model()
        try:
            query_vec = model.encode(
                [query],
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )[0]

            # Dot product of L2-normalised vectors = cosine similarity
            chunk_vecs  = np.array([c.vector for c in index.chunks if c.vector is not None])
            valid_chunks = [c for c in index.chunks if c.vector is not None]

            if len(chunk_vecs) == 0:
                return _keyword_retrieve(index, query, n)

            similarities = chunk_vecs @ query_vec  # shape: (num_chunks,)

            # Hybrid boost: also add keyword score to prevent pure semantic failures
            kw_q = _extract_keywords(query)
            for i, chunk in enumerate(valid_chunks):
                kw_score = _score_keyword(chunk, kw_q) * 0.3  # 30% weight
                similarities[i] += kw_score

            top_indices = np.argsort(similarities)[::-1][:n]
            top_chunks  = [valid_chunks[i] for i in top_indices if similarities[i] > 0.1]

            # Fallback: always include first + last chunk for contract structure
            if len(top_chunks) < 2:
                if index.chunks[0] not in top_chunks:
                    top_chunks.insert(0, index.chunks[0])
                if len(index.chunks) > 1 and index.chunks[-1] not in top_chunks:
                    top_chunks.append(index.chunks[-1])

            return top_chunks[:n]

        except Exception as e:
            print(f"[RAG] Semantic retrieval error: {e} — using keyword fallback")

    # ── Keyword fallback retrieval ────────────────────────────────────────────
    return _keyword_retrieve(index, query, n)


def _keyword_retrieve(index: DocumentIndex, query: str, n: int) -> list[Chunk]:
    """TF-IDF keyword retrieval — original v0.6 behaviour."""
    query_keywords = _extract_keywords(query)
    scored = [(c, _score_keyword(c, query_keywords)) for c in index.chunks]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [c for c, s in scored[:n] if s > 0]

    if len(top) < 2 and index.chunks:
        if index.chunks[0] not in top:
            top.insert(0, index.chunks[0])
        if len(index.chunks) > 1 and index.chunks[-1] not in top:
            top.append(index.chunks[-1])

    return top[:n]


# ── Context builders ──────────────────────────────────────────────────────────

def get_context(index: DocumentIndex, query: str) -> str:
    """
    Build context string for AI prompt.
    Retrieves semantically relevant chunks with page refs.
    """
    chunks = retrieve(index, query)
    if not chunks:
        return index.full_text[:MAX_CONTEXT_CHARS]

    parts = []
    for chunk in chunks:
        page_ref = f"[Page {chunk.page}] " if chunk.page else ""
        parts.append(f"{page_ref}{chunk.text}")

    context = "\n\n---\n\n".join(parts)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n[...truncated]"
    return context


def get_summary_context(index: DocumentIndex) -> str:
    """
    Context for summarisation — samples beginning, middle, and end.
    Gives representative coverage of the whole document.
    """
    chunks = index.chunks
    if not chunks:
        return index.full_text[:MAX_CONTEXT_CHARS]

    n        = len(chunks)
    selected = []

    selected.extend(chunks[:2])

    mid = n // 2
    if mid > 2:
        selected.extend(chunks[max(0, mid - 1):mid + 1])

    if n > 4:
        selected.extend(chunks[-2:])

    seen   = set()
    deduped = []
    for c in selected:
        if c.id not in seen:
            deduped.append(c)
            seen.add(c.id)

    parts   = []
    for chunk in deduped:
        page_ref = f"[Page {chunk.page}] " if chunk.page else ""
        parts.append(f"{page_ref}{chunk.text}")

    context = "\n\n---\n\n".join(parts)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n[...truncated]"
    return context


def get_stats(index: DocumentIndex) -> dict:
    """Return index statistics for display in UI."""
    return {
        "chunks":      len(index.chunks),
        "total_words": index.total_words,
        "total_pages": index.total_pages,
        "file_name":   index.file_name,
        "indexed":     len(index.chunks) > 0,
        "is_semantic": index.is_semantic,
        "is_ocr":      index.is_ocr,
        "rag_mode":    "semantic" if index.is_semantic else "keyword",
    }
