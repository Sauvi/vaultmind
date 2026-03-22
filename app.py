"""
app.py — VaultMind v0.6
RAG-powered document AI.
Upload once → index full document → chat, summarize, legal review all use the index.
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
from rag_engine import index_document, get_context, get_summary_context, get_stats, DocumentIndex
from legal_extractor import extract_fast, build_ai_prompt, format_report

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
# Key: file_path string
_doc_index:    dict[str, DocumentIndex] = {}   # RAG index per file
_chat_history: dict[str, list[dict]]   = {}   # conversation history per file

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="VaultMind", version="0.6.0")


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


# ── Helper ────────────────────────────────────────────────────────────────────

def _resolve_path(file_path: str) -> Path:
    """Resolve file path — try as-is, then relative to INPUT_DIR."""
    p = Path(file_path)
    if p.exists():
        return p
    alt = INPUT_DIR / p.name
    if alt.exists():
        return alt
    return p  # return even if not found — caller handles error


def _get_or_build_index(file_path: str) -> DocumentIndex:
    """Return cached index or build a new one."""
    key = str(Path(file_path))
    if key not in _doc_index:
        full_path = _resolve_path(file_path)
        # Use read_full_text — no truncation for indexing
        full_text   = read_full_text(str(full_path))
        # Also get page count from read_document
        doc_meta    = read_document(str(full_path))
        idx = index_document(
            text        = full_text,
            file_name   = full_path.name,
            total_pages = doc_meta.pages,
        )
        _doc_index[key] = idx
        print(f"📚 Indexed {full_path.name}: {len(idx.chunks)} chunks, {idx.total_words} words")
    return _doc_index[key]


def _log_audit(action: str, file_path: str, success: bool):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "OK" if success else "FAIL"
    with open(AUDIT_FILE, "a") as f:
        f.write(f"[{ts}] {status} | {action} | {file_path}\n")


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
    models  = list_models() if running else []
    return JSONResponse({"ollama": running, "models": models})


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
    """
    Upload file + immediately build RAG index.
    Index is stored in memory — all subsequent operations use it.
    """
    try:
        safe_name = Path(file.filename).name
        save_path = INPUT_DIR / safe_name

        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Build RAG index on upload — use full text, no truncation
        key       = str(save_path)
        full_text = read_full_text(str(save_path))
        doc_meta  = read_document(str(save_path))
        idx = index_document(
            text        = full_text,
            file_name   = safe_name,
            total_pages = doc_meta.pages,
        )
        _doc_index[key] = idx

        # Reset chat history for this file
        _chat_history[key] = []

        stats = get_stats(idx)
        print(f"📚 Indexed {safe_name}: {stats['chunks']} chunks, "
              f"{stats['total_words']} words, {stats['total_pages']} pages")

        return JSONResponse({
            "file_path":   str(save_path),
            "action":      action,
            "output_path": str(OUTPUT_DIR / (save_path.stem + f"_{action}.txt")),
            "allowed":     True,
            "file_info": {
                "name":      safe_name,
                "extension": save_path.suffix.lower(),
                "size_kb":   round(save_path.stat().st_size / 1024, 1),
                "supported": save_path.suffix.lower() in SUPPORTED_EXTENSIONS,
            },
            "index_stats": stats,
        })

    except Exception as e:
        return JSONResponse({
            "allowed": False,
            "error":   str(e),
            "file_path": "", "action": action, "output_path": "",
        })


@app.post("/chat-stream")
async def chat_stream(file_path: str = Form(...), question: str = Form(...)):
    """
    Stream chat answer using RAG — finds relevant chunks, answers from those.
    Includes conversation history for follow-up questions.
    """
    if not is_ollama_running():
        async def err():
            yield "data: Ollama is not running. Please start Ollama.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    full_path = _resolve_path(file_path)
    if not full_path.exists():
        async def err():
            yield "data: File not found. Please re-upload.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    try:
        # Get or build index
        idx = _get_or_build_index(str(full_path))

        # Retrieve relevant context for this question
        context = get_context(idx, question)

        # Get conversation history
        key     = str(full_path)
        history = _chat_history.get(key, [])

    except Exception as e:
        async def err():
            yield f"data: Error preparing context: {str(e)}\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    def generate():
        answer_tokens = []
        for token in stream_chat_with_history(context, history, question):
            safe = token.replace("\n", "\\n")
            yield f"data: {safe}\n\n"
            answer_tokens.append(token)
        yield "data: [DONE]\n\n"

        # Save to history
        full_answer = "".join(answer_tokens).strip()
        if full_answer:
            history.append({"role": "user",      "content": question})
            history.append({"role": "assistant", "content": full_answer[:500]})
            # Cap history at 20 turns
            if len(history) > 20:
                _chat_history[key] = history[-20:]
            else:
                _chat_history[key] = history

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/summarize-stream")
async def summarize_stream(file_path: str = Form(...)):
    """Stream AI summary using representative chunks from across the document."""
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
            idx     = _get_or_build_index(str(full_path))
            context = get_summary_context(idx)
            stats   = get_stats(idx)

            # Stream header
            header = (f"Document: {stats['file_name']} · "
                      f"{stats['total_pages']} pages · "
                      f"{stats['total_words']:,} words · "
                      f"{stats['chunks']} indexed chunks\\n\\n")
            yield f"data: {header}\n\n"

            for token in stream_summary(context):
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
    Stream legal review.
    Stage 1: Pattern extraction on FULL document (all chunks).
    Stage 2: AI analysis on extracted sections only.
    """
    full_path = _resolve_path(file_path)
    if not full_path.exists():
        async def err():
            yield "data: File not found.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    def generate():
        try:
            # Use full_text from index for legal extraction — scans everything
            idx      = _get_or_build_index(str(full_path))
            full_doc = idx.full_text   # complete document, not truncated

            # Stage 1 — pattern extraction on full document
            extraction = extract_fast(full_doc, pages_read=idx.total_pages)
            stats      = get_stats(idx)

            header = (
                f"LEGAL REVIEW — {stats['file_name']}\\n"
                f"Pages: {stats['total_pages']} · "
                f"Words: {stats['total_words']:,} · "
                f"Chunks indexed: {stats['chunks']}\\n"
                f"{'─' * 40}\\n\\n"
                f"STAGE 1 — Pattern extraction (full document)\\n"
                f"Contract type  : {extraction.contract_type}\\n"
                f"Parties found  : {len(extraction.parties)}\\n"
                f"Key dates      : {len(extraction.dates)}\\n"
                f"Risk clauses   : {len(extraction.risk_clauses)}\\n"
                f"Obligations    : {len(extraction.obligations)}\\n"
                f"Governing law  : {extraction.governing_law or 'Not detected'}\\n"
            )

            if extraction.parties:
                header += f"\\nParties:\\n"
                for p in extraction.parties:
                    header += f"  • {p}\\n"

            if extraction.dates:
                header += f"\\nKey dates:\\n"
                for d in extraction.dates:
                    header += f"  • {d}\\n"

            for line in header.split("\\n"):
                yield f"data: {line}\\n\n\n"

            # Stage 2 — AI on extracted sections
            if is_ollama_running() and (extraction.risk_clauses or extraction.obligations):
                ai_prompt = build_ai_prompt(extraction)
                yield "data: \\n\n\n"
                yield "data: STAGE 2 — AI Risk Analysis\\n\n\n"
                yield "data: ─────────────────────────────────────\\n\n\n"
                for token in stream_legal_analyze(ai_prompt):
                    safe = token.replace("\n", "\\n")
                    yield f"data: {safe}\n\n"
            else:
                yield "data: \\n\n\n"
                yield "data: (Start Ollama for AI risk analysis)\\n\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/chat-reset")
async def chat_reset(file_path: str = Form(...)):
    """Clear conversation history — keep document index."""
    key = str(Path(file_path))
    _chat_history.pop(key, None)
    alt = str(INPUT_DIR / Path(file_path).name)
    _chat_history.pop(alt, None)
    return JSONResponse({"cleared": True})


@app.post("/execute")
async def execute(file_path: str = Form(...), action: str = Form("summarize")):
    """Save action result to file (for download)."""
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
    idx = _doc_index.get(key)
    return JSONResponse({
        "ollama_running": is_ollama_running(),
        "models": list_models(),
        "file_path_received": file_path,
        "file_exists": full_path.exists() if full_path else False,
        "files_in_input_dir": input_files,
        "index_stats": get_stats(idx) if idx else None,
    })
