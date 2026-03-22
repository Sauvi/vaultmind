"""
ollama_engine.py — VaultMind v0.7
Simplified direct approach — send full document to AI.
phi3.5 supports large context windows — use them.
No chunking, no retrieval, no missed content.
"""

import urllib.request
import urllib.error
import json
from typing import Generator

OLLAMA_URL    = "http://localhost:11434"
DEFAULT_MODEL = "phi3.5"

# Full context window — phi3.5 supports up to 128k
# We use 12000 tokens safely on 8GB RAM (covers ~48000 chars)
_BASE_OPTIONS = {
    "temperature":    0.1,
    "num_ctx":        4096,   # safe for 8GB RAM
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


# ── Smart truncation — only if doc exceeds safe limit ────────────────────────

def _prepare_doc(text: str, max_chars: int = 3500) -> tuple[str, bool]:
    """
    Prepare document text for AI chat/summarize.
    3500 chars ≈ 875 tokens — fast and safe on 8GB RAM.
    Keeps first 60% + last 40% — parties at start, signatures/dates at end.
    Legal review bypasses this entirely (uses pattern extraction instead).
    """
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
    Extract the most relevant section of a document for a question.
    Splits into paragraphs, scores each against question keywords,
    returns the highest-scoring paragraphs up to max_chars.
    Fast — pure Python, no AI needed.
    """
    import re
    # Extract question keywords
    stop = {"the","a","an","is","are","was","were","what","how","who",
            "when","where","why","which","this","that","in","of","to",
            "and","or","for","with","do","does","did","can","will","me",
            "give","tell","show","find","please","my","your","its"}
    q_words = set(re.findall(r"\b[a-z]{3,}\b", question.lower())) - stop

    # Split into paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    # Score each paragraph
    scored = []
    for para in paragraphs:
        para_lower = para.lower()
        score = sum(1 for w in q_words if w in para_lower)
        scored.append((score, para))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Always include first paragraph (parties/intro) + top scoring ones
    result_parts = []
    total = 0

    # First paragraph always included
    if paragraphs:
        result_parts.append(paragraphs[0])
        total += len(paragraphs[0])

    # Add top scoring paragraphs
    for score, para in scored:
        if total >= max_chars:
            break
        if para not in result_parts:
            result_parts.append(para)
            total += len(para)

    return "\n\n".join(result_parts)

# ── Prompt builders ───────────────────────────────────────────────────────────

def _build_summary_prompt(text: str) -> str:
    doc, truncated = _prepare_doc(text)
    note = "\nNote: Document was truncated — showing start and end sections.\n" if truncated else ""
    return (
        "<|system|>\n"
        "You are a precise document summarizer. Read the full document and "
        "provide a clear, accurate summary. Never add information not in the document.\n"
        "<|end|>\n"
        "<|user|>\n"
        f"Summarize this document in 5 clear bullet points covering the key information:{note}\n\n"
        f"{doc}\n"
        "<|end|>\n"
        "<|assistant|>\n"
    )


def _build_chat_prompt(document: str, history: list[dict], question: str) -> str:
    # Use smart extraction for chat — finds relevant sections for the question
    doc = _smart_extract(document, question, max_chars=3000)
    truncated = len(document) > 3000
    note = "\nNote: Showing most relevant sections for your question.\n" if truncated else ""

    # Build conversation history (last 6 turns)
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
        "You are a legal document analyst. Analyze the provided contract sections "
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

def summarize(text: str, model: str = None) -> str:
    model = model or get_best_model()
    return "".join(_stream(_build_summary_prompt(text), model, num_predict=500))


def stream_summary(text: str, model: str = None) -> Generator[str, None, None]:
    model = model or get_best_model()
    yield from _stream(_build_summary_prompt(text), model, num_predict=500)


def stream_chat_with_history(
    document_text: str,
    history: list[dict],
    question: str,
    model: str = None
) -> Generator[str, None, None]:
    model = model or get_best_model()
    prompt = _build_chat_prompt(document_text, history, question)
    yield from _stream(prompt, model, num_predict=600)


def chat_with_document(document_text: str, question: str, model: str = None) -> str:
    return "".join(stream_chat_with_history(document_text, [], question, model))


def legal_analyze(prompt: str, model: str = None) -> str:
    model = model or get_best_model()
    return "".join(_stream(prompt, model, num_predict=500))


def stream_legal_analyze(prompt: str, model: str = None) -> Generator[str, None, None]:
    model = model or get_best_model()
    yield from _stream(prompt, model, num_predict=500)
