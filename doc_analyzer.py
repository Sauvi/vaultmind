"""
doc_analyzer.py — VaultMind v1.1
12 zero-AI document analysis features.
Pure Python — regex, difflib, statistics. All instant.

1.  defined_terms_map          — extract all "X means Y" definitions; flag undefined
2.  monetary_scanner           — all currency amounts sorted by size
3.  cross_reference_checker    — find "See Clause X" refs; flag broken ones
4.  defined_term_usage_checker — capitalised terms used inconsistently / only once
5.  redline_diff               — word-level diff between two document versions
6.  document_statistics        — readability, complexity, density metrics
7.  signature_block_extractor  — find signing blocks; flag missing fields
8.  notice_requirements        — all notice periods, methods, addresses
9.  termination_trigger_map    — all conditions that trigger termination
10. liability_cap_finder        — all liability caps, exclusions, indemnity limits
11. boilerplate_detector        — standard vs non-standard clauses
12. party_obligation_matrix     — who must do what, per party
"""

import re
import difflib
from datetime import datetime
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+|\n{2,}', text)
    return [s.strip() for s in parts if len(s.strip()) > 15]


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ═══════════════════════════════════════════════════════════════
# 1. DEFINED TERMS MAP
# ═══════════════════════════════════════════════════════════════

_DEFINITION_PATTERNS = [
    # "Term" means / shall mean / is defined as
    r'"([A-Z][A-Za-z\s\-]{1,50})"\s+(?:means|shall mean|is defined as|refers to|shall refer to)\s+([^.;]{10,200})',
    # (the "Term") after a description
    r'([^.,(]{10,120})\s+\((?:the\s+)?"([A-Z][A-Za-z\s\-]{1,50})"\)',
    # "Term" — defined term in quotes followed by colon or dash
    r'"([A-Z][A-Za-z\s\-]{1,50})"\s*[:\-—]\s*([^.;]{10,200})',
    # Term (as defined herein / as defined below)
    r'\b([A-Z][A-Za-z\s\-]{1,50})\s+\(as defined (?:herein|below|in [Cc]lause \d+)\)',
]

_EXCLUDED_CAPS = {
    'THIS', 'THE', 'IN', 'FOR', 'OF', 'AND', 'OR', 'TO', 'BY',
    'A', 'AN', 'ON', 'AT', 'AS', 'WITH', 'FROM', 'THAT', 'SUCH',
    'EACH', 'ALL', 'ANY', 'NO', 'NOT', 'BE', 'IS', 'ARE', 'WAS',
    'WERE', 'WILL', 'SHALL', 'MAY', 'MUST', 'SHOULD', 'WOULD',
    'PARTIES', 'PARTY', 'AGREEMENT', 'SCHEDULE', 'EXHIBIT', 'ANNEX',
    'SECTION', 'CLAUSE', 'ARTICLE', 'APPENDIX', 'WHEREAS', 'NOW',
    'THEREFORE', 'WITNESSETH', 'RECITALS',
}


def defined_terms_map(text: str, file_name: str = "") -> dict:
    """
    Extract all defined terms and their definitions.
    Also identifies capitalised terms used in the document
    but never formally defined — a common drafting error.
    """
    definitions = {}

    for pattern in _DEFINITION_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            groups = m.groups()
            if len(groups) == 2:
                # Determine which group is term vs definition
                if re.match(r'^[A-Z]', groups[0]) and len(groups[0]) < 60:
                    term = _clean(groups[0]).strip('"\'')
                    defn = _clean(groups[1])
                else:
                    term = _clean(groups[1]).strip('"\'')
                    defn = _clean(groups[0])

                if len(term) > 2 and term.upper() not in _EXCLUDED_CAPS:
                    if term not in definitions:
                        definitions[term] = defn[:250]

    # Find all capitalised multi-word phrases used as defined terms
    # (Title Case phrases that appear 2+ times)
    cap_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\b'
    cap_counts: dict[str, int] = defaultdict(int)
    for m in re.finditer(cap_pattern, text):
        word = m.group(1)
        if word.split()[0].upper() not in _EXCLUDED_CAPS:
            cap_counts[word] += 1

    # Find capitalised single words used like defined terms (ALLCAPS style)
    allcaps_pattern = r'\b([A-Z]{3,20})\b'
    for m in re.finditer(allcaps_pattern, text):
        word = m.group(1)
        if word not in _EXCLUDED_CAPS:
            cap_counts[word] = cap_counts.get(word, 0) + 1

    # Identify undefined terms (used 2+ times but not formally defined)
    defined_lower = {k.lower() for k in definitions}
    undefined = []
    for term, count in sorted(cap_counts.items(), key=lambda x: -x[1]):
        if count >= 2 and term.lower() not in defined_lower:
            if len(term) > 3:
                undefined.append({"term": term, "occurrences": count})

    return {
        "file_name":        file_name,
        "generated_at":     _now(),
        "total_defined":    len(definitions),
        "total_undefined":  len(undefined),
        "definitions":      [{"term": k, "definition": v} for k, v in sorted(definitions.items())],
        "undefined_terms":  undefined[:20],
    }


def format_defined_terms(result: dict) -> str:
    lines = ["=" * 50, "DEFINED TERMS MAP"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50, f"Defined terms:   {result['total_defined']}",
              f"Undefined terms: {result['total_undefined']}", ""]

    if result["definitions"]:
        lines.append("── DEFINED TERMS")
        lines.append("─" * 40)
        for d in result["definitions"]:
            lines.append(f"  \"{d['term']}\"")
            lines.append(f"    → {d['definition'][:200]}")
            lines.append("")

    if result["undefined_terms"]:
        lines.append("── POSSIBLY UNDEFINED (used 2+ times, no formal definition found)")
        lines.append("─" * 40)
        for u in result["undefined_terms"]:
            lines.append(f"  ⚠  {u['term']}  ({u['occurrences']} uses)")
        lines.append("")
        lines.append("TIP: Each of these should either be formally defined or decapitalised.")

    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 2. MONETARY VALUE SCANNER
# ═══════════════════════════════════════════════════════════════

_CURRENCY_PATTERNS = [
    # INR formats: ₹ or Rs. or INR
    r'(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?(?:\s*(?:lakh|lakhs|crore|crores|thousand|million|billion))?)',
    # USD/GBP/EUR symbols
    r'(?:USD|US\$|\$|GBP|£|EUR|€)\s*([\d,]+(?:\.\d{1,2})?(?:\s*(?:thousand|million|billion))?)',
    # Written-out amount with currency after
    r'([\d,]+(?:\.\d{1,2})?)\s*(?:USD|INR|GBP|EUR)',
    # Amount with words
    r'\b((?:one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|lakh|crore|million|billion)(?:\s+(?:and\s+)?(?:one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|lakh|crore|million|billion))*)\s+(?:rupees?|dollars?|pounds?|euros?)',
]

_MULTIPLIERS = {
    'thousand': 1_000, 'lakh': 100_000, 'lakhs': 100_000,
    'crore': 10_000_000, 'crores': 10_000_000,
    'million': 1_000_000, 'billion': 1_000_000_000,
}

_CONTEXT_WINDOW = 120  # chars either side of amount for context


def _parse_amount(raw: str) -> float:
    """Convert a raw amount string to a float for sorting."""
    raw = raw.lower().replace(',', '').strip()
    multiplier = 1
    for word, mult in _MULTIPLIERS.items():
        if word in raw:
            raw = raw.replace(word, '').strip()
            multiplier = mult
            break
    try:
        return float(re.search(r'[\d.]+', raw).group()) * multiplier
    except Exception:
        return 0.0


def monetary_scanner(text: str, file_name: str = "") -> dict:
    """
    Extract all monetary values from a document.
    Returns them sorted by numeric value (largest first).
    Includes surrounding context to show what each amount is for.
    """
    found = []
    seen_positions = set()

    for pattern in _CURRENCY_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            pos = m.start()
            # Deduplicate overlapping matches
            if any(abs(pos - p) < 20 for p in seen_positions):
                continue
            seen_positions.add(pos)

            raw_amount = m.group(0)
            amount_val = _parse_amount(m.group(0))

            # Extract context
            start = max(0, pos - _CONTEXT_WINDOW)
            end   = min(len(text), pos + len(raw_amount) + _CONTEXT_WINDOW)
            ctx   = _clean(text[start:end])

            # Determine context type (what is this amount for?)
            ctx_lower = ctx.lower()
            amount_type = "General"
            if any(w in ctx_lower for w in ["penalt", "liquidated", "damages"]):
                amount_type = "Penalty / Damages"
            elif any(w in ctx_lower for w in ["fee", "payment", "invoice", "consideration"]):
                amount_type = "Fee / Payment"
            elif any(w in ctx_lower for w in ["salary", "remuneration", "compensation"]):
                amount_type = "Compensation"
            elif any(w in ctx_lower for w in ["liabilit", "cap", "limit", "maximum"]):
                amount_type = "Liability Cap"
            elif any(w in ctx_lower for w in ["deposit", "security", "retention"]):
                amount_type = "Deposit / Security"
            elif any(w in ctx_lower for w in ["interest", "rate", "per annum", "p.a."]):
                amount_type = "Interest / Rate"
            elif any(w in ctx_lower for w in ["indemnif", "reimburse", "indemnity"]):
                amount_type = "Indemnity"

            found.append({
                "raw":         raw_amount,
                "numeric":     amount_val,
                "type":        amount_type,
                "context":     ctx[:300],
            })

    # Sort by numeric value descending
    found.sort(key=lambda x: x["numeric"], reverse=True)

    # Remove duplicates by raw value
    seen_raw: set[str] = set()
    unique = []
    for item in found:
        key = item["raw"].lower().replace(" ", "")
        if key not in seen_raw:
            seen_raw.add(key)
            unique.append(item)

    return {
        "file_name":     file_name,
        "generated_at":  _now(),
        "total_amounts": len(unique),
        "amounts":       unique[:30],
    }


def format_monetary(result: dict) -> str:
    lines = ["=" * 50, "MONETARY VALUE SCANNER"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50, f"Total amounts found: {result['total_amounts']}", ""]

    if not result["amounts"]:
        lines.append("No monetary values detected.")
    else:
        type_groups: dict[str, list] = defaultdict(list)
        for a in result["amounts"]:
            type_groups[a["type"]].append(a)

        for atype, items in sorted(type_groups.items()):
            lines.append(f"── {atype.upper()}")
            lines.append("─" * 40)
            for item in items:
                lines.append(f"  {item['raw']}")
                lines.append(f"  Context: {item['context'][:160]}...")
                lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 3. CROSS-REFERENCE CHECKER
# ═══════════════════════════════════════════════════════════════

_XREF_PATTERNS = [
    r'[Ss]ection\s+(\d+(?:\.\d+)*)',
    r'[Cc]lause\s+(\d+(?:\.\d+)*)',
    r'[Aa]rticle\s+(\d+(?:\.\d+)*)',
    r'[Ss]chedule\s+([A-Z\d]+)',
    r'[Ee]xhibit\s+([A-Z\d]+)',
    r'[Aa]nnex(?:ure)?\s+([A-Z\d]+)',
    r'[Pp]aragraph\s+(\d+(?:\.\d+)*)',
]

_HEADING_PATTERNS = [
    r'^\s*(\d+(?:\.\d+)*)\s+[A-Z]',        # "4.2 TERMINATION"
    r'^\s*[Ss]ection\s+(\d+(?:\.\d+)*)\b',
    r'^\s*[Cc]lause\s+(\d+(?:\.\d+)*)\b',
    r'^\s*[Aa]rticle\s+(\d+(?:\.\d+)*)\b',
]


def cross_reference_checker(text: str, file_name: str = "") -> dict:
    """
    Find all internal cross-references (See Clause 4.2, per Schedule A)
    and check whether the referenced section actually exists in the document.
    """
    # Extract actual section numbers that exist
    existing_sections: set[str] = set()
    for line in text.split('\n'):
        for pat in _HEADING_PATTERNS:
            m = re.match(pat, line)
            if m:
                existing_sections.add(m.group(1).strip())

    # Extract all references made
    references = []
    seen_refs: set[str] = set()

    for pattern in _XREF_PATTERNS:
        ref_type = pattern.split('\\s')[0].replace('(?:', '').replace('[', '').replace(']', '').replace('Ss', 'Section').replace('Cc', 'Clause').replace('Aa', 'Article').replace('Pp', 'Paragraph').title()

        for m in re.finditer(pattern, text):
            ref_num = m.group(1).strip()
            key = f"{ref_type}:{ref_num}"
            if key in seen_refs:
                continue
            seen_refs.add(key)

            # Get surrounding context
            start = max(0, m.start() - 80)
            end   = min(len(text), m.end() + 80)
            ctx   = _clean(text[start:end])

            # Check if it exists
            exists = (ref_num in existing_sections or
                      any(ref_num.startswith(s) or s.startswith(ref_num)
                          for s in existing_sections))

            references.append({
                "reference": m.group(0),
                "number":    ref_num,
                "type":      ref_type,
                "exists":    exists,
                "context":   ctx[:200],
            })

    broken  = [r for r in references if not r["exists"]]
    valid   = [r for r in references if r["exists"]]

    return {
        "file_name":          file_name,
        "generated_at":       _now(),
        "total_references":   len(references),
        "broken_count":       len(broken),
        "valid_count":        len(valid),
        "existing_sections":  sorted(existing_sections),
        "broken_references":  broken[:20],
        "all_references":     references[:40],
    }


def format_cross_references(result: dict) -> str:
    lines = ["=" * 50, "CROSS-REFERENCE CHECKER"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50,
              f"Total references: {result['total_references']}",
              f"Broken refs:      {result['broken_count']}  {'⚠' if result['broken_count'] > 0 else '✓'}",
              f"Sections found:   {len(result['existing_sections'])}", ""]

    if result["broken_references"]:
        lines.append("── BROKEN / UNVERIFIED REFERENCES")
        lines.append("─" * 40)
        for r in result["broken_references"]:
            lines.append(f"  ⚠  {r['reference']}  (section {r['number']} not found)")
            lines.append(f"     Context: {r['context'][:150]}")
            lines.append("")
    else:
        lines.append("✓ All cross-references appear valid.")
        lines.append("")

    if result["existing_sections"]:
        lines.append(f"Sections detected: {', '.join(result['existing_sections'][:20])}")

    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 4. DEFINED TERM USAGE CHECKER
# ═══════════════════════════════════════════════════════════════

def defined_term_usage_checker(text: str, file_name: str = "") -> dict:
    """
    After extracting defined terms, checks whether they are:
    - Used only once (defined but never used)
    - Used inconsistently (mixed capitalisation)
    - Appear to be intended defined terms but are uncapitalised in places
    """
    # First get defined terms
    defs = defined_terms_map(text)
    defined_terms = [d["term"] for d in defs["definitions"]]

    issues = []

    for term in defined_terms:
        # Count exact capitalised uses
        exact_count  = len(re.findall(r'\b' + re.escape(term) + r'\b', text))
        # Count lowercase uses
        lower_count  = len(re.findall(r'\b' + re.escape(term.lower()) + r'\b', text, re.IGNORECASE)) - exact_count
        lower_count  = max(0, lower_count)

        # Defined but used only once (the definition itself)
        if exact_count <= 1:
            issues.append({
                "term": term, "issue": "Defined but never used",
                "exact_uses": exact_count, "lower_uses": lower_count,
                "severity": "MEDIUM"
            })
        # Used inconsistently (both capitalised and lowercase)
        elif lower_count > 0:
            issues.append({
                "term": term, "issue": "Inconsistent capitalisation",
                "exact_uses": exact_count, "lower_uses": lower_count,
                "severity": "HIGH"
            })

    issues.sort(key=lambda x: ("HIGH", "MEDIUM", "LOW").index(x["severity"]))

    return {
        "file_name":      file_name,
        "generated_at":   _now(),
        "total_defined":  len(defined_terms),
        "total_issues":   len(issues),
        "issues":         issues[:25],
    }


def format_term_usage(result: dict) -> str:
    lines = ["=" * 50, "DEFINED TERM USAGE CHECKER"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50,
              f"Defined terms checked: {result['total_defined']}",
              f"Issues found:          {result['total_issues']}", ""]

    if not result["issues"]:
        lines.append("✓ All defined terms appear to be used consistently.")
    else:
        for issue in result["issues"]:
            sev_icon = "⚠" if issue["severity"] == "HIGH" else "•"
            lines.append(f"{sev_icon}  [{issue['severity']}] \"{issue['term']}\"")
            lines.append(f"   Issue: {issue['issue']}")
            lines.append(f"   Capitalised uses: {issue['exact_uses']}  |  Lowercase uses: {issue['lower_uses']}")
            lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 5. REDLINE / WORD-LEVEL DIFF
# ═══════════════════════════════════════════════════════════════

def redline_diff(text_a: str, text_b: str,
                 name_a: str = "Version A",
                 name_b: str = "Version B") -> dict:
    """
    Word-level diff between two document versions.
    Returns structured diff with insertions, deletions, and unchanged text.
    Also generates an HTML redline for rendering in the browser.
    """
    words_a = re.findall(r'\S+|\s+', text_a)
    words_b = re.findall(r'\S+|\s+', text_b)

    matcher = difflib.SequenceMatcher(None, words_a, words_b, autojunk=False)
    opcodes = matcher.get_opcodes()

    segments = []
    insertions = 0
    deletions  = 0

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            segments.append({"type": "unchanged", "text": "".join(words_a[i1:i2])})
        elif tag == 'delete':
            txt = "".join(words_a[i1:i2])
            segments.append({"type": "deleted", "text": txt})
            deletions += len(words_a[i1:i2])
        elif tag == 'insert':
            txt = "".join(words_b[j1:j2])
            segments.append({"type": "inserted", "text": txt})
            insertions += len(words_b[j1:j2])
        elif tag == 'replace':
            old = "".join(words_a[i1:i2])
            new = "".join(words_b[j1:j2])
            segments.append({"type": "deleted",  "text": old})
            segments.append({"type": "inserted", "text": new})
            deletions  += len(words_a[i1:i2])
            insertions += len(words_b[j1:j2])

    # Build HTML redline
    html_parts = []
    for seg in segments:
        t = seg["text"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if seg["type"] == "deleted":
            html_parts.append(f'<del style="background:#ffeaea;color:#c0392b;text-decoration:line-through;padding:0 1px">{t}</del>')
        elif seg["type"] == "inserted":
            html_parts.append(f'<ins style="background:#eafaf1;color:#1a7a45;text-decoration:none;padding:0 1px">{t}</ins>')
        else:
            html_parts.append(t)

    html_redline = "".join(html_parts)

    # Similarity score
    similarity = round(matcher.ratio() * 100, 1)

    return {
        "name_a":       name_a,
        "name_b":       name_b,
        "generated_at": _now(),
        "insertions":   insertions,
        "deletions":    deletions,
        "similarity":   similarity,
        "html_redline": html_redline,
        "segments":     segments[:500],  # cap for JSON size
    }


def format_redline_summary(result: dict) -> str:
    lines = ["=" * 50, "REDLINE — WORD LEVEL DIFF"]
    lines += ["=" * 50,
              f"Version A: {result['name_a']}",
              f"Version B: {result['name_b']}",
              f"Similarity:  {result['similarity']}%",
              f"Words added: {result['insertions']}",
              f"Words deleted: {result['deletions']}", "",
              "See the HTML redline in the browser for full colour markup.",
              "=" * 50]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 6. DOCUMENT STATISTICS
# ═══════════════════════════════════════════════════════════════

def document_statistics(text: str, file_name: str = "") -> dict:
    """
    Compute readability, complexity, and structural metrics.
    No AI — pure counting and statistics.
    """
    words      = text.split()
    word_count = len(words)
    sentences  = _sentences(text)
    sent_count = max(len(sentences), 1)

    # Avg words per sentence
    avg_sent_len = round(word_count / sent_count, 1)

    # Avg word length
    only_words = re.findall(r'\b[a-zA-Z]+\b', text)
    avg_word_len = round(sum(len(w) for w in only_words) / max(len(only_words), 1), 1)

    # Flesch-Kincaid approximation (syllables ≈ word_len / 3)
    syllables_est = sum(max(1, len(w) // 3) for w in only_words)
    if word_count > 0 and sent_count > 0:
        fk_grade = round(0.39 * (word_count / sent_count) + 11.8 * (syllables_est / max(word_count, 1)) - 15.59, 1)
    else:
        fk_grade = 0

    # Reading time (avg lawyer reads ~250 wpm for legal docs)
    reading_mins = round(word_count / 250, 1)

    # Longest sentences
    sorted_sents = sorted(sentences, key=len, reverse=True)
    longest      = [s[:250] for s in sorted_sents[:5]]

    # Paragraph count
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    para_count = len(paragraphs)

    # Unique word ratio (vocabulary richness)
    unique_ratio = round(len(set(w.lower() for w in only_words)) / max(len(only_words), 1) * 100, 1)

    # Passive voice indicators
    passive_patterns = [r'\b(?:is|are|was|were|be|been|being)\s+\w+ed\b',
                        r'\b(?:is|are|was|were|be|been|being)\s+\w+en\b']
    passive_count = sum(len(re.findall(p, text, re.IGNORECASE)) for p in passive_patterns)

    # Obligation density (shall/must per 100 words)
    obligation_count = len(re.findall(r'\b(?:shall|must|will|agrees? to|required to)\b', text, re.IGNORECASE))
    obligation_density = round(obligation_count / max(word_count, 1) * 100, 2)

    # Complexity rating
    if fk_grade >= 18:        complexity = "Very High (specialist legal)"
    elif fk_grade >= 14:      complexity = "High (advanced legal)"
    elif fk_grade >= 10:      complexity = "Medium (standard legal)"
    else:                     complexity = "Low (plain language)"

    return {
        "file_name":          file_name,
        "generated_at":       _now(),
        "word_count":         word_count,
        "sentence_count":     sent_count,
        "paragraph_count":    para_count,
        "avg_sentence_len":   avg_sent_len,
        "avg_word_len":       avg_word_len,
        "reading_time_mins":  reading_mins,
        "fk_grade":           fk_grade,
        "complexity":         complexity,
        "unique_word_ratio":  unique_ratio,
        "passive_count":      passive_count,
        "obligation_count":   obligation_count,
        "obligation_density": obligation_density,
        "longest_sentences":  longest,
    }


def format_statistics(result: dict) -> str:
    lines = ["=" * 50, "DOCUMENT STATISTICS"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50, "",
              f"Words              : {result['word_count']:,}",
              f"Sentences          : {result['sentence_count']:,}",
              f"Paragraphs         : {result['paragraph_count']:,}",
              f"Avg sentence length: {result['avg_sentence_len']} words",
              f"Avg word length    : {result['avg_word_len']} chars",
              f"Reading time       : ~{result['reading_time_mins']} minutes",
              "",
              f"Complexity         : {result['complexity']}",
              f"FK Grade           : {result['fk_grade']}",
              f"Vocabulary richness: {result['unique_word_ratio']}%",
              f"Passive voice uses : {result['passive_count']}",
              f"Obligation density : {result['obligation_density']} per 100 words",
              "",
              "── TOP 3 LONGEST SENTENCES"]
    for i, s in enumerate(result["longest_sentences"][:3], 1):
        lines.append(f"  {i}. {s[:200]}...")
        lines.append("")
    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 7. SIGNATURE BLOCK EXTRACTOR
# ═══════════════════════════════════════════════════════════════

_SIG_MARKERS = [
    r'(?:IN WITNESS WHEREOF|SIGNED|EXECUTED|AGREED|ACCEPTED)',
    r'Signature\s*[:_]+',
    r'Name\s*[:_]+',
    r'Authorised\s+[Ss]ignatory',
    r'Signed\s+by\s*:',
]

_SIG_FIELDS = {
    "signature": r'[Ss]ignature\s*[:\-_]*\s*(?:_+|\.+)',
    "name":      r'[Nn]ame\s*[:\-_]*\s*(?:_+|\.+|[A-Z][A-Za-z\s]{2,40})',
    "title":     r'[Tt]itle\s*[:\-_]*\s*(?:_+|\.+|[A-Z][A-Za-z\s]{2,40})',
    "date":      r'[Dd]ate\s*[:\-_]*\s*(?:_+|\.+|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
    "company":   r'(?:[Ff]or and on behalf of|[Cc]ompany)\s*[:\-_]*\s*(?:_+|\.+|[A-Z][A-Za-z\s]{2,60})',
}


def signature_block_extractor(text: str, file_name: str = "") -> dict:
    """
    Locate all signature blocks in the document.
    Flag missing required fields (name, title, date).
    """
    blocks = []
    lines  = text.split('\n')

    # Find regions with signature markers
    sig_region_starts = []
    for i, line in enumerate(lines):
        for marker in _SIG_MARKERS:
            if re.search(marker, line, re.IGNORECASE):
                sig_region_starts.append(i)
                break

    # De-duplicate nearby starts
    filtered_starts = []
    for s in sig_region_starts:
        if not filtered_starts or s - filtered_starts[-1] > 5:
            filtered_starts.append(s)

    for start in filtered_starts:
        end = min(start + 20, len(lines))
        region = "\n".join(lines[start:end])

        fields_found = {}
        fields_missing = []

        for field, pattern in _SIG_FIELDS.items():
            if re.search(pattern, region, re.IGNORECASE):
                fields_found[field] = True
            else:
                # Required fields
                if field in ("name", "date"):
                    fields_missing.append(field)

        blocks.append({
            "line_number":     start + 1,
            "preview":         _clean(region)[:300],
            "fields_found":    list(fields_found.keys()),
            "fields_missing":  fields_missing,
            "complete":        len(fields_missing) == 0,
        })

    return {
        "file_name":     file_name,
        "generated_at":  _now(),
        "total_blocks":  len(blocks),
        "complete":      sum(1 for b in blocks if b["complete"]),
        "incomplete":    sum(1 for b in blocks if not b["complete"]),
        "blocks":        blocks,
    }


def format_signature_blocks(result: dict) -> str:
    lines = ["=" * 50, "SIGNATURE BLOCK EXTRACTOR"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50,
              f"Signature blocks found: {result['total_blocks']}",
              f"Complete:               {result['complete']}",
              f"Incomplete:             {result['incomplete']}", ""]

    if not result["blocks"]:
        lines.append("No signature blocks detected.")
    else:
        for i, b in enumerate(result["blocks"], 1):
            status = "✓ Complete" if b["complete"] else f"⚠ Missing: {', '.join(b['fields_missing'])}"
            lines.append(f"── Block {i} (line {b['line_number']}) — {status}")
            lines.append(f"   {b['preview'][:200]}")
            if b["fields_found"]:
                lines.append(f"   Fields: {', '.join(b['fields_found'])}")
            lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 8. NOTICE REQUIREMENTS EXTRACTOR
# ═══════════════════════════════════════════════════════════════

_NOTICE_PATTERNS = [
    r'(?:notice|notification).{0,100}?(?:\d+\s+(?:business\s+)?days?)',
    r'(?:\d+\s+(?:business\s+)?days?).{0,80}?(?:notice|notification)',
    r'(?:written\s+notice|notice\s+in\s+writing).{0,200}',
    r'(?:notice\s+shall\s+be\s+(?:given|sent|delivered|served)).{0,200}',
    r'(?:by\s+(?:email|post|courier|hand|registered\s+post|certified\s+mail)).{0,150}',
    r'(?:notice\s+period|period\s+of\s+notice).{0,150}',
]

_ADDRESS_PATTERN = r'(?:address(?:ed)?(?:\s+to)?|attention(?:\s+of)?|for\s+the\s+attention\s+of)[:\s]+([A-Z][^\n]{10,100})'


def notice_requirements(text: str, file_name: str = "") -> dict:
    """
    Extract all notice provisions: periods, methods, addresses.
    Critical for lawyers to understand how to validly serve notice.
    """
    notices = []
    seen: set[str] = set()

    for pattern in _NOTICE_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            sent = _clean(m.group(0))
            if sent[:60] in seen or len(sent) < 20:
                continue
            seen.add(sent[:60])

            # Extract notice period
            period_m = re.search(r'(\d+\s+(?:business\s+)?days?|\d+\s+hours?|\d+\s+weeks?)', sent, re.IGNORECASE)
            period = period_m.group(0) if period_m else None

            # Extract method
            method = None
            for meth in ["email", "post", "courier", "hand delivery", "registered post", "certified mail", "fax"]:
                if meth in sent.lower():
                    method = meth.title()
                    break

            notices.append({
                "text":   sent[:300],
                "period": period,
                "method": method,
            })

    # Extract notice addresses
    addresses = []
    for m in re.finditer(_ADDRESS_PATTERN, text, re.IGNORECASE):
        addr = _clean(m.group(1))
        if len(addr) > 10 and addr not in addresses:
            addresses.append(addr[:200])

    return {
        "file_name":    file_name,
        "generated_at": _now(),
        "total_notices": len(notices),
        "notices":      notices[:15],
        "addresses":    addresses[:10],
    }


def format_notice_requirements(result: dict) -> str:
    lines = ["=" * 50, "NOTICE REQUIREMENTS"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50, f"Notice provisions found: {result['total_notices']}", ""]

    if not result["notices"]:
        lines.append("No notice provisions detected.")
    else:
        for i, n in enumerate(result["notices"], 1):
            lines.append(f"── Notice {i}")
            if n["period"]: lines.append(f"   Period: {n['period']}")
            if n["method"]: lines.append(f"   Method: {n['method']}")
            lines.append(f"   {n['text'][:200]}")
            lines.append("")

    if result["addresses"]:
        lines.append("── NOTICE ADDRESSES")
        for a in result["addresses"]:
            lines.append(f"  → {a}")
        lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 9. TERMINATION TRIGGER MAP
# ═══════════════════════════════════════════════════════════════

_TERMINATION_TRIGGERS = {
    "Breach":          [r'breach', r'default', r'failure to (?:perform|comply|pay)', r'non.performance'],
    "Insolvency":      [r'insolv', r'bankrupt', r'liquidat', r'winding.up', r'receiver', r'administrator'],
    "Convenience":     [r'convenience', r'without cause', r'for any reason', r'at (?:its|either party\'s) discretion'],
    "Notice":          [r'(?:upon|on|after)\s+\d+\s+days.?\s+(?:written\s+)?notice', r'notice\s+of\s+termination'],
    "Force Majeure":   [r'force majeure', r'act of god', r'beyond (?:its|the party\'s) control'],
    "Change of Control":[r'change of control', r'change in control', r'acquisition', r'merger'],
    "Regulatory":      [r'regulatory', r'law.*prohibit', r'illegal', r'unlawful', r'government order'],
    "Non-Payment":     [r'failure to pay', r'non.payment', r'payment.*overdue', r'invoice.*unpaid'],
    "Expiry":          [r'expir', r'end of term', r'upon completion', r'natural expiry'],
}


def termination_trigger_map(text: str, file_name: str = "") -> dict:
    """
    Build a complete map of all conditions that can trigger termination.
    Grouped by trigger type.
    """
    triggers: dict[str, list[str]] = defaultdict(list)
    sentences = _sentences(text)

    # Only look at sentences that contain termination language
    term_sents = [s for s in sentences if re.search(r'terminat|end\s+this|cancel', s, re.IGNORECASE)]

    for sent in term_sents:
        matched = False
        for trigger_type, patterns in _TERMINATION_TRIGGERS.items():
            for pat in patterns:
                if re.search(pat, sent, re.IGNORECASE):
                    if sent[:200] not in triggers[trigger_type]:
                        triggers[trigger_type].append(_clean(sent)[:250])
                    matched = True
                    break
        if not matched:
            # General termination clause not fitting a category
            if sent[:200] not in triggers["General"]:
                triggers["General"].append(_clean(sent)[:250])

    result_triggers = {k: v for k, v in triggers.items() if v}

    return {
        "file_name":      file_name,
        "generated_at":   _now(),
        "trigger_types":  len(result_triggers),
        "total_triggers": sum(len(v) for v in result_triggers.values()),
        "triggers":       dict(result_triggers),
    }


def format_termination_triggers(result: dict) -> str:
    lines = ["=" * 50, "TERMINATION TRIGGER MAP"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50,
              f"Trigger categories: {result['trigger_types']}",
              f"Total provisions:   {result['total_triggers']}", ""]

    if not result["triggers"]:
        lines.append("No termination provisions detected.")
    else:
        for trigger_type, provisions in result["triggers"].items():
            lines.append(f"── {trigger_type.upper()}")
            lines.append("─" * 40)
            for p in provisions[:3]:
                lines.append(f"  → {p[:200]}")
            lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 10. LIABILITY CAP FINDER
# ═══════════════════════════════════════════════════════════════

_LIABILITY_PATTERNS = [
    r'(?:total|aggregate|maximum|overall)\s+liabilit.{0,200}',
    r'liabilit.{0,50}(?:shall not exceed|capped at|limited to).{0,150}',
    r'(?:in no event|under no circumstances).{0,200}liabilit.{0,100}',
    r'(?:exclusion|exclus).{0,50}(?:liabilit|consequential|indirect).{0,150}',
    r'(?:consequential|indirect|special|punitive|incidental)\s+damages?.{0,150}(?:excluded|not liable|shall not)',
    r'indemnif.{0,200}(?:shall not exceed|limited|maximum).{0,100}',
    r'(?:neither party|no party|the (?:vendor|client|company|party))\s+shall\s+be\s+liable.{0,200}',
]


def liability_cap_finder(text: str, file_name: str = "") -> dict:
    """
    Find all liability caps, exclusions, and indemnity limits.
    """
    caps = []
    seen: set[str] = set()

    for pattern in _LIABILITY_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            sent = _clean(m.group(0))
            if sent[:80] in seen or len(sent) < 20:
                continue
            seen.add(sent[:80])

            # Check for amount
            amount_m = re.search(
                r'(?:₹|Rs\.?|INR|USD|\$|GBP|£)?\s*[\d,]+(?:\.\d{1,2})?(?:\s*(?:lakh|crore|million|billion|thousand))?',
                sent, re.IGNORECASE
            )
            amount = amount_m.group(0).strip() if amount_m else None

            # Type classification
            cap_type = "General Liability"
            sl = sent.lower()
            if any(w in sl for w in ["consequential", "indirect", "special", "punitive"]):
                cap_type = "Exclusion of Consequential Loss"
            elif any(w in sl for w in ["indemnif"]):
                cap_type = "Indemnity Limit"
            elif any(w in sl for w in ["aggregate", "total", "maximum", "overall"]):
                cap_type = "Aggregate Cap"
            elif any(w in sl for w in ["in no event", "under no circumstances"]):
                cap_type = "Full Exclusion"

            caps.append({
                "type":    cap_type,
                "amount":  amount,
                "text":    sent[:300],
            })

    return {
        "file_name":    file_name,
        "generated_at": _now(),
        "total_caps":   len(caps),
        "caps":         caps[:20],
    }


def format_liability_caps(result: dict) -> str:
    lines = ["=" * 50, "LIABILITY CAP FINDER"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50, f"Liability provisions found: {result['total_caps']}", ""]

    if not result["caps"]:
        lines.append("No liability caps or exclusions detected.")
        lines.append("⚠ This may mean there is no liability limitation — review carefully.")
    else:
        type_groups: dict[str, list] = defaultdict(list)
        for cap in result["caps"]:
            type_groups[cap["type"]].append(cap)

        for cap_type, items in type_groups.items():
            lines.append(f"── {cap_type.upper()}")
            lines.append("─" * 40)
            for item in items:
                if item["amount"]:
                    lines.append(f"  Cap amount: {item['amount']}")
                lines.append(f"  {item['text'][:200]}")
                lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 11. BOILERPLATE DETECTOR
# ═══════════════════════════════════════════════════════════════

# Standard boilerplate phrases that appear in most contracts verbatim
_BOILERPLATE_LIBRARY = {
    "Entire Agreement":   r'constitutes?\s+the\s+entire\s+agreement.{0,100}supersede',
    "Severability":       r'(?:invalid|unenforceable|void).{0,50}(?:remaining|other)\s+provisions?.{0,50}(?:remain|continue)',
    "Waiver":             r'(?:failure|delay).{0,50}(?:exercise|enforce).{0,50}(?:waiver|right)',
    "Counterparts":       r'(?:executed|signed)\s+in\s+counterparts',
    "Governing Law":      r'governed\s+by\s+(?:and\s+construed.{0,30})?laws?\s+of',
    "Dispute Resolution": r'(?:arbitration|mediation|conciliation).{0,100}(?:dispute|claim|controversy)',
    "Force Majeure":      r'force\s+majeure.{0,200}beyond.{0,50}control',
    "Assignment":         r'(?:shall not|may not|cannot)\s+assign.{0,100}(?:without|prior)\s+(?:written\s+)?(?:consent|approval)',
    "Amendment":          r'(?:amended|modified|varied).{0,80}(?:written|writing).{0,50}(?:both|all)\s+parties',
    "Notices":            r'notice.{0,100}(?:in writing|written notice).{0,100}(?:delivered|sent)',
    "Indemnification":    r'(?:indemnify|defend|hold harmless).{0,200}(?:claims?|losses?|damages?)',
    "Confidentiality":    r'(?:confidential|proprietary)\s+information.{0,100}(?:shall not|agree not to)\s+disclose',
}

_NON_STANDARD_INDICATORS = [
    r'notwithstanding\s+(?:anything|any\s+other)',  # override clause
    r'sole\s+(?:and\s+absolute\s+)?discretion',
    r'irrevocabl',
    r'unconditional',
    r'perpetual',
    r'unlimited\s+liabilit',
    r'personal\s+guarantee',
    r'joint\s+and\s+several',
    r'liquidated\s+damages',
    r'time\s+is\s+of\s+the\s+essence',
    r'lien|mortgage|charge\s+over',
    r'step.in\s+rights?',
]


def boilerplate_detector(text: str, file_name: str = "") -> dict:
    """
    Identify which standard boilerplate clauses are present/absent,
    and flag unusual non-standard clauses that deserve attention.
    """
    text_lower = text.lower()

    standard_present  = []
    standard_absent   = []
    non_standard_hits = []

    for clause_name, pattern in _BOILERPLATE_LIBRARY.items():
        if re.search(pattern, text, re.IGNORECASE):
            # Find the actual sentence
            m = re.search(pattern, text, re.IGNORECASE)
            start = max(0, m.start() - 40)
            end   = min(len(text), m.end() + 100)
            standard_present.append({
                "clause": clause_name,
                "preview": _clean(text[start:end])[:200],
            })
        else:
            standard_absent.append(clause_name)

    for indicator in _NON_STANDARD_INDICATORS:
        m = re.search(indicator, text, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 60)
            end   = min(len(text), m.end() + 140)
            snippet = _clean(text[start:end])
            if snippet not in [h["text"] for h in non_standard_hits]:
                non_standard_hits.append({
                    "trigger": m.group(0),
                    "text":    snippet[:250],
                })

    return {
        "file_name":         file_name,
        "generated_at":      _now(),
        "standard_present":  len(standard_present),
        "standard_absent":   len(standard_absent),
        "non_standard_count": len(non_standard_hits),
        "present":           standard_present,
        "absent":            standard_absent,
        "non_standard":      non_standard_hits[:15],
    }


def format_boilerplate(result: dict) -> str:
    lines = ["=" * 50, "BOILERPLATE DETECTOR"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50,
              f"Standard clauses present: {result['standard_present']}",
              f"Standard clauses absent:  {result['standard_absent']}",
              f"Non-standard flags:       {result['non_standard_count']}", ""]

    if result["present"]:
        lines.append("── STANDARD CLAUSES PRESENT")
        lines.append("─" * 40)
        for p in result["present"]:
            lines.append(f"  ✓  {p['clause']}")
        lines.append("")

    if result["absent"]:
        lines.append("── STANDARD CLAUSES MISSING")
        lines.append("─" * 40)
        for a in result["absent"]:
            lines.append(f"  ⚠  {a}")
        lines.append("")

    if result["non_standard"]:
        lines.append("── NON-STANDARD / UNUSUAL CLAUSES")
        lines.append("─" * 40)
        for ns in result["non_standard"]:
            lines.append(f"  ⚑  Trigger: \"{ns['trigger']}\"")
            lines.append(f"     {ns['text'][:180]}")
            lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 12. PARTY OBLIGATION MATRIX
# ═══════════════════════════════════════════════════════════════

_OBLIGATION_VERBS = [
    r'\bshall\b', r'\bmust\b', r'\bagrees?\s+to\b', r'\bundertakes?\s+to\b',
    r'\bcovenants?\s+to\b', r'\bis\s+required\s+to\b', r'\bwill\b',
    r'\bresponsible\s+for\b', r'\bobligated\s+to\b',
]


def party_obligation_matrix(text: str, file_name: str = "") -> dict:
    """
    Build a matrix of which party must do what.
    Extracts parties first, then maps obligations to each party.
    """
    from legal_extractor import _extract_parties

    parties = _extract_parties(text)
    if not parties:
        # Fall back to common party names
        for generic in ["Client", "Vendor", "Employer", "Employee",
                        "Consultant", "Company", "Service Provider"]:
            if re.search(r'\b' + generic + r'\b', text):
                parties.append(generic)

    sentences = _sentences(text)
    matrix: dict[str, list[str]] = {p: [] for p in parties}
    unattributed: list[str] = []

    for sent in sentences:
        # Only process obligation sentences
        is_obligation = any(re.search(pat, sent, re.IGNORECASE) for pat in _OBLIGATION_VERBS)
        if not is_obligation:
            continue

        matched_party = None
        for party in parties:
            # Check if the sentence refers to this party specifically
            party_words = party.split()
            # Match on last significant word (e.g. "Service Provider" → "Provider")
            short_name = party_words[-1] if len(party_words) > 1 else party
            if re.search(r'\b' + re.escape(short_name) + r'\b', sent, re.IGNORECASE):
                matched_party = party
                break
            if re.search(r'\b' + re.escape(party) + r'\b', sent, re.IGNORECASE):
                matched_party = party
                break

        cleaned = _clean(sent)[:220]
        if matched_party:
            if cleaned not in matrix[matched_party]:
                matrix[matched_party].append(cleaned)
        else:
            # Check for "each party" / "both parties"
            if re.search(r'\b(?:each|both|all)\s+part(?:y|ies)\b', sent, re.IGNORECASE):
                for p in parties:
                    if cleaned not in matrix[p]:
                        matrix[p].append(cleaned)
            elif cleaned not in unattributed:
                unattributed.append(cleaned)

    # Trim lists
    for p in matrix:
        matrix[p] = matrix[p][:10]
    unattributed = unattributed[:10]

    return {
        "file_name":     file_name,
        "generated_at":  _now(),
        "parties":       parties,
        "matrix":        {k: v for k, v in matrix.items() if v},
        "unattributed":  unattributed,
        "total_obligations": sum(len(v) for v in matrix.values()) + len(unattributed),
    }


def format_obligation_matrix(result: dict) -> str:
    lines = ["=" * 50, "PARTY OBLIGATION MATRIX"]
    if result["file_name"]: lines.append(f"Source: {result['file_name']}")
    lines += ["=" * 50,
              f"Parties identified: {len(result['parties'])}",
              f"Total obligations:  {result['total_obligations']}", ""]

    if not result["parties"]:
        lines.append("No parties identified.")
    else:
        for party, obligations in result["matrix"].items():
            if obligations:
                lines.append(f"── {party.upper()}")
                lines.append("─" * 40)
                for i, obl in enumerate(obligations, 1):
                    lines.append(f"  {i}. {obl}")
                lines.append("")

        if result["unattributed"]:
            lines.append("── GENERAL (both parties / unattributed)")
            lines.append("─" * 40)
            for i, obl in enumerate(result["unattributed"], 1):
                lines.append(f"  {i}. {obl}")
            lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# MASTER RUNNER — run all 12 at once
# ═══════════════════════════════════════════════════════════════

def run_full_analysis(text: str, file_name: str = "") -> dict:
    """Run all 12 zero-AI analyses and return combined results."""
    return {
        "defined_terms":    defined_terms_map(text, file_name),
        "monetary":         monetary_scanner(text, file_name),
        "cross_references": cross_reference_checker(text, file_name),
        "term_usage":       defined_term_usage_checker(text, file_name),
        "statistics":       document_statistics(text, file_name),
        "signatures":       signature_block_extractor(text, file_name),
        "notices":          notice_requirements(text, file_name),
        "termination":      termination_trigger_map(text, file_name),
        "liability":        liability_cap_finder(text, file_name),
        "boilerplate":      boilerplate_detector(text, file_name),
        "obligations":      party_obligation_matrix(text, file_name),
    }
