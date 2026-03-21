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
from ollama_engine import is_ollama_running, list_models, chat_with_document, stream_chat, warmup_model, stream_legal_analyze
from file_reader import read_file, read_document, SUPPORTED_EXTENSIONS

# ── Dirs ──────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
INPUT_DIR    = BASE_DIR / "workspace" / "input"
OUTPUT_DIR   = BASE_DIR / "workspace" / "output"
STATIC_DIR   = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
AUDIT_FILE   = BASE_DIR / "audit.log"

for d in [INPUT_DIR, OUTPUT_DIR, STATIC_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="VaultMind", version="0.3.0")


@app.on_event("startup")
async def startup():
    """Pre-load Ollama model into RAM on server start — prevents cold-load hang on first request."""
    import asyncio
    import threading
    def _warmup():
        if is_ollama_running():
            print("🔥 VaultMind: warming up AI model...")
            ok = warmup_model()
            print("✅ AI model ready." if ok else "⚠️  Warmup failed — model will load on first use.")
        else:
            print("⚠️  Ollama not running — start Ollama for AI features.")
    # Run warmup in background thread so server starts instantly
    threading.Thread(target=_warmup, daemon=True).start()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))



@app.get("/check-deps")
async def check_deps():
    """Check if optional dependencies are installed."""
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
        import fastapi
        results["fastapi"] = f"✅ installed (v{fastapi.__version__})"
    except ImportError:
        results["fastapi"] = "❌ missing"
    return JSONResponse(results)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    memory = load_memory()
    output_files = sorted(os.listdir(OUTPUT_DIR), reverse=True)[:10]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "memory": memory,
        "output_files": output_files,
    })


@app.get("/status")
async def status():
    """Returns Ollama health + available models — used by the UI status badge."""
    running = is_ollama_running()
    models  = list_models() if running else []
    return JSONResponse({
        "ollama": running,
        "models": models,
    })


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), action: str = Form("summarize")):
    try:
        safe_name = Path(file.filename).name
        ext = Path(safe_name).suffix.lower()
        save_path = INPUT_DIR / safe_name
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        plan = get_proposed_plan(str(save_path), action)
        return JSONResponse(plan)
    except Exception as e:
        return JSONResponse({
            "allowed": False,
            "error": str(e),
            "file_path": "",
            "action": action,
            "output_path": "",
        })


@app.post("/execute")
async def execute(file_path: str = Form(...), action: str = Form("summarize")):
    result = handle_file(file_path, action)
    result["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(AUDIT_FILE, "a") as log:
        status_str = "OK" if result["success"] else "FAIL"
        log.write(f"[{result['timestamp']}] {status_str} | {action} | {file_path}\n")
    return JSONResponse(result)


@app.post("/chat")
async def chat(file_path: str = Form(...), question: str = Form(...)):
    """Answer a question about a specific document using Ollama."""
    if not is_ollama_running():
        return JSONResponse({
            "success": False,
            "answer": "Ollama is not running. Please start Ollama and refresh."
        })

    # Try the path as-is first, then fall back to INPUT_DIR
    full_path = Path(file_path)
    if not full_path.exists():
        full_path = INPUT_DIR / Path(file_path).name
    if not full_path.exists():
        return JSONResponse({
            "success": False,
            "answer": f"File not found at: {file_path}. Please re-upload the file."
        })

    try:
        _doc = read_document(str(full_path))
        doc_content = _doc.text
        if not doc_content.strip():
            return JSONResponse({"success": False, "answer": "The file appears to be empty."})

        answer = chat_with_document(doc_content, question)
        return JSONResponse({
            "success": True,
            "answer": answer,
            "chars_read": len(doc_content)   # helpful for debugging
        })
    except ConnectionError as e:
        return JSONResponse({"success": False, "answer": str(e)})
    except Exception as e:
        return JSONResponse({"success": False, "answer": f"Error: {str(e)}"})


@app.get("/debug-chat")
async def debug_chat(file_path: str = ""):
    """Debug endpoint — shows what the chat endpoint sees."""
    full_path = Path(file_path) if file_path else None
    input_files = [str(f) for f in INPUT_DIR.iterdir()] if INPUT_DIR.exists() else []
    return JSONResponse({
        "ollama_running": is_ollama_running(),
        "models": list_models(),
        "file_path_received": file_path,
        "file_exists": full_path.exists() if full_path else False,
        "files_in_input_dir": input_files,
    })



@app.post("/chat-stream")
async def chat_stream(file_path: str = Form(...), question: str = Form(...)):
    """Stream chat answer token by token — makes responses feel instant."""
    if not is_ollama_running():
        async def err():
            yield "data: Ollama is not running. Please start Ollama.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    # Resolve file path
    full_path = Path(file_path)
    if not full_path.exists():
        full_path = INPUT_DIR / Path(file_path).name
    if not full_path.exists():
        async def err():
            yield f"data: File not found. Please re-upload.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    try:
        _doc = read_document(str(full_path))
        doc_content = _doc.text
    except Exception as e:
        async def err():
            yield f"data: Could not read file: {str(e)}\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    def generate():
        """Yield SSE-formatted tokens from Ollama."""
        for token in stream_chat(doc_content, question):
            # Escape newlines for SSE format
            safe = token.replace("\n", "\\n")
            yield f"data: {safe}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})



@app.post("/legal-stream")
async def legal_stream(file_path: str = Form(...)):
    """
    Stream legal review results — Stage 1 instant, Stage 2 streamed.
    Shows pattern extraction immediately, then streams AI analysis.
    """
    from legal_extractor import extract_fast, build_ai_prompt, format_report
    from file_reader import read_file

    full_path = Path(file_path)
    if not full_path.exists():
        full_path = INPUT_DIR / Path(file_path).name
    if not full_path.exists():
        async def err():
            yield "data: File not found.\n\n"
        return StreamingResponse(err(), media_type="text/event-stream")

    def generate():
        try:
            _doc = read_document(str(full_path))
            content = _doc.text
            # Stage 1 — instant extraction
            extraction = extract_fast(content)

            # Stream stage 1 results immediately
            stage1 = f"""STAGE 1 COMPLETE — Pattern extraction (instant)\n
Document type : {extraction.contract_type}\n
Parties found : {len(extraction.parties)}\n
Dates found   : {len(extraction.dates)}\n
Risk clauses  : {len(extraction.risk_clauses)}\n
Obligations   : {len(extraction.obligations)}\n
{'─' * 38}\n
Running AI analysis on extracted sections...\n
"""
            for line in stage1.split("\n"):
                yield f"data: {line}\n\n"

            # Stage 2 — stream AI analysis
            if is_ollama_running() and (extraction.risk_clauses or extraction.obligations):
                ai_prompt = build_ai_prompt(extraction)
                yield "data: \n\n"
                yield "data: STAGE 2 — AI Risk Analysis\n\n"
                yield "data: ─────────────────────────────────────\n\n"
                for token in stream_legal_analyze(ai_prompt):
                    safe = token.replace("\n", "\\n")
                    yield f"data: {safe}\n\n"
            else:
                yield "data: \n\n"
                yield "data: (Start Ollama for AI risk analysis)\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
