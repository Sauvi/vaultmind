"""
actions.py — VaultMind v0.5
All permitted file processing actions.
Uses the full document pipeline: extract → clean → truncate → AI.
"""

from pathlib import Path
from sandbox import is_safe_output
from file_reader import read_document
from ollama_engine import summarize, is_ollama_running, legal_analyze
from legal_extractor import extract_fast, build_ai_prompt, format_report


def summarize_file(input_path: str, output_path: str) -> str:
    if not is_safe_output(output_path):
        raise PermissionError(f"Output path blocked: {output_path}")

    doc = read_document(input_path)

    if not doc.text.strip():
        summary_text = "(Document appears empty or contains only images.)"
    elif is_ollama_running():
        summary_text = summarize(doc.text)
    else:
        # Fallback — first 10 lines
        lines = [l for l in doc.text.splitlines() if l.strip()]
        summary_text = "\n".join(lines[:10])
        summary_text += "\n\n⚠️  Ollama not running — basic extract only."

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"=== VaultMind Summary ===\n")
        f.write(f"Source    : {Path(input_path).name}\n")
        f.write(f"Type      : {doc.file_type.upper()}\n")
        f.write(f"Pages     : {doc.pages}\n")
        f.write(f"Words     : {len(doc.text.split()):,}\n")
        if doc.truncated:
            f.write(f"Note      : Large document — start + end analysed\n")
        f.write(f"{'=' * 35}\n\n")
        f.write(summary_text + "\n")

    return output_path


def legal_review_file(input_path: str, output_path: str) -> str:
    """
    Two-stage legal analysis:
    Stage 1 — Pattern extraction (zero AI, instant)
    Stage 2 — Targeted AI on extracted sections only (fast, low RAM)
    """
    if not is_safe_output(output_path):
        raise PermissionError(f"Output path blocked: {output_path}")

    doc = read_document(input_path)
    if not doc.text.strip():
        raise ValueError("Document appears empty or unreadable.")

    # Stage 1: instant pattern extraction
    extraction = extract_fast(doc.text, pages_read=doc.pages)

    # Stage 2: AI on targeted sections only
    if is_ollama_running() and (extraction.risk_clauses or extraction.obligations):
        ai_prompt = build_ai_prompt(extraction)
        extraction.ai_analysis = legal_analyze(ai_prompt)
    elif not is_ollama_running():
        extraction.ai_analysis = "⚠️  Ollama not running — pattern extraction only."
    else:
        extraction.ai_analysis = "No risk clauses or obligations detected."

    report = format_report(extraction)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    return output_path


ALLOWED_ACTIONS = {
    "summarize":    summarize_file,
    "legal_review": legal_review_file,
}
