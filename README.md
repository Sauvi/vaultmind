<div align="center">

# 🔒 VaultMind

### Private AI for your documents — 100% local, no cloud, no compromise.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Ollama](https://img.shields.io/badge/Powered%20by-Ollama-orange.svg)](https://ollama.com)
[![Status: Beta](https://img.shields.io/badge/Status-Beta-purple.svg)]()

**Chat with contracts, review legal documents, and draft agreements using local AI.**
**Your files never leave your machine — not even for a millisecond.**

[🌐 Website](https://sauvi.github.io/vaultmind) · [📦 Download](https://github.com/Sauvi/vaultmind/releases) · [🐛 Issues](https://github.com/Sauvi/vaultmind/issues)

</div>

---

## Why VaultMind?

Every major AI tool — ChatGPT, Claude, Gemini — processes your documents on their servers. For lawyers, HR teams, and finance professionals, that is a compliance nightmare.

VaultMind runs entirely on your machine. Your documents never leave your computer. Ever.

---

## Features

### Core
- **Chat with documents** — Ask questions in plain English about any PDF, DOCX, or TXT file
- **AI summarization** — 5-point summary of any document in seconds
- **Streaming responses** — Answers appear word by word, just like ChatGPT
- **Conversation memory** — Follow-up questions work naturally across a session
- **Multi-document chat** — Upload multiple files, ask questions across all of them at once

### Legal Tools
- **Legal review** — Automatically extract parties, dates, risk clauses, obligations, and governing law
- **Clause extraction** — Pull specific clause types: payment, confidentiality, liability, IP, force majeure, dispute, warranty, assignment, non-compete
- **Contract comparison** — Upload two contracts, get an instant diff with risk level (LOW / MEDIUM / HIGH)
- **Deadline & obligation tracker** — All dates and obligations as a printable checklist

### Document Drafting
- **NDA** — Non-Disclosure Agreement
- **Service Agreement** — Client-vendor service contract
- **Employment Contract** — Full employment agreement with statutory compliance
- **Consulting Agreement** — Independent contractor agreement

All drafts generated instantly as downloadable DOCX files.

### Reports & Export
- **Professional DOCX report** — One-click export of all findings: parties, dates, risks, obligations, AI analysis
- **Audit log** — Every action recorded locally — what file, what action, when, result

### Privacy & Security
- **Permission-first** — Every action shows a dry-run plan before executing. You always approve first
- **Workspace sandbox** — AI can only access files inside the workspace directory
- **100% offline** — No internet connection used after setup
- **Open source** — Read every line of code yourself

---

## Supported File Types

| Format | Chat | Summarize | Legal Review | Clause Extract | Compare |
|--------|------|-----------|--------------|----------------|---------|
| `.pdf` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `.docx` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `.txt` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `.md` | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Quick Start

### Requirements

- Windows / macOS / Linux
- Python 3.10+
- 8 GB RAM minimum (16 GB recommended for best performance)
- [Ollama](https://ollama.com) installed

### 1. Install Ollama and pull the model

```bash
# Download Ollama from https://ollama.com
# Then pull the recommended model (2.2GB):
ollama pull phi3.5
```

### 2. Clone and install

```bash
git clone https://github.com/Sauvi/vaultmind.git
cd vaultmind
pip install -r requirements.txt
```

### 3. Start VaultMind

**Windows:**
```
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

Drop a file, approve the action, get answers.

---

## How It Works

```
Your Document (PDF / DOCX / TXT / MD)
         │
         ▼
┌─────────────────────────────────┐
│  File Reader                    │
│  Full text extraction           │
│  Clean + normalize              │
│  Cached in memory               │
└──────────────┬──────────────────┘
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
┌────────────┐  ┌───────────────────┐
│  Pattern   │  │  Smart keyword    │
│  Extractor │  │  extraction for   │
│  (instant) │  │  AI context       │
└────────────┘  └────────┬──────────┘
       │                 │
       ▼                 ▼
┌─────────────────────────────────┐
│  Ollama — phi3.5                │
│  Running on YOUR machine        │
│  Zero internet connection       │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  Output                         │
│  Streamed to browser            │
│  Saved to workspace/output/     │
│  Logged to audit.log            │
└─────────────────────────────────┘
```

**Nothing in this pipeline touches the internet.**

---

## Project Structure

```
vaultmind/
├── app.py                  # FastAPI web server + all API routes
├── ollama_engine.py        # Local AI communication (streaming)
├── file_reader.py          # Document extraction (PDF/DOCX/TXT/MD)
├── legal_extractor.py      # Legal pattern extraction engine
├── features.py             # Clause extraction, comparison, deadline tracker, report
├── drafting.py             # Document drafting assistant (4 templates)
├── multi_doc.py            # Multi-document analysis engine
├── task_manager.py         # Action orchestration + validation
├── sandbox.py              # Workspace security boundaries
├── memory.py               # Behavior pattern tracking
├── templates/
│   └── index.html          # Full web UI (single file)
├── workspace/
│   ├── input/              # Uploaded files
│   └── output/             # Generated reports and drafts
├── requirements.txt
├── run.bat                 # Windows launcher
└── run.sh                  # macOS/Linux launcher
```

---

## Security Model

| Area | Policy |
|------|--------|
| File access | Workspace directory only — sandboxed |
| Internet | Completely disabled during processing |
| AI processing | Local machine only — Ollama |
| Actions | Allowlisted only |
| Execution | User approval required before every action |
| Logging | Local audit trail only |

---

## Recommended Models

| Model | RAM needed | Speed | Best for |
|-------|-----------|-------|----------|
| `phi3.5` ⭐ | ~1.4 GB | Good | 8 GB machines — recommended |
| `phi3` | ~2.0 GB | Medium | 12 GB machines |
| `llama3.1:8b` | ~5.0 GB | Slower | 16 GB+ machines |

> **Note:** GPU acceleration dramatically improves speed. If you have an NVIDIA GPU, Ollama uses it automatically.

---

## Roadmap

- [x] Web UI with dark theme
- [x] PDF, DOCX, TXT, MD support
- [x] Streaming chat with documents
- [x] Conversation memory (multi-turn)
- [x] Multi-document chat
- [x] Legal extraction engine (parties, dates, risks, obligations)
- [x] Clause extraction (10 clause types)
- [x] Contract comparison with risk scoring
- [x] Deadline and obligation tracker
- [x] Professional DOCX report export
- [x] Document drafting assistant (4 templates)
- [x] Audit log and behavior memory
- [ ] One-click Windows installer
- [ ] Multi-file drag and drop
- [ ] Plugin / action SDK
- [ ] Paid hosted cloud tier (optional)

---

## Contributing

VaultMind is open source and contributions are welcome.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add your feature'`
4. Push and open a Pull Request

For bugs and feature requests, open an [Issue](https://github.com/Sauvi/vaultmind/issues).

---

## License

MIT — free to use, modify, and distribute. See [LICENSE](LICENSE) for details.

---

<div align="center">

Built by [Saurabh Parmar](https://github.com/Sauvi) · Star ⭐ if you find it useful

*Your documents deserve actual privacy.*

</div>
