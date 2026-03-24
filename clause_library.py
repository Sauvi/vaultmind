"""
clause_library.py — VaultMind v1.0
Reusable clause library with local JSON persistence.

Lawyers can save clauses from any analysis, tag them,
and reuse them when drafting new documents.

No AI needed — pure local storage.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

# ── Storage ───────────────────────────────────────────────────
LIBRARY_PATH = Path("workspace/clause_library.json")

CLAUSE_CATEGORIES = [
    "payment",
    "termination",
    "confidentiality",
    "liability",
    "ip",
    "dispute",
    "warranty",
    "force_majeure",
    "assignment",
    "non_compete",
    "indemnity",
    "governing_law",
    "general",
]


# ══════════════════════════════════════════════════════════════
# STORAGE HELPERS
# ══════════════════════════════════════════════════════════════

def _load_library() -> dict:
    """Load clause library from disk. Returns empty structure if not found."""
    LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LIBRARY_PATH.exists():
        return {"clauses": [], "meta": {"created": datetime.now().isoformat()}}
    try:
        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"clauses": [], "meta": {"created": datetime.now().isoformat()}}


def _save_library(data: dict) -> None:
    """Persist clause library to disk."""
    LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════
# CORE OPERATIONS
# ══════════════════════════════════════════════════════════════

def save_clause(
    text: str,
    category: str = "general",
    title: str = "",
    source_file: str = "",
    tags: list = None,
) -> dict:
    """
    Save a clause to the local library.

    Args:
        text: The clause text to save.
        category: One of CLAUSE_CATEGORIES.
        title: Optional short title for the clause.
        source_file: Original document name (for reference).
        tags: Optional list of custom tags.

    Returns:
        The saved clause dict with its ID.
    """
    if not text or not text.strip():
        raise ValueError("Clause text cannot be empty.")

    if category not in CLAUSE_CATEGORIES:
        category = "general"

    if not title:
        # Auto-generate a title from the first ~60 chars
        title = text.strip()[:60].rstrip(".,;:") + ("..." if len(text) > 60 else "")

    clause = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "category": category,
        "text": text.strip(),
        "source_file": source_file,
        "tags": tags or [],
        "created_at": datetime.now().isoformat(),
        "used_count": 0,
    }

    library = _load_library()
    library["clauses"].append(clause)
    _save_library(library)

    return clause


def get_all_clauses(category: str = None) -> list:
    """
    Retrieve all saved clauses, optionally filtered by category.

    Args:
        category: Filter by category name. None returns all.

    Returns:
        List of clause dicts, newest first.
    """
    library = _load_library()
    clauses = library.get("clauses", [])

    if category and category != "all":
        clauses = [c for c in clauses if c.get("category") == category]

    # Newest first
    return list(reversed(clauses))


def search_clauses(query: str) -> list:
    """
    Search clauses by keyword — matches against title, text, tags, source.

    Args:
        query: Search string (case-insensitive).

    Returns:
        List of matching clause dicts.
    """
    if not query or not query.strip():
        return get_all_clauses()

    q = query.lower().strip()
    library = _load_library()
    results = []

    for clause in library.get("clauses", []):
        searchable = " ".join([
            clause.get("title", ""),
            clause.get("text", ""),
            clause.get("category", ""),
            clause.get("source_file", ""),
            " ".join(clause.get("tags", [])),
        ]).lower()

        if q in searchable:
            results.append(clause)

    return list(reversed(results))


def get_clause_by_id(clause_id: str) -> dict | None:
    """Retrieve a single clause by its ID."""
    library = _load_library()
    for clause in library.get("clauses", []):
        if clause.get("id") == clause_id:
            return clause
    return None


def delete_clause(clause_id: str) -> bool:
    """
    Delete a clause from the library by ID.

    Returns:
        True if deleted, False if not found.
    """
    library = _load_library()
    original_count = len(library.get("clauses", []))
    library["clauses"] = [
        c for c in library.get("clauses", []) if c.get("id") != clause_id
    ]
    if len(library["clauses"]) < original_count:
        _save_library(library)
        return True
    return False


def increment_usage(clause_id: str) -> None:
    """Track how many times a clause has been used/inserted."""
    library = _load_library()
    for clause in library.get("clauses", []):
        if clause.get("id") == clause_id:
            clause["used_count"] = clause.get("used_count", 0) + 1
            break
    _save_library(library)


def update_clause(clause_id: str, updates: dict) -> dict | None:
    """
    Update an existing clause (title, text, category, tags).

    Args:
        clause_id: ID of clause to update.
        updates: Dict of fields to update.

    Returns:
        Updated clause or None if not found.
    """
    allowed = {"title", "text", "category", "tags"}
    library = _load_library()

    for clause in library.get("clauses", []):
        if clause.get("id") == clause_id:
            for key, value in updates.items():
                if key in allowed:
                    if key == "category" and value not in CLAUSE_CATEGORIES:
                        value = "general"
                    clause[key] = value
            clause["updated_at"] = datetime.now().isoformat()
            _save_library(library)
            return clause

    return None


def library_stats() -> dict:
    """Return summary stats for the clause library."""
    library = _load_library()
    clauses = library.get("clauses", [])

    by_category = {}
    for clause in clauses:
        cat = clause.get("category", "general")
        by_category[cat] = by_category.get(cat, 0) + 1

    most_used = sorted(clauses, key=lambda c: c.get("used_count", 0), reverse=True)[:5]

    return {
        "total_clauses": len(clauses),
        "by_category": by_category,
        "most_used": [
            {"id": c["id"], "title": c["title"], "used": c.get("used_count", 0)}
            for c in most_used
        ],
    }


# ══════════════════════════════════════════════════════════════
# FORMATTING
# ══════════════════════════════════════════════════════════════

def format_library_listing(clauses: list, title: str = "SAVED CLAUSES") -> str:
    """Format a list of clauses for display."""
    lines = ["=" * 50, title, "=" * 50, ""]

    if not clauses:
        lines.append("No clauses saved yet.")
        lines.append("")
        lines.append("Tip: After a clause extraction or legal review,")
        lines.append("     use 'Save to Library' to store useful clauses.")
        lines.append("=" * 50)
        return "\n".join(lines)

    current_cat = None
    for clause in clauses:
        cat = clause.get("category", "general")
        if cat != current_cat:
            current_cat = cat
            lines.append(f"── {cat.replace('_', ' ').upper()}")
            lines.append("─" * 40)

        lines.append(f"[{clause['id']}] {clause['title']}")
        lines.append(f"  {clause['text'][:150]}{'...' if len(clause['text']) > 150 else ''}")
        if clause.get("source_file"):
            lines.append(f"  Source: {clause['source_file']}")
        if clause.get("tags"):
            lines.append(f"  Tags: {', '.join(clause['tags'])}")
        lines.append(f"  Used: {clause.get('used_count', 0)} times | "
                     f"Saved: {clause['created_at'][:10]}")
        lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


def format_clause_detail(clause: dict) -> str:
    """Format a single clause for display / copy."""
    if not clause:
        return "Clause not found."

    lines = [
        "=" * 50,
        f"CLAUSE: {clause['title']}",
        "=" * 50,
        f"ID       : {clause['id']}",
        f"Category : {clause['category'].replace('_', ' ').title()}",
        f"Source   : {clause.get('source_file', 'Manual entry')}",
        f"Tags     : {', '.join(clause.get('tags', [])) or 'None'}",
        f"Used     : {clause.get('used_count', 0)} times",
        f"Saved    : {clause['created_at'][:10]}",
        "",
        "── CLAUSE TEXT",
        "─" * 40,
        clause["text"],
        "",
        "=" * 50,
        "Tip: Copy the clause text above and paste into your draft.",
    ]
    return "\n".join(lines)
