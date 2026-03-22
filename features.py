"""
features.py — VaultMind v0.8
Four new sellable capabilities:
1. contract_compare   — diff two contracts, highlight changes + risks
2. clause_extract     — pull specific clause types from any contract
3. deadline_tracker   — extract all dates + obligations as checklist
4. report_generator   — generate professional DOCX report
"""

import re
from datetime import datetime
from pathlib import Path
from legal_extractor import (
    extract_fast, _extract_dates, _extract_risk_sentences,
    _extract_obligation_sentences, _extract_parties,
    _detect_governing_law, _detect_contract_type
)


# ══════════════════════════════════════════════════════════════
# 1. CONTRACT COMPARISON
# ══════════════════════════════════════════════════════════════

def compare_contracts(text_a: str, text_b: str,
                      name_a: str = "Contract A",
                      name_b: str = "Contract B") -> dict:
    """
    Compare two contracts and return structured differences.
    Uses pattern extraction — no AI needed, instant.
    """
    ext_a = extract_fast(text_a)
    ext_b = extract_fast(text_b)

    def _set(lst): return set(s.strip().lower() for s in lst)

    # Party changes
    parties_added    = list(_set(ext_b.parties) - _set(ext_a.parties))
    parties_removed  = list(_set(ext_a.parties) - _set(ext_b.parties))

    # Date changes
    dates_added      = list(_set(ext_b.dates) - _set(ext_a.dates))
    dates_removed    = list(_set(ext_a.dates) - _set(ext_b.dates))

    # Risk clause changes
    risks_added      = []
    risks_removed    = []
    for r in ext_b.risk_clauses:
        if not any(_similarity(r, ra) > 0.6 for ra in ext_a.risk_clauses):
            risks_added.append(r[:200])
    for r in ext_a.risk_clauses:
        if not any(_similarity(r, rb) > 0.6 for rb in ext_b.risk_clauses):
            risks_removed.append(r[:200])

    # Obligation changes
    obls_added   = []
    obls_removed = []
    for o in ext_b.obligations:
        if not any(_similarity(o, oa) > 0.6 for oa in ext_a.obligations):
            obls_added.append(o[:200])
    for o in ext_a.obligations:
        if not any(_similarity(o, ob) > 0.6 for ob in ext_b.obligations):
            obls_removed.append(o[:200])

    # Governing law change
    law_changed = (ext_a.governing_law or "").strip() != (ext_b.governing_law or "").strip()

    # Contract type change
    type_changed = ext_a.contract_type != ext_b.contract_type

    # Risk score — higher = more different/riskier
    risk_score = (
        len(risks_added) * 3 +
        len(obls_added) * 2 +
        len(dates_added) * 1 +
        (5 if law_changed else 0) +
        (3 if type_changed else 0)
    )
    risk_level = "HIGH" if risk_score >= 10 else "MEDIUM" if risk_score >= 4 else "LOW"

    return {
        "name_a":          name_a,
        "name_b":          name_b,
        "contract_type_a": ext_a.contract_type,
        "contract_type_b": ext_b.contract_type,
        "type_changed":    type_changed,
        "governing_law_a": ext_a.governing_law,
        "governing_law_b": ext_b.governing_law,
        "law_changed":     law_changed,
        "parties_added":   parties_added,
        "parties_removed": parties_removed,
        "dates_added":     dates_added,
        "dates_removed":   dates_removed,
        "risks_added":     risks_added[:5],
        "risks_removed":   risks_removed[:5],
        "obls_added":      obls_added[:5],
        "obls_removed":    obls_removed[:5],
        "risk_score":      risk_score,
        "risk_level":      risk_level,
        "summary": _compare_summary(
            risk_level, type_changed, law_changed,
            len(risks_added), len(obls_added), len(dates_added)
        ),
    }


def _similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity score."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def _compare_summary(risk_level, type_changed, law_changed,
                     n_risks, n_obls, n_dates) -> str:
    parts = []
    if type_changed:
        parts.append("contract type changed")
    if law_changed:
        parts.append("governing law changed — significant legal implications")
    if n_risks > 0:
        parts.append(f"{n_risks} new risk clause(s) added")
    if n_obls > 0:
        parts.append(f"{n_obls} new obligation(s) added")
    if n_dates > 0:
        parts.append(f"{n_dates} new date(s) added")
    if not parts:
        return "Contracts are substantially similar — no major differences detected."
    return f"Risk level: {risk_level}. Key changes: {'; '.join(parts)}."


def format_comparison(result: dict) -> str:
    """Format comparison result as readable text."""
    lines = []
    lines.append("=" * 44)
    lines.append("CONTRACT COMPARISON REPORT")
    lines.append("=" * 44)
    lines.append(f"Document A : {result['name_a']}")
    lines.append(f"Document B : {result['name_b']}")
    lines.append(f"Risk level : {result['risk_level']}")
    lines.append("")
    lines.append(result["summary"])
    lines.append("")

    if result["type_changed"]:
        lines.append("⚠  CONTRACT TYPE CHANGED")
        lines.append(f"   A: {result['contract_type_a']}")
        lines.append(f"   B: {result['contract_type_b']}")
        lines.append("")

    if result["law_changed"]:
        lines.append("⚠  GOVERNING LAW CHANGED")
        lines.append(f"   A: {result['governing_law_a'] or 'Not specified'}")
        lines.append(f"   B: {result['governing_law_b'] or 'Not specified'}")
        lines.append("")

    if result["risks_added"]:
        lines.append(f"NEW RISKS IN {result['name_b']} ({len(result['risks_added'])})")
        for r in result["risks_added"]:
            lines.append(f"  ⚠  {r}")
        lines.append("")

    if result["risks_removed"]:
        lines.append(f"RISKS REMOVED FROM {result['name_a']} ({len(result['risks_removed'])})")
        for r in result["risks_removed"]:
            lines.append(f"  ✓  {r}")
        lines.append("")

    if result["obls_added"]:
        lines.append(f"NEW OBLIGATIONS IN {result['name_b']} ({len(result['obls_added'])})")
        for o in result["obls_added"]:
            lines.append(f"  →  {o}")
        lines.append("")

    if result["dates_added"]:
        lines.append(f"NEW DATES IN {result['name_b']}")
        for d in result["dates_added"]:
            lines.append(f"  📅  {d}")
        lines.append("")

    lines.append("=" * 44)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 2. CLAUSE EXTRACTION
# ══════════════════════════════════════════════════════════════

CLAUSE_TYPES = {
    "payment":         ["payment", "invoice", "fee", "price", "cost", "compensation", "salary", "remuneration", "inr", "usd", "amount"],
    "termination":     ["terminat", "cancel", "end", "expir", "cessation", "wind-down", "dissolv"],
    "confidentiality": ["confidential", "non-disclosure", "nda", "proprietary", "secret", "disclose"],
    "liability":       ["liabilit", "liable", "indemnif", "damages", "loss", "compensat"],
    "ip":              ["intellectual property", "copyright", "patent", "trademark", "trade secret", "invention", "ownership"],
    "dispute":         ["dispute", "arbitration", "mediation", "litigation", "jurisdiction", "court", "governing law"],
    "warranty":        ["warrant", "represent", "guarantee", "assur", "promise", "covenant"],
    "force_majeure":   ["force majeure", "act of god", "pandemic", "natural disaster", "beyond control"],
    "assignment":      ["assign", "transfer", "delegate", "novation", "successor"],
    "non_compete":     ["non-compet", "non compet", "restraint of trade", "exclusiv"],
}


def extract_clauses(text: str, clause_type: str = "all") -> dict:
    """
    Extract specific clause types from a contract.
    Returns dict of clause_type → list of relevant sentences.
    """
    sentences = re.split(r'(?<=[.!?])\s+|\n\n', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

    types_to_check = (
        list(CLAUSE_TYPES.keys())
        if clause_type == "all"
        else [clause_type] if clause_type in CLAUSE_TYPES else list(CLAUSE_TYPES.keys())
    )

    result = {}
    for ct in types_to_check:
        keywords = CLAUSE_TYPES[ct]
        found = []
        for sent in sentences:
            sent_lower = sent.lower()
            if any(kw in sent_lower for kw in keywords):
                if sent not in found:
                    found.append(sent[:300])
        if found:
            result[ct] = found[:6]  # max 6 per type

    return result


def format_clauses(clauses: dict, file_name: str = "") -> str:
    """Format extracted clauses as readable text."""
    lines = ["=" * 44, "CLAUSE EXTRACTION REPORT"]
    if file_name:
        lines.append(f"Source: {file_name}")
    lines.extend(["=" * 44, ""])

    if not clauses:
        lines.append("No specific clauses detected.")
        return "\n".join(lines)

    for clause_type, sentences in clauses.items():
        title = clause_type.replace("_", " ").upper()
        lines.append(f"── {title} ({len(sentences)} clauses)")
        for i, sent in enumerate(sentences, 1):
            lines.append(f"  {i}. {sent}")
        lines.append("")

    lines.append("=" * 44)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 3. DEADLINE & OBLIGATION TRACKER
# ══════════════════════════════════════════════════════════════

def track_deadlines(text: str, file_name: str = "") -> dict:
    """
    Extract all dates and obligations from a contract
    and return as a structured checklist.
    """
    dates       = _extract_dates(text)
    obligations = _extract_obligation_sentences(text)
    parties     = _extract_parties(text)

    # Try to pair dates with nearby obligation context
    date_items = []
    for date in dates:
        # Find sentence containing this date
        for sent in re.split(r'(?<=[.!?])\s+', text):
            if date in sent:
                context = sent.strip()[:200]
                date_items.append({
                    "date":    date,
                    "context": context,
                    "done":    False,
                })
                break
        else:
            date_items.append({"date": date, "context": "", "done": False})

    # Format obligations as checklist items
    obligation_items = []
    for obl in obligations[:10]:
        obligation_items.append({
            "text": obl[:200],
            "done": False,
        })

    return {
        "file_name":        file_name,
        "generated_at":     datetime.now().strftime("%Y-%m-%d %H:%M"),
        "parties":          parties,
        "total_dates":      len(date_items),
        "total_obligations": len(obligation_items),
        "dates":            date_items,
        "obligations":      obligation_items,
    }


def format_deadlines(tracker: dict) -> str:
    """Format deadline tracker as readable checklist."""
    lines = ["=" * 44, "DEADLINE & OBLIGATION TRACKER"]
    if tracker["file_name"]:
        lines.append(f"Source    : {tracker['file_name']}")
    lines.append(f"Generated : {tracker['generated_at']}")
    if tracker["parties"]:
        lines.append(f"Parties   : {', '.join(tracker['parties'][:2])}")
    lines.extend(["=" * 44, ""])

    lines.append(f"KEY DATES ({tracker['total_dates']} found)")
    lines.append("─" * 30)
    for item in tracker["dates"]:
        check = "☐"
        lines.append(f"{check}  {item['date']}")
        if item["context"]:
            lines.append(f"    Context: {item['context'][:120]}...")
        lines.append("")

    lines.append(f"OBLIGATIONS ({tracker['total_obligations']} found)")
    lines.append("─" * 30)
    for i, item in enumerate(tracker["obligations"], 1):
        lines.append(f"☐  {i}. {item['text']}")
        lines.append("")

    lines.append("=" * 44)
    lines.append("TIP: Print this checklist and tick off items as completed.")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 4. PROFESSIONAL REPORT GENERATOR (python-docx)
# ══════════════════════════════════════════════════════════════

def generate_report(
    extraction,
    file_name:   str = "",
    output_path: str = "",
    ai_analysis: str = "",
    comparison:  dict = None,
    clauses:     dict = None,
    tracker:     dict = None,
) -> str:
    """
    Generate a professional DOCX report using python-docx.
    Returns the output file path.
    """
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise RuntimeError("Run: pip install python-docx")

    doc = Document()

    # ── Page margins ──────────────────────────────────────────
    for section in doc.sections:
        section.top_margin    = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin   = Inches(1.2)
        section.right_margin  = Inches(1.2)

    # ── Styles helper ─────────────────────────────────────────
    def heading(text, level=1):
        p = doc.add_heading(text, level=level)
        p.runs[0].font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
        return p

    def body(text):
        p = doc.add_paragraph(text)
        p.runs[0].font.size = Pt(11) if p.runs else None
        return p

    def bullet(text):
        doc.add_paragraph(text, style="List Bullet")

    def divider():
        p = doc.add_paragraph()
        p.paragraph_format.space_after  = Pt(2)
        p.paragraph_format.space_before = Pt(2)

    # ── Cover ─────────────────────────────────────────────────
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("VaultMind Legal Analysis Report")
    run.bold      = True
    run.font.size = Pt(20)
    run.font.color.rgb = RGBColor(0x7C, 0x6A, 0xF7)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run(f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}")

    if file_name:
        fn = doc.add_paragraph()
        fn.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fn.add_run(f"Document: {file_name}").bold = True

    doc.add_paragraph()

    # ── Executive summary ─────────────────────────────────────
    heading("Executive Summary")
    body(f"Contract Type: {extraction.contract_type or 'General Contract'}")
    body(f"Governing Law: {extraction.governing_law or 'Not specified'}")
    body(f"Parties: {', '.join(extraction.parties) if extraction.parties else 'Not identified'}")
    body(f"Key Dates Found: {len(extraction.dates)}")
    body(f"Risk Clauses: {len(extraction.risk_clauses)}")
    body(f"Obligations: {len(extraction.obligations)}")
    divider()

    # ── Parties ───────────────────────────────────────────────
    if extraction.parties:
        heading("Parties", level=2)
        for p in extraction.parties:
            bullet(p)
        divider()

    # ── Key dates ─────────────────────────────────────────────
    if extraction.dates:
        heading("Key Dates & Deadlines", level=2)
        for d in extraction.dates:
            bullet(d)
        divider()

    # ── Risk clauses ──────────────────────────────────────────
    if extraction.risk_clauses:
        heading("Risk Clauses Detected", level=2)
        for r in extraction.risk_clauses:
            bullet(f"⚠  {r[:250]}")
        divider()

    # ── Obligations ───────────────────────────────────────────
    if extraction.obligations:
        heading("Key Obligations", level=2)
        for o in extraction.obligations:
            bullet(f"→  {o[:250]}")
        divider()

    # ── AI risk analysis ──────────────────────────────────────
    if ai_analysis:
        heading("AI Risk Analysis", level=2)
        for line in ai_analysis.split("\n"):
            line = line.strip()
            if line:
                body(line)
        divider()

    # ── Clause extraction ─────────────────────────────────────
    if clauses:
        heading("Clause Extraction", level=2)
        for clause_type, sentences in clauses.items():
            heading(clause_type.replace("_", " ").title(), level=3)
            for sent in sentences[:3]:
                bullet(sent[:250])
        divider()

    # ── Deadline tracker ──────────────────────────────────────
    if tracker:
        heading("Obligation Checklist", level=2)
        for item in tracker.get("obligations", [])[:8]:
            doc.add_paragraph(f"☐  {item['text'][:200]}", style="List Bullet")
        divider()

    # ── Comparison ────────────────────────────────────────────
    if comparison:
        heading("Contract Comparison", level=2)
        body(comparison.get("summary", ""))
        if comparison.get("risks_added"):
            heading("New Risks Added", level=3)
            for r in comparison["risks_added"]:
                bullet(f"⚠  {r[:200]}")
        divider()

    # ── Footer note ───────────────────────────────────────────
    doc.add_paragraph()
    note = doc.add_paragraph(
        "This report was generated by VaultMind — 100% local AI, no cloud processing. "
        "All analysis was performed on your machine. "
        "This report is for informational purposes only and does not constitute legal advice."
    )
    note.runs[0].font.size = Pt(9)
    note.runs[0].font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    # ── Save ──────────────────────────────────────────────────
    if not output_path:
        stem = Path(file_name).stem if file_name else "document"
        output_path = str(
            Path("workspace/output") / f"{stem}_vaultmind_report.docx"
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    return output_path
