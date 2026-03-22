"""
ollama_engine.py — VaultMind v0.5
Optimized for phi3.5 on 8GB RAM machines.
Smart prompts + minimal context = fast, accurate responses.
"""

import urllib.request
import urllib.error
import json
from typing import Generator

OLLAMA_URL    = "http://localhost:11434"
DEFAULT_MODEL = "phi3.5"

# ── Low-RAM inference options ─────────────────────────────────────────────────
_BASE_OPTIONS = {
    "temperature": 0.1,    # factual, not creative
    "num_ctx":     2048,   # small context window = low RAM
    "num_thread":  4,      # don't hog CPU
    "repeat_penalty": 1.1, # prevent repetitive output
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
    """Pick best available model. Priority: phi3.5 > phi3 > llama3.2 > first available."""
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
    """Pre-load model into RAM. Call once at startup."""
    model = model or get_best_model()
    try:
        body = json.dumps({
            "model": model, "prompt": "hi",
            "stream": False,
            "options": {**_BASE_OPTIONS, "num_predict": 1}
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

def _stream(prompt: str, model: str, num_predict: int = 250) -> Generator[str, None, None]:
    """Stream tokens from Ollama, one chunk at a time."""
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
        with urllib.request.urlopen(req, timeout=120) as resp:
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


# ── Prompt builders ───────────────────────────────────────────────────────────

def _build_summary_prompt(text: str) -> str:
    return (
        "<|system|>\n"
        "You are a precise document summarizer. "
        "Summarize ONLY what is in the document. "
        "Never add outside information.\n"
        "<|end|>\n"
        "<|user|>\n"
        f"Summarize this document in 5 clear bullet points:\n\n{text}\n"
        "<|end|>\n"
        "<|assistant|>\n"
    )


def _build_chat_prompt(document: str, question: str) -> str:
    return (
        "<|system|>\n"
        "You are a document assistant. "
        "Answer questions using ONLY the provided document. "
        "If the answer is not in the document, say exactly: "
        "'That information is not in this document.' "
        "Be direct and specific.\n"
        "<|end|>\n"
        "<|user|>\n"
        f"DOCUMENT:\n{document}\n\n"
        f"QUESTION: {question}\n"
        "<|end|>\n"
        "<|assistant|>\n"
    )


def _build_legal_prompt(extracted_context: str, contract_type: str) -> str:
    return (
        "<|system|>\n"
        "You are a legal document analyst. "
        "Analyze ONLY the provided contract sections. "
        "Be concise and use plain English.\n"
        "<|end|>\n"
        "<|user|>\n"
        f"Contract type: {contract_type}\n\n"
        f"{extracted_context}\n\n"
        "Provide:\n"
        "1. Key risks (2-3 bullets)\n"
        "2. Main obligations (1-2 sentences)\n"
        "3. Risk level: LOW / MEDIUM / HIGH\n"
        "<|end|>\n"
        "<|assistant|>\n"
    )


# ── Public functions ──────────────────────────────────────────────────────────

def summarize(text: str, model: str = None) -> str:
    model = model or get_best_model()
    return "".join(_stream(_build_summary_prompt(text), model, num_predict=300))


def stream_summary(text: str, model: str = None) -> Generator[str, None, None]:
    model = model or get_best_model()
    yield from _stream(_build_summary_prompt(text), model, num_predict=300)


def stream_chat(document_text: str, question: str, model: str = None) -> Generator[str, None, None]:
    model = model or get_best_model()
    yield from _stream(_build_chat_prompt(document_text, question), model, num_predict=350)


def chat_with_document(document_text: str, question: str, model: str = None) -> str:
    return "".join(stream_chat(document_text, question, model))


def legal_analyze(prompt: str, model: str = None) -> str:
    model = model or get_best_model()
    return "".join(_stream(prompt, model, num_predict=350))


def stream_legal_analyze(prompt: str, model: str = None) -> Generator[str, None, None]:
    model = model or get_best_model()
    yield from _stream(prompt, model, num_predict=350)


def build_legal_prompt(extracted_context: str, contract_type: str) -> str:
    """Public wrapper for legal prompt builder."""
    return _build_legal_prompt(extracted_context, contract_type)


def stream_chat_with_history(
    document_text: str,
    history: list[dict],
    question: str,
    model: str = None
) -> Generator[str, None, None]:
    """
    Stream answer with full conversation history.
    history is a list of {"role": "user"|"assistant", "content": "..."}
    Builds a single prompt that includes prior turns so model has context.
    """
    model = model or get_best_model()

    # Build conversation history string (last 6 turns max to save RAM)
    recent = history[-6:] if len(history) > 6 else history
    history_text = ""
    for turn in recent:
        role  = "You" if turn["role"] == "user" else "VaultMind"
        history_text += f"{role}: {turn['content']}\n"

    prompt = (
        "<|system|>\n"
        "You are a document assistant. Answer using ONLY the document provided. "
        "Use the conversation history to understand context and follow-up questions. "
        "If something refers to a previous answer, use that context. "
        "If the answer is not in the document, say so clearly.\n"
        "<|end|>\n"
        "<|user|>\n"
        f"DOCUMENT:\n{document_text}\n\n"
        f"CONVERSATION SO FAR:\n{history_text}\n"
        f"CURRENT QUESTION: {question}\n"
        "<|end|>\n"
        "<|assistant|>\n"
    )

    yield from _stream(prompt, model, num_predict=350)
