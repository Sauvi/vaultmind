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
from file_reader import read_document, read_full_text, SUPPORTED_EXTENSIONS
from legal_extractor import extract_fast, build_ai_prompt, format_report
from drafting import (
    get_template_list, get_template_fields,
    draft_document, save_draft, save_draft_docx
)
from multi_doc import (
    DocCollection, add_document, get_multi_context,
    get_collection_summary, find_conflicts
)
from drafting import (
    get_template_list, get_template_fields,
    draft_document, save_draft, save_draft_docx,
)
from multi_doc import (
    DocCollection, add_document, get_multi_context,
    get_collection_summary, find_conflicts,
)
from features import (
    compare_contracts, format_comparison,
    extract_clauses, format_clauses,
    track_deadlines, format_deadlines,
    generate_report,
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
    return JSONResponse(results)


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), action: str = Form("summarize")):
    """Upload file — read full text and cache it."""
    try:
        safe_name = Path(file.filename).name
        save_path = INPUT_DIR / safe_name

        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Read and cache full document text
        key       = str(save_path)
        full_text = read_full_text(str(save_path))
        doc_meta  = read_document(str(save_path))

        _doc_cache[key]    = full_text
        _chat_history[key] = []  # reset conversation
        _doc_meta[key] = {
            "name":       safe_name,
            "pages":      doc_meta.pages,
            "words":      len(full_text.split()),
            "chars":      len(full_text),
            "size_kb":    round(save_path.stat().st_size / 1024, 1),
            "extension":  save_path.suffix.lower(),
        }

        meta = _doc_meta[key]
        print(f"📄 Loaded {safe_name}: {meta['words']:,} words, "
              f"{meta['pages']} pages, {meta['chars']:,} chars")

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

    def generate():
        answer_tokens = []
        for token in stream_chat_with_history(doc_text, history, question):
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
            doc_text = _get_doc_text(str(full_path))
            meta     = _doc_meta.get(str(full_path), {})

            header = (
                f"Document: {meta.get('name', full_path.name)}\\n"
                f"Pages: {meta.get('pages', '?')} · "
                f"Words: {meta.get('words', 0):,}\\n\\n"
            )
            yield f"data: {header}\n\n"

            for token in stream_summary(doc_text):
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



SESSION_ID = "default"


@app.get("/draft/templates")
async def draft_templates():
    return JSONResponse({"templates": get_template_list()})


@app.get("/draft/fields/{template_id}")
async def draft_fields(template_id: str):
    try:
        return JSONResponse(get_template_fields(template_id))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/draft/generate")
async def draft_generate(request: Request):
    try:
        body        = await request.json()
        template_id = body.get("template_id", "nda")
        fields      = body.get("fields", {})
        fmt         = body.get("format", "docx")
        content_txt = draft_document(template_id, fields)
        if fmt == "docx":
            out_path = save_draft_docx(content_txt, template_id)
        else:
            out_path = save_draft(content_txt, template_id)
        filename = Path(out_path).name
        _log_audit("draft_generate", template_id, True)
        return JSONResponse({"success": True, "content": content_txt,
                             "output": out_path, "filename": filename})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/multi/add")
async def multi_add(file: UploadFile = File(...)):
    try:
        safe_name = Path(file.filename).name
        save_path = INPUT_DIR / safe_name
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        full_text = read_full_text(str(save_path))
        _doc_cache[str(save_path)] = full_text
        if SESSION_ID not in _multi_collections:
            _multi_collections[SESSION_ID] = DocCollection()
        add_document(_multi_collections[SESSION_ID], safe_name, full_text)
        summary = get_collection_summary(_multi_collections[SESSION_ID])
        return JSONResponse({"success": True, "file_name": safe_name, "collection": summary})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/multi/status")
async def multi_status():
    if SESSION_ID not in _multi_collections:
        return JSONResponse({"count": 0, "names": [], "total_words": 0})
    return JSONResponse(get_collection_summary(_multi_collections[SESSION_ID]))


@app.post("/multi/chat-stream")
async def multi_chat_stream(question: str = Form(...)):
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
    def generate():
        answer_tokens = []
        for token in stream_chat_with_history(context, history, question):
            safe = token.replace("\n", "\\n")
            yield f"data: {safe}\n\n"
            answer_tokens.append(token)
        yield "data: [DONE]\n\n"
        full_answer = "".join(answer_tokens).strip()
        if full_answer:
            history.append({"role": "user",      "content": question})
            history.append({"role": "assistant", "content": full_answer[:600]})
            _chat_history[f"multi_{SESSION_ID}"] = history[-20:]
    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/multi/clear")
async def multi_clear():
    _multi_collections.pop(SESSION_ID, None)
    _chat_history.pop(f"multi_{SESSION_ID}", None)
    return JSONResponse({"success": True})


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
