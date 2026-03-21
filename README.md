<div align="center">

# 🔒 VaultMind

### Private AI for your documents — 100% local, no cloud, no compromise.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Ollama](https://img.shields.io/badge/Powered%20by-Ollama-orange.svg)](https://ollama.com)
[![Status: Beta](https://img.shields.io/badge/Status-Beta-purple.svg)]()

**Ask questions about your contracts, reports, and documents — without sending a single byte to the cloud.**

</div>

---

## Why VaultMind?

Every major AI tool — ChatGPT, Claude, Gemini — processes your documents on their servers. For lawyers, HR teams, and finance professionals, that's a compliance nightmare.

VaultMind runs entirely on your machine. Your documents never leave your computer. Ever.

---

## Features

- **Chat with documents** — Ask questions about any PDF, DOCX, or TXT file in plain English
- **AI summarization** — Get a clean 5-point summary of any document in seconds
- **Legal review** — Automatically extract parties, dates, risk clauses, and obligations from contracts
- **Permission-first** — Every action shows a dry-run plan before executing. You always approve first
- **Audit log** — Every action is logged locally so you know exactly what happened and when
- **Behavior memory** — VaultMind learns your habits and suggests actions over time
- **Beautiful UI** — Clean dark web interface, no terminal knowledge needed after setup

---

## Supported File Types

| Format | Summarize | Chat | Legal Review |
|--------|-----------|------|--------------|
| `.pdf` | ✅ | ✅ | ✅ |
| `.docx` | ✅ | ✅ | ✅ |
| `.txt` | ✅ | ✅ | ✅ |
| `.md` | ✅ | ✅ | ✅ |

---

## Quick Start

### Requirements

- Windows / macOS / Linux
- Python 3.10+
- 8 GB RAM minimum (16 GB recommended)
- [Ollama](https://ollama.com) installed

### 1. Install Ollama and pull the model

```bash
# Download Ollama from https://ollama.com
# Then pull the recommended model:
ollama pull phi3.5
```

### 2. Clone and install VaultMind

```bash
git clone https://github.com/YOUR_USERNAME/vaultmind.git
cd vaultmind
pip install -r requirements.txt
```

### 3. Start VaultMind

**Windows:**
```bash
run.bat
```

**macOS / Linux:**
```bash
bash run.sh
```

### 4. Open your browser

```
http://localhost:8000
```

That's it. Drop a file, approve the action, get answers.

---

## How It Works

```
Your File
    │
    ▼
┌─────────────────────────────────────┐
│  File Reader                        │
│  Extract text (PDF/DOCX/TXT/MD)     │
│  Clean noise + smart truncation     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Sandbox Check                      │
│  Validate file is inside workspace  │
│  Show dry-run plan to user          │
│  Wait for approval                  │
└──────────────┬──────────────────────┘
               │  User approves
               ▼
┌─────────────────────────────────────┐
│  Local AI Engine (Ollama)           │
│  phi3.5 running on your machine     │
│  Zero internet connection           │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Output                             │
│  Saved to workspace/output/         │
│  Logged to audit.log                │
└─────────────────────────────────────┘
```

**Nothing in this pipeline touches the internet.**

---

## Legal Review — How It Works

VaultMind uses a two-stage approach for contract analysis:

**Stage 1 — Pattern Extraction (instant, zero AI)**
Scans the document using regex patterns to find:
- Parties and signatories
- Key dates and deadlines
- Risk clause keywords (indemnification, liability, termination, etc.)
- Obligations and duties
- Governing law and jurisdiction

**Stage 2 — Targeted AI Analysis (fast, low RAM)**
Sends *only the extracted sections* to the local AI — not the full document.
This keeps analysis fast even on modest hardware.

---

## Project Structure

```
vaultmind/
├── app.py              # FastAPI web server + all routes
├── file_reader.py      # Smart document extraction pipeline
├── ollama_engine.py    # Local AI communication (streaming)
├── legal_extractor.py  # Legal pattern extraction engine
├── task_manager.py     # Action orchestration + validation
├── actions.py          # Summarize + legal review actions
├── sandbox.py          # Workspace security boundaries
├── memory.py           # Behavior tracking
├── templates/
│   └── index.html      # Full web UI (single file)
├── workspace/
│   ├── input/          # Drop files here
│   └── output/         # Results saved here
├── requirements.txt
├── run.bat             # Windows launcher
└── run.sh              # macOS/Linux launcher
```

---

## Security Model

| Area | Policy |
|------|--------|
| File access | Workspace directory only |
| Internet | Completely disabled |
| AI processing | Local machine only |
| Actions | Allowlisted only |
| Execution | User approval required |
| Logging | Local audit trail |

---

## Recommended Models

| Model | RAM needed | Quality | Speed | Best for |
|-------|-----------|---------|-------|----------|
| `phi3.5` ⭐ | ~1.4 GB | Good | Fast | 8 GB machines — recommended |
| `phi3` | ~2.0 GB | Better | Medium | 12 GB machines |
| `llama3.1:8b` | ~5.0 GB | Best | Slower | 16 GB+ machines |

---

## Roadmap

- [x] Web UI with dark theme
- [x] PDF, DOCX, TXT, MD support
- [x] Streaming chat with documents
- [x] Legal extraction engine
- [x] Smart input pipeline
- [x] Audit log + memory system
- [ ] Conversation memory (multi-turn chat)
- [ ] One-click Windows installer
- [ ] Multi-file chat
- [ ] Landing page
- [ ] Plugin / action SDK

---

## Contributing

VaultMind is open source and contributions are welcome.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add your feature'`
4. Push and open a Pull Request

For bugs and feature requests, open an [Issue](https://github.com/YOUR_USERNAME/vaultmind/issues).

---

## License

MIT — free to use, modify, and distribute. See [LICENSE](LICENSE) for details.

---

<div align="center">

Built by [Saurabh Parmar](https://github.com/YOUR_USERNAME) · Star ⭐ if you find it useful

</div>
