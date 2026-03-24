"""
ollama_engine.py — VaultMind v1.2
Simplified direct approach — send full document to AI.
phi3.5 supports large context windows — use them.

UPGRADE in v1.2:
  Chat now uses real semantic RAG (rag_engine.py) instead of keyword _smart_extract().
  "exit the agreement" now correctly finds "termination" clauses.
  Summarisation uses RAG get_summary_context() for long documents.
"""

import urllib.request
import urllib.error
import json
from typing import Generator

OLLAMA_URL    = "http://localhost:11434"
DEFAULT_MODEL = "phi3.5"

_BASE_OPTIONS = {
    "temperature":    0.1,
    "num_ctx":        4096,
    "num_thread":     4,
    "repeat_penalty": 1.1,
}


# ── Model management ──────────────────────────────────────────────────────────

def is_ollama_running() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3)
        return True
    except Exception:
        return False


def list_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def get_best_model() -> str:
    models = list_models()
    if not models:
        return DEFAULT_MODEL
    priority = ["phi3.5", "phi3", "phi3-mini", "llama3.2", "mistral"]
    for preferred in priority:
        for m in models:
            if preferred in m.lower():
                return m
    return models[0]


def warmup_model(model: str = None) -> bool:
    model = model or get_best_model()
    try:
        body = json.dumps({
            "model": model, "prompt": "hi",
            "stream": False,
            "options": {"num_predict": 1, "num_ctx": 512}
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate", data=body,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return "response" in result
    except Exception:
        return False


# ── Core streaming ────────────────────────────────────────────────────────────

def _stream(prompt: str, model: str, num_predict: int = 500) -> Generator[str, None, None]:
    options = {**_BASE_OPTIONS, "num_predict": num_predict}
    body = json.dumps({
        "model":   model,
        "prompt":  prompt,
        "stream":  True,
        "options": options,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=body,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    continue
    except urllib.error.URLError as e:
        yield f"\n[Connection error — is Ollama running? {e}]"
    except Exception as e:
        yield f"\n[Error: {e}]"


# ── Context preparation ───────────────────────────────────────────────────────

def _prepare_context_for_chat(document_text: str, question: str,
                               doc_index=None) -> tuple[str, bool]:
    """
    Get context for chat.
    Priority:
      1. Semantic RAG index (best — finds relevant chunks by meaning)
      2. Keyword RAG index (fallback if semantic model not installed)
      3. Smart keyword extraction (legacy fallback)

    Returns (context_text, used_rag)
    """
    # Use RAG index if available
    if doc_index is not None:
        try:
            from rag_engine import get_context
            ctx = get_context(doc_index, question)
            return ctx, True
        except Exception as e:
            print(f"[Engine] RAG retrieval failed: {e} — using keyword fallback")

    # Legacy keyword extraction fallback
    ctx = _smart_extract(document_text, question, max_chars=3000)
    return ctx, False


def _prepare_context_for_summary(document_text: str, doc_index=None) -> str:
    """Get context for summarisation — samples document evenly."""
    if doc_index is not None:
        try:
            from rag_engine import get_summary_context
            return get_summary_context(doc_index)
        except Exception:
            pass

    # Fallback: head + tail of document
    doc, _ = _prepare_doc(document_text)
    return doc


def _prepare_doc(text: str, max_chars: int = 3500) -> tuple[str, bool]:
    """Legacy truncation for direct send (used when no RAG index)."""
    if len(text) <= max_chars:
        return text, False
    head = int(max_chars * 0.6)
    tail = max_chars - head
    truncated = (
        text[:head]
        + "\n\n[...middle section omitted...]\n\n"
        + text[-tail:]
    )
    return truncated, True


def _smart_extract(text: str, question: str, max_chars: int = 3000) -> str:
    """
    Legacy keyword-based extraction (kept as fallback when no RAG index).
    Scores paragraphs by word overlap with question.
    """
    import re
    stop = {"the","a","an","is","are","was","were","what","how","who",
            "when","where","why","which","this","that","in","of","to",
            "and","or","for","with","do","does","did","can","will","me",
            "give","tell","show","find","please","my","your","its"}
    q_words = set(re.findall(r"\b[a-z]{3,}\b", question.lower())) - stop

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    scored     = []
    for para in paragraphs:
        para_lower = para.lower()
        score      = sum(1 for w in q_words if w in para_lower)
        scored.append((score, para))

    scored.sort(key=lambda x: x[0], reverse=True)

    result_parts = []
    total = 0
    if paragraphs:
        result_parts.append(paragraphs[0])
        total += len(paragraphs[0])

    for score, para in scored:
        if total >= max_chars:
            break
        if para not in result_parts:
            result_parts.append(para)
            total += len(para)

    return "\n\n".join(result_parts)


# ── Prompt builders ───────────────────────────────────────────────────────────

def _build_summary_prompt(text: str, doc_index=None) -> str:
    doc = _prepare_context_for_summary(text, doc_index)
    note = "\nNote: Showing representative sections of the document.\n" if doc_index else ""
    return (
        "<|system|>\n"
        "You are a precise document summariser. Read the provided document sections and "
        "provide a clear, accurate summary. Never add information not in the document.\n"
        "<|end|>\n"
        "<|user|>\n"
        f"Summarise this document in 5 clear bullet points covering the key information:{note}\n\n"
        f"{doc}\n"
        "<|end|>\n"
        "<|assistant|>\n"
    )


def _build_chat_prompt(document: str, history: list[dict], question: str,
                       doc_index=None) -> str:
    doc, used_rag = _prepare_context_for_chat(document, question, doc_index)
    note = "\nNote: Showing the most relevant sections for your question.\n" if used_rag else ""

    recent = history[-6:] if len(history) > 6 else history
    history_text = ""
    for turn in recent:
        role = "You" if turn["role"] == "user" else "VaultMind"
        history_text += f"{role}: {turn['content']}\n"

    return (
        "<|system|>\n"
        "You are a document assistant. Answer questions using ONLY the document provided. "
        "Use conversation history to understand follow-up questions. "
        "Be direct, specific, and accurate. "
        "If the answer is not in the document, say so clearly.\n"
        "<|end|>\n"
        "<|user|>\n"
        f"DOCUMENT:{note}\n{doc}\n\n"
        + (f"CONVERSATION:\n{history_text}\n" if history_text else "")
        + f"QUESTION: {question}\n"
        "<|end|>\n"
        "<|assistant|>\n"
    )


def _build_legal_prompt(extracted_context: str, contract_type: str) -> str:
    return (
        "<|system|>\n"
        "You are a legal document analyst. Analyse the provided contract sections "
        "and give clear, professional insights. Use plain English.\n"
        "<|end|>\n"
        "<|user|>\n"
        f"Contract type: {contract_type}\n\n"
        f"{extracted_context}\n\n"
        "Provide:\n"
        "1. Key risks or red flags (3 bullet points)\n"
        "2. Main obligations summary (2-3 sentences)\n"
        "3. Overall risk level: LOW / MEDIUM / HIGH with brief reason\n"
        "<|end|>\n"
        "<|assistant|>\n"
    )


# ── Public functions ──────────────────────────────────────────────────────────

def summarize(text: str, model: str = None, doc_index=None) -> str:
    model = model or get_best_model()
    return "".join(_stream(_build_summary_prompt(text, doc_index), model, num_predict=500))


def stream_summary(text: str, model: str = None,
                   doc_index=None) -> Generator[str, None, None]:
    model = model or get_best_model()
    yield from _stream(_build_summary_prompt(text, doc_index), model, num_predict=500)


def stream_chat_with_history(
    document_text: str,
    history: list[dict],
    question: str,
    model: str = None,
    doc_index=None,
) -> Generator[str, None, None]:
    model  = model or get_best_model()
    prompt = _build_chat_prompt(document_text, history, question, doc_index)
    yield from _stream(prompt, model, num_predict=600)


def chat_with_document(document_text: str, question: str,
                       model: str = None, doc_index=None) -> str:
    return "".join(stream_chat_with_history(document_text, [], question, model, doc_index))


def legal_analyze(prompt: str, model: str = None) -> str:
    model = model or get_best_model()
    return "".join(_stream(prompt, model, num_predict=500))


def stream_legal_analyze(prompt: str, model: str = None) -> Generator[str, None, None]:
    model = model or get_best_model()
    yield from _stream(prompt, model, num_predict=500)
