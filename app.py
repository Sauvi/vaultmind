"""
app.py — VaultMind v0.7
Simplified architecture — full document sent directly to AI.
No chunking, no retrieval gaps, no missed content.
RAG index kept for legal pattern extraction only (full doc scan).
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from task_manager import handle_file, get_proposed_plan
from memory import load_memory
from ollama_engine import (
    is_ollama_running, list_models, warmup_model,
    stream_chat_with_history, stream_summary, stream_legal_analyze,
    get_best_model
)
from file_reader import (
    read_document, read_full_text, read_full_text_with_meta,
    SUPPORTED_EXTENSIONS, ocr_status
)
from rag_engine import index_document, get_stats as rag_get_stats, is_semantic_available
from legal_extractor import extract_fast, build_ai_prompt, format_report
from drafting import (
    get_template_list, get_template_fields,
    draft_document, save_draft, save_draft_docx
)
from multi_doc import (
    DocCollection, add_document, get_multi_context,
    get_collection_summary, find_conflicts
)
from features import (
    compare_contracts, format_comparison,
    extract_clauses, format_clauses,
    track_deadlines, format_deadlines,
    generate_report,
    detect_ambiguity, format_ambiguity,
    extract_timeline, format_timeline,
)
from clause_library import (
    save_clause, get_all_clauses, search_clauses,
    get_clause_by_id, delete_clause, update_clause,
    library_stats, format_library_listing, format_clause_detail,
    CLAUSE_CATEGORIES,
)
from doc_analyzer import (
    defined_terms_map, format_defined_terms,
    monetary_scanner, format_monetary,
    cross_reference_checker, format_cross_references,
    defined_term_usage_checker, format_term_usage,
    redline_diff, format_redline_summary,
    document_statistics, format_statistics,
    signature_block_extractor, format_signature_blocks,
    notice_requirements, format_notice_requirements,
    termination_trigger_map, format_termination_triggers,
    liability_cap_finder, format_liability_caps,
    boilerplate_detector, format_boilerplate,
    party_obligation_matrix, format_obligation_matrix,
    run_full_analysis,
)


# ── Dirs ──────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
INPUT_DIR    = BASE_DIR / "workspace" / "input"
OUTPUT_DIR   = BASE_DIR / "workspace" / "output"
STATIC_DIR   = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
AUDIT_FILE   = BASE_DIR / "audit.log"

for d in [INPUT_DIR, OUTPUT_DIR, STATIC_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── In-memory stores ──────────────────────────────────────────────────────────
_doc_cache:         dict[str, str]        = {}  # file_path → full clean text
_doc_meta:          dict[str, dict]       = {}  # file_path → metadata
_chat_history:      dict[str, list[dict]] = {}  # file_path → conversation
_multi_collections: dict[str, object]     = {}  # session_id → DocCollection
_rag_index:         dict[str, object]     = {}  # file_path → DocumentIndex (RAG)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="VaultMind", version="0.7.0")


@app.on_event("startup")
async def startup():
    import threading
    def _warmup():
        if is_ollama_running():
            print("🔥 VaultMind: warming up AI model...")
            ok = warmup_model()
            print("✅ AI model ready." if ok else "⚠️  Warmup failed.")
        else:
            print("⚠️  Ollama not running.")
    threading.Thread(target=_warmup, daemon=True).start()


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_path(file_path: str) -> Path:
    p = Path(file_path)
    if p.exists():
        return p
    alt = INPUT_DIR / p.name
    if alt.exists():
        return alt
    return p


def _get_doc_text(file_path: str) -> str:
    """Get full document text — cached after first read."""
    key = str(Path(file_path))
    if key not in _doc_cache:
        full_path = _resolve_path(file_path)
        _doc_cache[key] = read_full_text(str(full_path))
    return _doc_cache[key]


def _log_audit(action: str, file_path: str, success: bool):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(AUDIT_FILE, "a") as f:
        f.write(f"[{ts}] {'OK' if success else 'FAIL'} | {action} | {file_path}\n")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "memory": load_memory(),
        "output_files": sorted(os.listdir(OUTPUT_DIR), reverse=True)[:10],
    })


@app.get("/status")
async def status():
    running = is_ollama_running()
    return JSONResponse({
        "ollama": running,
        "models": list_models() if running else []
    })


@app.get("/check-deps")
async def check_deps():
    results = {}
    try:
        import fitz
        results["pymupdf"] = f"✅ installed (v{fitz.version[0]})"
    except ImportError:
        results["pymupdf"] = "❌ missing — run: pip install pymupdf"
    try:
        import docx
        results["python-docx"] = "✅ installed"
    except ImportError:
        results["python-docx"] = "❌ missing — run: pip install python-docx"
    try:
        import pytesseract
        results["pytesseract"] = "✅ installed"
    except ImportError:
        results["pytesseract"] = "❌ missing — run: pip install pytesseract"
    try:
        import pdf2image
        results["pdf2image"] = "✅ installed"
    except ImportError:
        results["pdf2image"] = "❌ missing — run: pip install pdf2image"
    try:
        import sentence_transformers
        results["sentence-transformers"] = "✅ installed"
    except ImportError:
        results["sentence-transformers"] = "❌ missing — run: pip install sentence-transformers"
    return JSONResponse(results)


@app.get("/ocr-status")
async def ocr_status_route():
    """Return OCR availability status."""
    return JSONResponse(ocr_status())


@app.get("/rag-status")
async def rag_status_route():
    """Return RAG engine status."""
    semantic = is_semantic_available()
    indexed  = {k: rag_get_stats(v) for k, v in _rag_index.items()}
    return JSONResponse({
        "semantic_available": semantic,
        "mode": "semantic" if semantic else "keyword",
        "indexed_documents":  len(indexed),
        "indexes": indexed,
    })


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), action: str = Form("summarize")):
    """Upload file — read full text and cache it."""
    try:
        safe_name = Path(file.filename).name
        save_path = INPUT_DIR / safe_name

        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Read and cache full document text + build RAG index
        key       = str(save_path)
        full_text, pages_count, is_ocr = read_full_text_with_meta(str(save_path))
        doc_meta  = read_document(str(save_path))

        _doc_cache[key]    = full_text
        _chat_history[key] = []  # reset conversation

        # Build RAG index in background thread (non-blocking)
        import threading
        def _build_index():
            try:
                idx = index_document(
                    full_text,
                    file_name=safe_name,
                    total_pages=pages_count,
                    is_ocr=is_ocr,
                )
                _rag_index[key] = idx
                stats = rag_get_stats(idx)
                print(f"[RAG] Indexed {safe_name}: {stats['chunks']} chunks, "
                      f"mode={stats['rag_mode']}, ocr={is_ocr}")
            except Exception as e:
                print(f"[RAG] Indexing failed for {safe_name}: {e}")
        threading.Thread(target=_build_index, daemon=True).start()

        _doc_meta[key] = {
            "name":       safe_name,
            "pages":      pages_count,
            "words":      len(full_text.split()),
            "chars":      len(full_text),
            "size_kb":    round(save_path.stat().st_size / 1024, 1),
            "extension":  save_path.suffix.lower(),
            "is_ocr":     is_ocr,
        }

        meta = _doc_meta[key]
        print(f"📄 Loaded {safe_name}: {meta['words']:,} words, "
              f"{meta['pages']} pages, {meta['chars']:,} chars"
              f"{' [OCR]' if is_ocr else ''}")

        return JSONResponse({
            "file_path":   str(save_path),
            "action":      action,
            "output_path": str(OUTPUT_DIR / (save_path.stem + f"_{action}.txt")),
            "allowed":     True,
            "file_info": {
                "name":      safe_name,
                "extension": save_path.suffix.lower(),
                "size_kb":   meta["size_kb"],
                "supported": save_path.suffix.lower() in SUPPORTED_EXTENSIONS,
                "pages":     meta["pages"],
                "words":     meta["words"],
                "is_ocr":    is_ocr,
            },
        })

    except Exception as e:
        return JSONResponse({
            "allowed": False, "error": str(e),
            "file_path": "", "action": action, "output_path": "",
        })


@app.post("/chat-stream")
async def chat_stream(file_path: str = Form(...), question: str = Form(...)):
    """Stream answer — sends FULL document text to AI, no chunking."""
    if not is_ollama_running():
        async def err():
            yield "data: Ollama is not running.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    full_path = _resolve_path(file_path)
    if not full_path.exists():
        async def err():
            yield "data: File not found. Please re-upload.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    key         = str(full_path)
    doc_text    = _get_doc_text(str(full_path))
    history     = _chat_history.get(key, [])
    doc_index   = _rag_index.get(key)  # None if not yet indexed (falls back gracefully)

    def generate():
        answer_tokens = []
        for token in stream_chat_with_history(doc_text, history, question,
                                              doc_index=doc_index):
            safe = token.replace("\n", "\\n")
            yield f"data: {safe}\n\n"
            answer_tokens.append(token)
        yield "data: [DONE]\n\n"

        # Save turn to history
        full_answer = "".join(answer_tokens).strip()
        if full_answer:
            history.append({"role": "user",      "content": question})
            history.append({"role": "assistant", "content": full_answer[:600]})
            _chat_history[key] = history[-20:]  # keep last 20 turns

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/summarize-stream")
async def summarize_stream(file_path: str = Form(...)):
    """Stream summary — sends full document, AI reads everything."""
    if not is_ollama_running():
        async def err():
            yield "data: Ollama is not running.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    full_path = _resolve_path(file_path)
    if not full_path.exists():
        async def err():
            yield "data: File not found.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    def generate():
        try:
            doc_text  = _get_doc_text(str(full_path))
            meta      = _doc_meta.get(str(full_path), {})
            doc_index = _rag_index.get(str(full_path))

            header = (
                f"Document: {meta.get('name', full_path.name)}\\n"
                f"Pages: {meta.get('pages', '?')} · "
                f"Words: {meta.get('words', 0):,}"
                + (f" · OCR: Yes" if meta.get('is_ocr') else "")
                + "\\n\\n"
            )
            yield f"data: {header}\n\n"

            for token in stream_summary(doc_text, doc_index=doc_index):
                safe = token.replace("\n", "\\n")
                yield f"data: {safe}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/legal-stream")
async def legal_stream(file_path: str = Form(...)):
    """
    Legal review — full document scan.
    Stage 1: Pattern extraction on complete text (instant).
    Stage 2: AI analysis on extracted sections.
    """
    full_path = _resolve_path(file_path)
    if not full_path.exists():
        async def err():
            yield "data: File not found.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    def generate():
        try:
            doc_text = _get_doc_text(str(full_path))
            meta     = _doc_meta.get(str(full_path), {})

            # Stage 1 — full document pattern extraction
            extraction = extract_fast(doc_text, pages_read=meta.get("pages", 1))

            header = (
                f"LEGAL REVIEW — {meta.get('name', full_path.name)}\\n"
                f"Pages: {meta.get('pages', '?')} · "
                f"Words: {meta.get('words', 0):,}\\n"
                f"{'─' * 44}\\n\\n"
                f"STAGE 1 — Pattern extraction (full document)\\n"
                f"Contract type : {extraction.contract_type}\\n"
                f"Parties found : {len(extraction.parties)}\\n"
                f"Key dates     : {len(extraction.dates)}\\n"
                f"Risk clauses  : {len(extraction.risk_clauses)}\\n"
                f"Obligations   : {len(extraction.obligations)}\\n"
                f"Governing law : {extraction.governing_law or 'Not detected'}\\n"
            )

            if extraction.parties:
                header += "\\nParties:\\n"
                for p in extraction.parties:
                    header += f"  • {p}\\n"

            if extraction.dates:
                header += "\\nKey dates:\\n"
                for d in extraction.dates:
                    header += f"  • {d}\\n"

            if extraction.risk_clauses:
                header += "\\nRisk clauses detected:\\n"
                for r in extraction.risk_clauses[:4]:
                    header += f"  ⚠  {r[:120]}...\\n"

            for line in header.split("\\n"):
                yield f"data: {line}\\n\n\n"

            # Stage 2 — AI analysis
            if is_ollama_running() and (extraction.risk_clauses or extraction.obligations):
                ai_prompt = build_ai_prompt(extraction)
                yield "data: \\n\n\n"
                yield "data: STAGE 2 — AI Risk Analysis\\n\n\n"
                yield "data: ─────────────────────────────────────\\n\n\n"
                for token in stream_legal_analyze(ai_prompt):
                    safe = token.replace("\n", "\\n")
                    yield f"data: {safe}\n\n"
            else:
                yield "data: (Start Ollama for AI risk analysis)\\n\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})




@app.post("/compare")
async def compare(
    file_path_a: str = Form(...),
    file_path_b: str = Form(...),
):
    """Compare two contracts — instant, no AI needed."""
    try:
        path_a = _resolve_path(file_path_a)
        path_b = _resolve_path(file_path_b)
        if not path_a.exists():
            return JSONResponse({"success": False, "error": f"File A not found: {file_path_a}"})
        if not path_b.exists():
            return JSONResponse({"success": False, "error": f"File B not found: {file_path_b}"})

        text_a = _get_doc_text(str(path_a))
        text_b = _get_doc_text(str(path_b))
        result = compare_contracts(text_a, text_b, path_a.name, path_b.name)
        report = format_comparison(result)

        # Save report
        out_path = OUTPUT_DIR / f"comparison_{path_a.stem}_vs_{path_b.stem}.txt"
        out_path.write_text(report, encoding="utf-8")
        _log_audit("compare", f"{path_a.name} vs {path_b.name}", True)

        return JSONResponse({
            "success":  True,
            "result":   result,
            "report":   report,
            "output":   str(out_path),
            "filename": out_path.name,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/extract-clauses")
async def extract_clauses_route(
    file_path:   str = Form(...),
    clause_type: str = Form("all"),
):
    """Extract specific clause types from a contract."""
    try:
        full_path = _resolve_path(file_path)
        if not full_path.exists():
            return JSONResponse({"success": False, "error": "File not found."})

        text    = _get_doc_text(str(full_path))
        clauses = extract_clauses(text, clause_type)
        report  = format_clauses(clauses, full_path.name)

        out_path = OUTPUT_DIR / f"{full_path.stem}_clauses.txt"
        out_path.write_text(report, encoding="utf-8")
        _log_audit("clause_extract", str(full_path), True)

        return JSONResponse({
            "success":  True,
            "clauses":  clauses,
            "report":   report,
            "output":   str(out_path),
            "filename": out_path.name,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/track-deadlines")
async def track_deadlines_route(file_path: str = Form(...)):
    """Extract all dates and obligations as a checklist."""
    try:
        full_path = _resolve_path(file_path)
        if not full_path.exists():
            return JSONResponse({"success": False, "error": "File not found."})

        text    = _get_doc_text(str(full_path))
        tracker = track_deadlines(text, full_path.name)
        report  = format_deadlines(tracker)

        out_path = OUTPUT_DIR / f"{full_path.stem}_deadlines.txt"
        out_path.write_text(report, encoding="utf-8")
        _log_audit("track_deadlines", str(full_path), True)

        return JSONResponse({
            "success":  True,
            "tracker":  tracker,
            "report":   report,
            "output":   str(out_path),
            "filename": out_path.name,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/generate-report")
async def generate_report_route(file_path: str = Form(...)):
    """Generate a professional DOCX report with all findings."""
    try:
        full_path = _resolve_path(file_path)
        if not full_path.exists():
            return JSONResponse({"success": False, "error": "File not found."})

        text       = _get_doc_text(str(full_path))
        meta       = _doc_meta.get(str(full_path), {})
        extraction = extract_fast(text, pages_read=meta.get("pages", 1))
        clauses    = extract_clauses(text, "all")
        tracker    = track_deadlines(text, full_path.name)

        out_name = f"{full_path.stem}_vaultmind_report.docx"
        out_path = str(OUTPUT_DIR / out_name)

        docx_path = generate_report(
            extraction  = extraction,
            file_name   = full_path.name,
            output_path = out_path,
            clauses     = clauses,
            tracker     = tracker,
        )

        _log_audit("generate_report", str(full_path), True)

        return JSONResponse({
            "success":  True,
            "output":   docx_path,
            "filename": out_name,
            "message":  "Professional DOCX report generated successfully.",
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})




# ── DRAFTING ASSISTANT ────────────────────────────────────────────────────────

@app.get("/draft/templates")
async def draft_templates():
    """Return available draft templates."""
    return JSONResponse({"templates": get_template_list()})


@app.get("/draft/fields/{template_id}")
async def draft_fields(template_id: str):
    """Return fields needed for a template."""
    try:
        return JSONResponse(get_template_fields(template_id))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/draft/generate")
async def draft_generate(request: Request):
    """Generate a draft document from template + fields."""
    try:
        body        = await request.json()
        template_id = body.get("template_id", "nda")
        fields      = body.get("fields", {})
        fmt         = body.get("format", "docx")  # "txt" or "docx"

        content_text = draft_document(template_id, fields)

        if fmt == "docx":
            out_path = save_draft_docx(content_text, template_id)
        else:
            out_path = save_draft(content_text, template_id)

        filename = Path(out_path).name
        _log_audit("draft_generate", template_id, True)

        return JSONResponse({
            "success":  True,
            "content":  content_text,
            "output":   out_path,
            "filename": filename,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


# ── MULTI-DOCUMENT ────────────────────────────────────────────────────────────

SESSION_ID = "default"  # Single-user app — one session


@app.post("/multi/add")
async def multi_add(file: UploadFile = File(...)):
    """Add a document to the multi-doc collection."""
    try:
        safe_name = Path(file.filename).name
        save_path = INPUT_DIR / safe_name
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        full_text = read_full_text(str(save_path))
        _doc_cache[str(save_path)]    = full_text
        _chat_history[str(save_path)] = []

        if SESSION_ID not in _multi_collections:
            _multi_collections[SESSION_ID] = DocCollection()

        add_document(_multi_collections[SESSION_ID], safe_name, full_text)
        summary = get_collection_summary(_multi_collections[SESSION_ID])

        return JSONResponse({
            "success":   True,
            "file_name": safe_name,
            "collection": summary,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/multi/remove")
async def multi_remove(file_name: str = Form(...)):
    """Remove a document from the multi-doc collection."""
    if SESSION_ID in _multi_collections:
        from multi_doc import remove_document as _rm
        _rm(_multi_collections[SESSION_ID], file_name)
    return JSONResponse({"success": True})


@app.get("/multi/status")
async def multi_status():
    """Return current multi-doc collection status."""
    if SESSION_ID not in _multi_collections:
        return JSONResponse({"count": 0, "names": [], "total_words": 0})
    return JSONResponse(get_collection_summary(_multi_collections[SESSION_ID]))


@app.post("/multi/chat-stream")
async def multi_chat_stream(question: str = Form(...)):
    """Stream answer from multi-document collection."""
    if not is_ollama_running():
        async def err():
            yield "data: Ollama is not running.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    collection = _multi_collections.get(SESSION_ID)
    if not collection or not collection.docs:
        async def err():
            yield "data: No documents loaded. Add documents first.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    context  = get_multi_context(collection, question)
    history  = _chat_history.get(f"multi_{SESSION_ID}", [])
    conflicts = find_conflicts(collection)

    def generate():
        answer_tokens = []
        for token in stream_chat_with_history(context, history, question):
            safe = token.replace("\n", "\\n")
            yield f"data: {safe}\n\n"
            answer_tokens.append(token)

        if conflicts:
            conflict_note = "\n\n⚠ Conflicts detected: " + "; ".join(conflicts)
            yield f"data: {conflict_note.replace(chr(10), chr(92)+'n')}\n\n"

        yield "data: [DONE]\n\n"

        full_answer = "".join(answer_tokens).strip()
        if full_answer:
            history.append({"role": "user",      "content": question})
            history.append({"role": "assistant", "content": full_answer[:600]})
            _chat_history[f"multi_{SESSION_ID}"] = history[-20:]

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/multi/clear")
async def multi_clear():
    """Clear the multi-doc collection."""
    _multi_collections.pop(SESSION_ID, None)
    _chat_history.pop(f"multi_{SESSION_ID}", None)
    return JSONResponse({"success": True})



SESSION_ID = "default"  # Single-user app — one session


@app.post("/chat-reset")
async def chat_reset(file_path: str = Form(...)):
    key = str(Path(file_path))
    _chat_history.pop(key, None)
    alt = str(INPUT_DIR / Path(file_path).name)
    _chat_history.pop(alt, None)
    return JSONResponse({"cleared": True})


@app.post("/execute")
async def execute(file_path: str = Form(...), action: str = Form("summarize")):
    result = handle_file(file_path, action)
    result["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _log_audit(action, file_path, result["success"])
    return JSONResponse(result)


@app.get("/download/{filename}")
async def download(filename: str):
    safe_name = Path(filename).name
    file_path = OUTPUT_DIR / safe_name
    if not file_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(str(file_path), filename=safe_name)


@app.get("/audit")
async def audit_log():
    if not AUDIT_FILE.exists():
        return JSONResponse({"log": []})
    with open(AUDIT_FILE, "r") as f:
        lines = f.readlines()
    return JSONResponse({"log": lines[-50:]})


@app.get("/memory")
async def memory_state():
    return JSONResponse(load_memory())


@app.get("/debug-chat")
async def debug_chat(file_path: str = ""):
    full_path = _resolve_path(file_path) if file_path else None
    input_files = [str(f) for f in INPUT_DIR.iterdir()] if INPUT_DIR.exists() else []
    key = str(full_path) if full_path else ""
    cached = key in _doc_cache
    return JSONResponse({
        "ollama_running":   is_ollama_running(),
        "models":           list_models(),
        "file_cached":      cached,
        "doc_chars":        len(_doc_cache.get(key, "")),
        "files_in_input":   input_files,
    })


# ══════════════════════════════════════════════════════════════
# v1.0 NEW FEATURES
# ══════════════════════════════════════════════════════════════

@app.post("/detect-ambiguity")
async def detect_ambiguity_route(file_path: str = Form(...)):
    """Scan document for ambiguous legal language — instant, no AI."""
    try:
        full_path = _resolve_path(file_path)
        if not full_path.exists():
            return JSONResponse({"success": False, "error": "File not found."})
        text   = _get_doc_text(str(full_path))
        result = detect_ambiguity(text, file_name=full_path.name)
        report = format_ambiguity(result)
        out_path = OUTPUT_DIR / f"{full_path.stem}_ambiguity.txt"
        out_path.write_text(report, encoding="utf-8")
        _log_audit("detect_ambiguity", str(full_path), True)
        return JSONResponse({
            "success":  True,
            "result":   result,
            "report":   report,
            "filename": out_path.name,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/extract-timeline")
async def extract_timeline_route(file_path: str = Form(...)):
    """Extract a chronological timeline of events from a contract."""
    try:
        full_path = _resolve_path(file_path)
        if not full_path.exists():
            return JSONResponse({"success": False, "error": "File not found."})
        text   = _get_doc_text(str(full_path))
        result = extract_timeline(text, file_name=full_path.name)
        report = format_timeline(result)
        out_path = OUTPUT_DIR / f"{full_path.stem}_timeline.txt"
        out_path.write_text(report, encoding="utf-8")
        _log_audit("extract_timeline", str(full_path), True)
        return JSONResponse({
            "success":  True,
            "result":   result,
            "report":   report,
            "filename": out_path.name,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/clause-library")
async def clause_library_get(category: str = "all", query: str = ""):
    """Get all saved clauses, with optional category filter or search."""
    try:
        if query:
            clauses = search_clauses(query)
        else:
            clauses = get_all_clauses(category=None if category == "all" else category)
        return JSONResponse({
            "success": True,
            "clauses": clauses,
            "count":   len(clauses),
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/clause-library/save")
async def clause_library_save(request: Request):
    """Save a clause to the local library."""
    try:
        body        = await request.json()
        text        = body.get("text", "").strip()
        category    = body.get("category", "general")
        title       = body.get("title", "")
        source_file = body.get("source_file", "")
        tags        = body.get("tags", [])
        if not text:
            return JSONResponse({"success": False, "error": "Clause text required."})
        clause = save_clause(text=text, category=category,
                             title=title, source_file=source_file, tags=tags)
        _log_audit("save_clause", source_file or "manual", True)
        return JSONResponse({"success": True, "clause": clause})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/clause-library/{clause_id}")
async def clause_library_get_one(clause_id: str):
    """Get a single clause by ID."""
    try:
        from clause_library import increment_usage
        clause = get_clause_by_id(clause_id)
        if not clause:
            return JSONResponse({"success": False, "error": "Clause not found."})
        increment_usage(clause_id)
        return JSONResponse({"success": True, "clause": clause,
                             "formatted": format_clause_detail(clause)})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.delete("/clause-library/{clause_id}")
async def clause_library_delete(clause_id: str):
    """Delete a clause from the library."""
    try:
        deleted = delete_clause(clause_id)
        if not deleted:
            return JSONResponse({"success": False, "error": "Clause not found."})
        return JSONResponse({"success": True, "message": f"Clause {clause_id} deleted."})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/clause-library-stats")
async def clause_library_stats_route():
    """Return clause library statistics."""
    try:
        return JSONResponse({"success": True, "stats": library_stats()})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/clause-categories")
async def clause_categories_route():
    """Return valid clause categories."""
    return JSONResponse({"success": True, "categories": CLAUSE_CATEGORIES})


# ══════════════════════════════════════════════════════════════
# v1.1 ZERO-AI DOCUMENT ANALYSIS — 12 NEW FEATURES
# All routes follow the same pattern:
#   POST with file_path form field → JSON response with result + report + filename
# ══════════════════════════════════════════════════════════════

def _analysis_route(file_path_str: str, analyzer_fn, formatter_fn,
                    log_name: str, out_suffix: str):
    """Shared helper for all doc_analyzer routes."""
    full_path = _resolve_path(file_path_str)
    if not full_path.exists():
        return {"success": False, "error": "File not found."}
    text   = _get_doc_text(str(full_path))
    result = analyzer_fn(text, file_name=full_path.name)
    report = formatter_fn(result)
    out_path = OUTPUT_DIR / f"{full_path.stem}_{out_suffix}.txt"
    out_path.write_text(report, encoding="utf-8")
    _log_audit(log_name, str(full_path), True)
    return {"success": True, "result": result, "report": report, "filename": out_path.name}


@app.post("/analyze/defined-terms")
async def analyze_defined_terms(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, defined_terms_map, format_defined_terms,
            "defined_terms", "defined_terms"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/monetary")
async def analyze_monetary(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, monetary_scanner, format_monetary,
            "monetary_scan", "monetary"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/cross-references")
async def analyze_cross_references(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, cross_reference_checker, format_cross_references,
            "cross_refs", "cross_refs"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/term-usage")
async def analyze_term_usage(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, defined_term_usage_checker, format_term_usage,
            "term_usage", "term_usage"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/statistics")
async def analyze_statistics(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, document_statistics, format_statistics,
            "doc_stats", "statistics"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/signatures")
async def analyze_signatures(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, signature_block_extractor, format_signature_blocks,
            "signatures", "signatures"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/notices")
async def analyze_notices(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, notice_requirements, format_notice_requirements,
            "notices", "notices"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/termination")
async def analyze_termination(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, termination_trigger_map, format_termination_triggers,
            "termination", "termination"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/liability")
async def analyze_liability(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, liability_cap_finder, format_liability_caps,
            "liability", "liability"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/boilerplate")
async def analyze_boilerplate(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, boilerplate_detector, format_boilerplate,
            "boilerplate", "boilerplate"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/obligations")
async def analyze_obligations(file_path: str = Form(...)):
    try:
        return JSONResponse(_analysis_route(
            file_path, party_obligation_matrix, format_obligation_matrix,
            "obligations", "obligations"))
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/redline")
async def analyze_redline(
    file_path_a: str = Form(...),
    file_path_b: str = Form(...),
):
    """Word-level diff between two document versions."""
    try:
        path_a = _resolve_path(file_path_a)
        path_b = _resolve_path(file_path_b)
        if not path_a.exists():
            return JSONResponse({"success": False, "error": f"File A not found."})
        if not path_b.exists():
            return JSONResponse({"success": False, "error": f"File B not found."})
        text_a = _get_doc_text(str(path_a))
        text_b = _get_doc_text(str(path_b))
        result = redline_diff(text_a, text_b, path_a.name, path_b.name)
        report = format_redline_summary(result)
        out_path = OUTPUT_DIR / f"redline_{path_a.stem}_vs_{path_b.stem}.txt"
        out_path.write_text(report, encoding="utf-8")
        _log_audit("redline", f"{path_a.name} vs {path_b.name}", True)
        return JSONResponse({
            "success":  True,
            "result":   {k: v for k, v in result.items() if k != "segments"},
            "report":   report,
            "filename": out_path.name,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/analyze/full")
async def analyze_full(file_path: str = Form(...)):
    """Run all 11 single-doc analyses at once and return combined JSON."""
    try:
        full_path = _resolve_path(file_path)
        if not full_path.exists():
            return JSONResponse({"success": False, "error": "File not found."})
        text    = _get_doc_text(str(full_path))
        results = run_full_analysis(text, file_name=full_path.name)
        _log_audit("full_analysis", str(full_path), True)
        return JSONResponse({"success": True, "results": results})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})
