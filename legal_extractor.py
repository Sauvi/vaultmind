"""
legal_extractor.py — VaultMind
Stage 1: Fast pattern-based extraction (zero AI, instant).
Stage 2: Send only targeted sections to Ollama for analysis.

This is what makes VaultMind fast on limited hardware.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class LegalExtraction:
    parties:      list[str]       = field(default_factory=list)
    dates:        list[str]       = field(default_factory=list)
    obligations:  list[str]       = field(default_factory=list)
    risk_clauses: list[str]       = field(default_factory=list)
    governing_law: Optional[str]  = None
    contract_type: Optional[str]  = None
    ai_analysis:   Optional[str]  = None   # filled by Stage 2
    word_count:    int             = 0
    pages_read:    int             = 0


# ── Stage 1: Pattern matching (instant, no AI) ─────────────────────────────────

# Party patterns
_PARTY_PATTERNS = [
    # Matches "COMPANY NAME, a company..." or "COMPANY NAME, a limited..."
    r'([A-Z][A-Z\s]+(?:LTD|LLC|LLP|INC|CORP|PVT|LIMITED|SOLUTIONS|TECHNOLOGIES|SERVICES|HOLDINGS)\.?\s*(?:PVT\.\s*LTD\.?|LLP\.?)?)\s*,\s*a\s+(?:company|limited|corporation|partnership|pvt)',
    # Matches name before "(hereinafter referred to as"
    r'([A-Z][A-Z\s\.,]+?)\s*\(hereinafter\s+referred\s+to\s+as',
    # Quoted company name with party role
    r'"([A-Z][A-Za-z\s]+?)"\s*\((?:the\s+)?"?(?:Company|Client|Vendor|Contractor|Employee|Employer)',
]

# Date patterns
_DATE_PATTERNS = [
    r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December),?\s+\d{4})\b',
    r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b',
    r'\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})\b',
    r'(?:effective|dated?|expires?|commenc(?:es?|ing)|terminat(?:es?|ing)|due|deadline)[^\n]*?(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4}|\d{4}-\d{2}-\d{2})',
    r'(?:effective|dated?|expires?|commenc(?:es?|ing)|terminat(?:es?|ing))[^\n]*?((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})',
]

# Risk clause triggers — sentences containing these need AI attention
_RISK_KEYWORDS = [
    r'indemnif',
    r'liabilit',
    r'penalt',
    r'terminat',
    r'breach',
    r'default',
    r'warrant',
    r'disclaim',
    r'limitation of',
    r'force majeure',
    r'liquidated damages',
    r'governing law',
    r'jurisdiction',
    r'arbitration',
    r'confidential',
    r'non.compet',
    r'intellectual property',
    r'assignment',
    r'severab',
]

# Obligation triggers
_OBLIGATION_KEYWORDS = [
    r'\bshall\b',
    r'\bmust\b',
    r'\bagrees? to\b',
    r'\bobligation\b',
    r'\brequired to\b',
    r'\bresponsible for\b',
    r'\bcovenants? to\b',
    r'\bundertakes? to\b',
]

# Contract type detection
_CONTRACT_TYPES = {
    'Employment Agreement':    [r'employ(?:ee|er|ment)', r'salary', r'compensation', r'position'],
    'NDA / Confidentiality':   [r'non.disclosure', r'confidential(?:ity)?', r'proprietary information'],
    'Service Agreement':       [r'service(?:s)?', r'deliverable', r'scope of work', r'statement of work'],
    'Lease Agreement':         [r'lease', r'tenant', r'landlord', r'rent', r'premises'],
    'Purchase Agreement':      [r'purchase', r'sale', r'buyer', r'seller', r'consideration'],
    'License Agreement':       [r'licen(?:se|sor|see)', r'royalt', r'intellectual property'],
    'Partnership Agreement':   [r'partner(?:ship)?', r'profit sharing', r'joint venture'],
    'Loan Agreement':          [r'loan', r'borrower', r'lender', r'interest rate', r'repayment'],
}


def _clean(text: str) -> str:
    """Normalize whitespace."""
    return re.sub(r'\s+', ' ', text).strip()


def _extract_parties(text: str) -> list[str]:
    parties = set()
    for pattern in _PARTY_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            name = _clean(match.group(1))
            if 5 < len(name) < 80:
                parties.add(name)
    # Clean up party names — remove leading "AND" word prefix
    import re as _re
    cleaned = []
    for p in sorted(parties)[:6]:
        p = p.strip()
        p = _re.sub(r'^AND\s+', '', p, flags=_re.IGNORECASE)
        p = p.strip(" ,.")
        if len(p) > 4:
            cleaned.append(p)
    return cleaned


def _extract_dates(text: str) -> list[str]:
    dates = set()
    for pattern in _DATE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # Get the last group (the actual date)
            date = _clean(match.group(match.lastindex or 0))
            if date:
                dates.add(date)
    return sorted(dates)[:10]


def _extract_risk_sentences(text: str) -> list[str]:
    """Find sentences containing risk keywords — these go to AI."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    risky = []
    for sent in sentences:
        sent_clean = _clean(sent)
        if len(sent_clean) < 20:
            continue
        for kw in _RISK_KEYWORDS:
            if re.search(kw, sent_clean, re.IGNORECASE):
                if sent_clean not in risky:
                    risky.append(sent_clean[:300])  # cap sentence length
                break
    return risky[:8]   # top 8 risk sentences


def _extract_obligation_sentences(text: str) -> list[str]:
    """Find sentences with obligation language."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    obligations = []
    for sent in sentences:
        sent_clean = _clean(sent)
        if len(sent_clean) < 20:
            continue
        for kw in _OBLIGATION_KEYWORDS:
            if re.search(kw, sent_clean, re.IGNORECASE):
                if sent_clean not in obligations:
                    obligations.append(sent_clean[:300])
                break
    return obligations[:8]


def _detect_contract_type(text: str) -> str:
    scores = {}
    text_lower = text.lower()
    for contract_type, patterns in _CONTRACT_TYPES.items():
        score = sum(1 for p in patterns if re.search(p, text_lower))
        if score > 0:
            scores[contract_type] = score
    if not scores:
        return "General Contract"
    return max(scores, key=scores.get)


def _detect_governing_law(text: str) -> Optional[str]:
    patterns = [
        r'laws\s+of\s+(India|England|Wales|[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b',
        r'governed\s+by\s+(?:the\s+)?laws?\s+of\s+(?:the\s+)?(?:State\s+of\s+)?([A-Z][A-Za-z\s]{2,25}?)(?:\.|,|\s+without)',
        r'seat\s+and\s+venue\s+of\s+arbitration\s+shall\s+be\s+([A-Z][A-Za-z\s]{2,25}?)(?:\.|,)',
        r'exclusive\s+jurisdiction\s+of\s+the\s+courts?\s+in\s+([A-Z][A-Za-z\s]{2,25}?)(?:\.|,)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result = _clean(match.group(1))
            if 2 < len(result) < 60:
                return result
    return None


# ── Stage 1 main ───────────────────────────────────────────────────────────────

def extract_fast(text: str, pages_read: int = 1) -> LegalExtraction:
    """
    Stage 1: Pure pattern extraction — no AI, runs in milliseconds.
    Returns a LegalExtraction with everything we can find without AI.
    """
    result = LegalExtraction(
        parties       = _extract_parties(text),
        dates         = _extract_dates(text),
        obligations   = _extract_obligation_sentences(text),
        risk_clauses  = _extract_risk_sentences(text),
        governing_law = _detect_governing_law(text),
        contract_type = _detect_contract_type(text),
        word_count    = len(text.split()),
        pages_read    = pages_read,
    )
    return result


# ── Stage 2: Build a focused AI prompt from extraction ────────────────────────

def build_ai_prompt(extraction: LegalExtraction) -> str:
    """
    Build a tight, targeted prompt for Ollama.
    Only sends the extracted sections — NOT the full document.
    This keeps the AI call fast and RAM-light.
    """
    sections = []

    if extraction.parties:
        sections.append("PARTIES:\n" + "\n".join(f"- {p}" for p in extraction.parties))

    if extraction.dates:
        sections.append("KEY DATES FOUND:\n" + "\n".join(f"- {d}" for d in extraction.dates))

    if extraction.risk_clauses:
        # Send only top 4 risk sentences to AI
        risk_text = "\n".join(f"- {r}" for r in extraction.risk_clauses[:4])
        sections.append(f"RISK CLAUSES TO ANALYZE:\n{risk_text}")

    if extraction.obligations:
        obl_text = "\n".join(f"- {o}" for o in extraction.obligations[:4])
        sections.append(f"OBLIGATIONS FOUND:\n{obl_text}")

    context = "\n\n".join(sections)

    prompt = f"""You are a legal document analyst. Analyze these extracted sections from a {extraction.contract_type}.

{context}

Provide a concise legal analysis covering:
1. Key risks or red flags (2-3 bullet points)
2. Main obligations summary (1-2 sentences)
3. Overall risk level: LOW / MEDIUM / HIGH

Be direct and specific. Legal professionals will read this."""

    return prompt


def format_report(extraction: LegalExtraction) -> str:
    """Format the full extraction as a readable text report."""
    lines = []
    lines.append("=" * 40)
    lines.append("VAULTMIND LEGAL ANALYSIS REPORT")
    lines.append("=" * 40)
    lines.append(f"Document type : {extraction.contract_type or 'Unknown'}")
    lines.append(f"Word count    : {extraction.word_count:,}")
    lines.append(f"Pages read    : {extraction.pages_read}")
    lines.append("")

    if extraction.parties:
        lines.append("── PARTIES ──────────────────────────")
        for p in extraction.parties:
            lines.append(f"  • {p}")
        lines.append("")

    if extraction.dates:
        lines.append("── KEY DATES ────────────────────────")
        for d in extraction.dates:
            lines.append(f"  • {d}")
        lines.append("")

    if extraction.governing_law:
        lines.append(f"── GOVERNING LAW ────────────────────")
        lines.append(f"  • {extraction.governing_law}")
        lines.append("")

    if extraction.risk_clauses:
        lines.append("── RISK CLAUSES DETECTED ────────────")
        for r in extraction.risk_clauses:
            lines.append(f"  ⚠  {r[:200]}")
        lines.append("")

    if extraction.obligations:
        lines.append("── KEY OBLIGATIONS ──────────────────")
        for o in extraction.obligations:
            lines.append(f"  →  {o[:200]}")
        lines.append("")

    if extraction.ai_analysis:
        lines.append("── AI RISK ANALYSIS ─────────────────")
        lines.append(extraction.ai_analysis)
        lines.append("")

    lines.append("=" * 40)
    lines.append("Generated by VaultMind — 100% local")
    lines.append("=" * 40)

    return "\n".join(lines)
