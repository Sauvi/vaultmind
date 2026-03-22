"""
multi_doc.py — VaultMind v0.9
Multi-document analysis.
Upload multiple files, chat across all of them at once.
Uses smart sampling — pulls relevant sections from each doc per question.
"""

import re
from dataclasses import dataclass, field


@dataclass
class DocCollection:
    docs:  dict[str, str]  = field(default_factory=dict)   # name → full_text
    names: list[str]       = field(default_factory=list)   # ordered names


def add_document(collection: DocCollection, name: str, text: str) -> None:
    """Add a document to the collection."""
    collection.docs[name]  = text
    if name not in collection.names:
        collection.names.append(name)


def remove_document(collection: DocCollection, name: str) -> None:
    collection.docs.pop(name, None)
    if name in collection.names:
        collection.names.remove(name)


def get_multi_context(collection: DocCollection,
                      question:   str,
                      max_chars_per_doc: int = 1500) -> str:
    """
    Build a combined context from all documents for a question.
    Extracts the most relevant section from each doc.
    Returns a clearly labeled combined context.
    """
    if not collection.docs:
        return ""

    stop = {"the","a","an","is","are","was","were","what","how","who",
            "when","where","why","which","this","that","in","of","to",
            "and","or","for","with","do","does","did","can","will","me",
            "give","tell","show","find","please","my","your","its","any"}
    q_words = set(re.findall(r"\b[a-z]{3,}\b", question.lower())) - stop

    parts = []
    for name in collection.names:
        text = collection.docs.get(name, "")
        if not text:
            continue

        # Extract most relevant paragraphs from this doc
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        scored = []
        for para in paragraphs:
            score = sum(1 for w in q_words if w in para.lower())
            scored.append((score, para))
        scored.sort(key=lambda x: x[0], reverse=True)

        # Take intro + best scoring paragraphs
        selected = []
        total    = 0
        if paragraphs:
            selected.append(paragraphs[0])
            total += len(paragraphs[0])
        for score, para in scored:
            if total >= max_chars_per_doc:
                break
            if para not in selected:
                selected.append(para)
                total += len(para)

        excerpt = "\n\n".join(selected)
        parts.append(f"[DOCUMENT: {name}]\n{excerpt}")

    return "\n\n" + ("─" * 40) + "\n\n".join(parts)


def get_collection_summary(collection: DocCollection) -> dict:
    return {
        "count":      len(collection.docs),
        "names":      collection.names,
        "total_words": sum(len(t.split()) for t in collection.docs.values()),
    }


def find_conflicts(collection: DocCollection) -> list[str]:
    """
    Find potential conflicts between documents.
    Looks for contradictory governing law, different parties, etc.
    """
    from legal_extractor import _detect_governing_law, _extract_parties

    conflicts = []
    laws    = {}
    parties = {}

    for name, text in collection.docs.items():
        law = _detect_governing_law(text)
        if law:
            laws[name] = law
        pts = _extract_parties(text)
        if pts:
            parties[name] = pts

    # Check governing law conflicts
    unique_laws = set(laws.values())
    if len(unique_laws) > 1:
        conflicts.append(
            f"Governing law conflict: "
            + ", ".join(f"{n}={l}" for n, l in laws.items())
        )

    return conflicts
