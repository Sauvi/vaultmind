"""
file_reader.py — VaultMind v0.5
Smart document ingestion pipeline.

For every file type:
1. Extract text preserving logical reading order
2. Clean structural noise (headers, footers, page numbers)
3. Normalize to clean prose the AI can actually process
4. Return metadata alongside text

Supports: .txt, .md, .pdf, .docx
"""

from pathlib import Path
from typing import NamedTuple

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx", ".md"}

# Hard cap — enough for good answers, low enough to protect 8GB RAM
MAX_CHARS = 3000


class DocumentResult(NamedTuple):
    text:       str     # clean, normalized text ready for AI
    raw_chars:  int     # original character count before cleaning
    final_chars: int    # character count after cleaning + truncation
    pages:      int     # page count (PDFs) or estimated (others)
    file_type:  str     # extension without dot
    truncated:  bool    # whether document was truncated


# ── Public API ────────────────────────────────────────────────────────────────

def read_file(file_path: str) -> str:
    """Legacy API — returns clean text string. Used by actions.py."""
    return read_document(file_path).text


def read_document(file_path: str) -> DocumentResult:
    """Full pipeline — returns DocumentResult with text + metadata."""
    path = Path(file_path)
    ext  = path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported format: '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    # Step 1: Extract raw text
    if ext in (".txt", ".md"):
        raw, pages = _extract_text(path)
    elif ext == ".pdf":
        raw, pages = _extract_pdf(path)
    elif ext == ".docx":
        raw, pages = _extract_docx(path)

    raw_chars = len(raw)

    # Step 2: Clean noise
    cleaned = _clean(raw)

    # Step 3: Smart truncate
    final, truncated = _smart_truncate(cleaned, MAX_CHARS)

    return DocumentResult(
        text        = final,
        raw_chars   = raw_chars,
        final_chars = len(final),
        pages       = pages,
        file_type   = ext.lstrip("."),
        truncated   = truncated,
    )


def get_file_info(file_path: str) -> dict:
    path = Path(file_path)
    ext  = path.suffix.lower()
    size_kb = round(path.stat().st_size / 1024, 1) if path.exists() else 0
    return {
        "name":      path.name,
        "extension": ext,
        "size_kb":   size_kb,
        "supported": ext in SUPPORTED_EXTENSIONS,
    }


# ── Extractors ────────────────────────────────────────────────────────────────

def _extract_text(path: Path) -> tuple[str, int]:
    """Plain text / markdown — try encodings gracefully."""
    for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            text = path.read_text(encoding=enc)
            lines = len([l for l in text.splitlines() if l.strip()])
            return text, max(1, lines // 40)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Cannot decode {path.name}. Save as UTF-8 and retry.")


def _extract_pdf(path: Path) -> tuple[str, int]:
    """
    PDF extraction with reading-order preservation.
    Uses 'blocks' mode + sorts by vertical position so two-column
    layouts don't scramble. Falls back to 'text' mode if blocks empty.
    """
    try:
        import fitz
    except ImportError:
        raise RuntimeError("Run: pip install pymupdf")

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > 15:
        raise RuntimeError(
            f"PDF is {size_mb:.1f} MB. Max is 15 MB. "
            "Split the document or use the DOCX version."
        )

    pages_text = []

    with fitz.open(str(path)) as doc:
        total_pages = len(doc)
        # Read all pages but hard-cap total chars early to avoid RAM spike
        for page_num in range(total_pages):
            page   = doc[page_num]

            # ── Reading-order extraction ──────────────────────────────────
            # Get text blocks with position data
            blocks = page.get_text("blocks")  # returns (x0,y0,x1,y1,text,...)

            if blocks:
                # Sort blocks top→bottom, then left→right
                # This fixes two-column PDFs and header/footer ordering
                blocks_sorted = sorted(blocks, key=lambda b: (round(b[1] / 20) * 20, b[0]))
                page_text = "\n".join(
                    b[4].strip()
                    for b in blocks_sorted
                    if isinstance(b[4], str) and b[4].strip()
                )
            else:
                # Fallback to simple text extraction
                page_text = page.get_text("text")

            if page_text.strip():
                pages_text.append(f"[Page {page_num + 1}]\n{page_text.strip()}")

            # Early exit if we already have way more than we'll use
            if sum(len(p) for p in pages_text) > MAX_CHARS * 3:
                if page_num < total_pages - 1:
                    pages_text.append(
                        f"[Pages {page_num + 2}–{total_pages} not read — "
                        f"sufficient content extracted]"
                    )
                break

    if not pages_text:
        raise RuntimeError(
            f"No text extracted from {path.name}. "
            "It may be a scanned image PDF (no selectable text)."
        )

    return "\n\n".join(pages_text), total_pages


def _extract_docx(path: Path) -> tuple[str, int]:
    """
    DOCX extraction preserving document structure.
    Headings get markers, tables get pipe-formatted, lists preserved.
    This gives the AI clear structure to reason about.
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise RuntimeError("Run: pip install python-docx")

    doc   = Document(str(path))
    parts = []

    for para in doc.paragraphs:
        text  = para.text.strip()
        if not text:
            continue
        style = para.style.name.lower() if para.style else ""

        # Mark headings so AI understands document structure
        if "heading 1" in style:
            parts.append(f"\n## {text}")
        elif "heading 2" in style:
            parts.append(f"\n### {text}")
        elif "heading" in style:
            parts.append(f"\n#### {text}")
        elif "list" in style or text.startswith(("•", "-", "*", "◦")):
            parts.append(f"  - {text.lstrip('•-*◦ ')}")
        else:
            parts.append(text)

    # Extract tables as pipe-formatted markdown — AI handles this well
    for table in doc.tables:
        table_rows = []
        for i, row in enumerate(table.rows):
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            # Deduplicate merged cells
            seen = []
            deduped = []
            for c in cells:
                if c not in seen:
                    deduped.append(c)
                    seen.append(c)
                else:
                    deduped.append("")
            row_str = " | ".join(deduped)
            table_rows.append(row_str)
            if i == 0:
                table_rows.append("-" * len(row_str))  # header separator
        if table_rows:
            parts.append("\n" + "\n".join(table_rows))

    if not parts:
        raise RuntimeError(f"No text found in {path.name}.")

    text = "\n".join(parts)
    # Estimate pages: ~300 words per page
    word_count = len(text.split())
    pages = max(1, word_count // 300)
    return text, pages


# ── Cleaner ───────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """
    Remove structural noise while preserving ALL language characters.
    Safe for Hindi, Arabic, Chinese, Devanagari etc.
    """
    import re

    # Remove page number lines (standalone numbers or "Page N of M")
    text = re.sub(r'(?m)^\s*[Pp]age\s+\d+\s+(?:of\s+\d+)?\s*$', '', text)
    text = re.sub(r'(?m)^\s*\d+\s*$', '', text)

    # Remove long divider lines (---, ===, ___)
    text = re.sub(r'[-_=*#~]{4,}', '', text)

    # Remove email headers noise (From:, To:, Subject: repeated blocks)
    text = re.sub(r'(?m)^(From|To|CC|BCC|Subject|Date)\s*:.*$', '', text)

    # Collapse 3+ newlines → 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Collapse multiple spaces/tabs on a line
    text = re.sub(r'[ \t]{2,}', ' ', text)

    # Strip lines that are pure noise (single chars, just punctuation)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # Keep if: has 3+ chars, or is a structural marker we added (##, ---)
        if len(stripped) >= 3 or stripped.startswith('#'):
            lines.append(line)
        elif not stripped:
            lines.append('')  # preserve blank lines for structure

    text = '\n'.join(lines)

    # Final: remove actual non-printable control chars
    # Keep ALL unicode — only drop ASCII control chars (0x00-0x1F except \n\r\t)
    text = ''.join(
        ch for ch in text
        if ord(ch) >= 32 or ch in '\n\r\t'
    )

    return text.strip()


# ── Smart truncation ──────────────────────────────────────────────────────────

def _smart_truncate(text: str, max_chars: int) -> tuple[str, bool]:
    """
    If text fits, return as-is.
    If too long: keep first 65% + last 35%.
    Contracts: parties/definitions at start, signatures/dates at end.
    Resumes: summary at start, recent experience in middle, skills at end.
    Keeping both ends captures the most important content.
    """
    if len(text) <= max_chars:
        return text, False

    head = int(max_chars * 0.65)
    tail = max_chars - head

    truncated = (
        text[:head]
        + "\n\n[... middle section omitted — showing start and end of document ...]\n\n"
        + text[-tail:]
    )
    return truncated, True


def clean_text(text: str) -> str:
    """Legacy alias — used by actions.py directly."""
    return _clean(text)

def read_full_text(file_path: str) -> str:
    """
    Extract complete text without any truncation.
    Used by RAG indexing — we need the full document to build the index.
    Truncation happens later at query time when we send to AI.
    """
    path = Path(file_path)
    ext  = path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported format: '{ext}'")

    if ext in (".txt", ".md"):
        raw, _ = _extract_text(path)
    elif ext == ".pdf":
        raw, _ = _extract_pdf_full(path)
    elif ext == ".docx":
        raw, _ = _extract_docx(path)

    return _clean(raw)


def _extract_pdf_full(path: Path) -> tuple[str, int]:
    """
    Extract ALL pages from PDF — no page or char limits.
    Used for RAG indexing only.
    """
    try:
        import fitz
    except ImportError:
        raise RuntimeError("Run: pip install pymupdf")

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > 50:
        raise RuntimeError(
            f"PDF is {size_mb:.1f} MB — max 50 MB for indexing."
        )

    pages_text = []
    with fitz.open(str(path)) as doc:
        total_pages = len(doc)
        for page_num in range(total_pages):
            page   = doc[page_num]
            blocks = page.get_text("blocks")
            if blocks:
                blocks_sorted = sorted(blocks, key=lambda b: (round(b[1] / 20) * 20, b[0]))
                page_text = "\n".join(
                    b[4].strip() for b in blocks_sorted
                    if isinstance(b[4], str) and b[4].strip()
                )
            else:
                page_text = page.get_text("text")

            if page_text.strip():
                pages_text.append(f"[Page {page_num + 1}]\n{page_text.strip()}")

    if not pages_text:
        raise RuntimeError(f"No text extracted from {path.name}.")

    return "\n\n".join(pages_text), total_pages
