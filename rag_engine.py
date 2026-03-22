"""
rag_engine.py — VaultMind v0.6
Keyword-based RAG (Retrieval Augmented Generation).
No vectors, no embeddings, no database — pure Python.
Works on 8GB RAM with any document size.

Flow:
  1. index_document(text) — split into chunks, build keyword index
  2. retrieve(query, n)   — find top N most relevant chunks
  3. get_context(query)   — return ready-to-use context string for AI
"""

import re
import math
from dataclasses import dataclass, field
from typing import Optional


# ── Config ────────────────────────────────────────────────────────────────────
CHUNK_SIZE    = 600    # chars per chunk — fits comfortably in phi3.5 context
CHUNK_OVERLAP = 150   # overlap between chunks — prevents cutting mid-sentence
MAX_CHUNKS_PER_QUERY = 4   # chunks sent to AI per question
MAX_CONTEXT_CHARS    = 2400 # total chars sent to AI (MAX_CHUNKS * ~600)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Chunk:
    id:       int
    text:     str
    page:     Optional[int]    # page number if known
    keywords: dict[str, int]   # word → frequency


@dataclass
class DocumentIndex:
    chunks:      list[Chunk]   = field(default_factory=list)
    total_pages: int           = 0
    total_words: int           = 0
    file_name:   str           = ""
    full_text:   str           = ""   # kept for legal pattern extraction


# ── Stop words (don't use these for matching) ─────────────────────────────────
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "this", "that", "these",
    "those", "i", "you", "he", "she", "it", "we", "they", "what", "which",
    "who", "whom", "when", "where", "why", "how", "all", "any", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "not",
    "only", "same", "so", "than", "too", "very", "can", "just", "as",
    "its", "their", "our", "your", "his", "her", "my", "if", "then",
    "than", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "again", "further",
    "here", "there", "once", "also", "up", "about", "per", "within"
}


# ── Keyword extraction ────────────────────────────────────────────────────────

def _extract_keywords(text: str) -> dict[str, int]:
    """Extract meaningful keywords and their frequencies from text."""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    freq = {}
    for w in words:
        if w not in _STOP_WORDS:
            freq[w] = freq.get(w, 0) + 1
    return freq


def _score_chunk(chunk: Chunk, query_keywords: dict[str, int]) -> float:
    """
    Score a chunk against query keywords using TF-IDF inspired scoring.
    Higher score = more relevant to the query.
    """
    if not query_keywords or not chunk.keywords:
        return 0.0

    score = 0.0
    chunk_total = sum(chunk.keywords.values()) or 1

    for qword, qfreq in query_keywords.items():
        if qword in chunk.keywords:
            # Term frequency in chunk
            tf = chunk.keywords[qword] / chunk_total
            # Boost for exact matches and legal terms
            boost = 2.0 if _is_legal_term(qword) else 1.0
            score += tf * qfreq * boost

    # Small bonus for longer chunks (more content = more useful)
    length_bonus = min(len(chunk.text) / CHUNK_SIZE, 1.0) * 0.1
    return score + length_bonus


def _is_legal_term(word: str) -> bool:
    """Identify high-value legal terms for scoring boost."""
    legal_terms = {
        "liability", "indemnif", "terminat", "breach", "warrant",
        "confidential", "intellectual", "property", "arbitration",
        "governing", "jurisdiction", "penalty", "damages", "obligation",
        "covenant", "represent", "disclaim", "indemn", "payment",
        "clause", "agreement", "contract", "party", "parties",
        "effective", "expir", "renew", "notice", "default"
    }
    return any(word.startswith(t) for t in legal_terms)


# ── Chunking ──────────────────────────────────────────────────────────────────

def _split_into_chunks(text: str) -> list[tuple[str, Optional[int]]]:
    """
    Split text into overlapping chunks.
    Returns list of (chunk_text, page_number_or_None).
    Tries to split at sentence boundaries to avoid cutting mid-thought.
    """
    # Extract page markers if present
    page_pattern = re.compile(r'\[Page (\d+)\]')
    current_page = None
    chunks = []

    # Remove page markers but track page numbers
    segments = page_pattern.split(text)
    # segments alternates: [text_before, page_num, text_after, page_num, ...]

    full_clean = []
    page_map = []  # (char_start, page_num)
    pos = 0

    if len(segments) == 1:
        # No page markers
        full_clean = [text]
        page_map = [(0, None)]
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

    combined = "".join(full_clean)

    # Split into sentences first
    sentences = re.split(r'(?<=[.!?])\s+|\n\n', combined)

    current_chunk = []
    current_len   = 0
    overlap_buf   = []

    def get_page_for_pos(p):
        pg = None
        for start, pnum in page_map:
            if start <= p:
                pg = pnum
        return pg

    char_pos = 0
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        if current_len + len(sent) > CHUNK_SIZE and current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append((chunk_text, get_page_for_pos(char_pos)))

            # Keep last few sentences as overlap
            overlap = []
            overlap_len = 0
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

    # Last chunk
    if current_chunk:
        chunks.append((" ".join(current_chunk), get_page_for_pos(char_pos)))

    return chunks


# ── Public API ────────────────────────────────────────────────────────────────

def index_document(text: str, file_name: str = "", total_pages: int = 0) -> DocumentIndex:
    """
    Index a full document for retrieval.
    Call once on upload — results cached in memory.
    """
    raw_chunks = _split_into_chunks(text)

    chunks = []
    for i, (chunk_text, page) in enumerate(raw_chunks):
        if not chunk_text.strip():
            continue
        chunks.append(Chunk(
            id       = i,
            text     = chunk_text,
            page     = page,
            keywords = _extract_keywords(chunk_text),
        ))

    return DocumentIndex(
        chunks      = chunks,
        total_pages = total_pages,
        total_words = len(text.split()),
        file_name   = file_name,
        full_text   = text,  # kept for legal pattern extraction
    )


def retrieve(index: DocumentIndex, query: str, n: int = MAX_CHUNKS_PER_QUERY) -> list[Chunk]:
    """
    Find the N most relevant chunks for a query.
    Returns chunks sorted by relevance score descending.
    """
    if not index.chunks:
        return []

    query_keywords = _extract_keywords(query)

    # Score all chunks
    scored = [
        (chunk, _score_chunk(chunk, query_keywords))
        for chunk in index.chunks
    ]

    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)

    # Take top N, but also ensure we have coverage
    top = [c for c, s in scored[:n] if s > 0]

    # If we have fewer than 2 relevant chunks, add top chunks by position
    # (beginning and end of document often have key info)
    if len(top) < 2 and index.chunks:
        if index.chunks[0] not in top:
            top.insert(0, index.chunks[0])
        if len(index.chunks) > 1 and index.chunks[-1] not in top:
            top.append(index.chunks[-1])

    return top[:n]


def get_context(index: DocumentIndex, query: str) -> str:
    """
    Build a context string ready to send to the AI.
    Includes relevant chunks with page references.
    """
    chunks = retrieve(index, query)
    if not chunks:
        return index.full_text[:MAX_CONTEXT_CHARS]

    parts = []
    for chunk in chunks:
        page_ref = f"[Page {chunk.page}] " if chunk.page else ""
        parts.append(f"{page_ref}{chunk.text}")

    context = "\n\n---\n\n".join(parts)

    # Final safety cap
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n[...truncated]"

    return context


def get_summary_context(index: DocumentIndex) -> str:
    """
    Build context for summarization — samples from beginning, middle, and end.
    Gives a representative overview of the whole document.
    """
    chunks = index.chunks
    if not chunks:
        return index.full_text[:MAX_CONTEXT_CHARS]

    n = len(chunks)
    selected = []

    # Always include first 2 chunks (intro, parties)
    selected.extend(chunks[:2])

    # Sample from middle
    mid = n // 2
    if mid > 2:
        selected.extend(chunks[max(0, mid-1):mid+1])

    # Always include last 2 chunks (signatures, dates, final clauses)
    if n > 4:
        selected.extend(chunks[-2:])

    # Deduplicate preserving order
    seen = set()
    deduped = []
    for c in selected:
        if c.id not in seen:
            deduped.append(c)
            seen.add(c.id)

    parts = []
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
    }
