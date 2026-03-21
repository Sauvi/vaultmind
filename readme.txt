# 🧠 Local AI Agent (Privacy-First Demo)

## 🚀 Overview

This project is a **fully local, privacy-first AI assistant prototype** designed to:

* Operate **100% offline**
* Enforce **strict workspace boundaries**
* Require **user permission before any action**
* Learn **basic user behavior patterns over time**

This is an MVP focused on **control, safety, and trust**, not raw AI intelligence.

---

## 🔐 Core Principles

### 1. Workspace Isolation

* AI can **ONLY access files inside `/workspace/`**
* No access to system files, personal data, or external directories

---

### 2. Permission-First Execution

* AI **never acts automatically**
* Every action follows:

  ```
  Detect → Show Plan → Ask → Execute
  ```

---

### 3. Controlled Actions

* AI can only perform **predefined actions**
* No arbitrary or unknown operations allowed

---

### 4. Local Memory (Learning Behavior)

* System tracks repeated actions
* Builds simple usage patterns (e.g., summarizing `.txt` files)

---

## 🧱 Project Structure

```
local_ai/
│
├── main.py              # Entry point
├── watcher.py           # File system observer
├── task_manager.py      # Core logic + decision making
├── actions.py           # Allowed actions (e.g., summarize)
├── sandbox.py           # Workspace restriction logic
├── memory.py            # Behavior tracking
├── memory.json          # Stored usage patterns
│
└── workspace/
    ├── input/           # User input files
    └── output/          # AI-generated files
```

---

## ⚙️ Features Implemented

### ✅ 1. File Monitoring

* Watches `/workspace/input/`
* Detects new `.txt` files

---

### ✅ 2. Dry-Run Execution (Transparency)

Before any action, system shows:

* File to read
* File to write
* Action to perform

Example:

```
Proposed Action:
- Read: workspace/input/file.txt
- Write: workspace/output/file_summary.txt
- Action: summarize
```

---

### ✅ 3. Permission System

User must approve:

```
Proceed? (y/n):
```

---

### ✅ 4. Controlled Action (Summarization)

Current supported action:

* `summarize` → extracts first few lines from text file

---

### ✅ 5. Memory Tracking

System stores usage in `memory.json`:

```json
{
  "txt": {
    "summarize": 3
  }
}
```

---

### ✅ 6. Behavior Awareness

After repeated usage (≥ 3 times):

```
🤖 You usually summarize .txt files.
Do you want me to do it? (y/n)
```

---

## 🧪 How to Run

### 1. Install dependency

```
pip install watchdog
```

---

### 2. Start the system

```
python main.py
```

---

### 3. Test it

* Drop a `.txt` file into:

  ```
  workspace/input/
  ```

* Approve action when prompted

* Output will appear in:

  ```
  workspace/output/
  ```

---

## 🔒 Security Model

| Area          | Policy             |
| ------------- | ------------------ |
| File Access   | Workspace only     |
| Internet      | Disabled           |
| System Access | None               |
| Actions       | Allowlisted only   |
| Execution     | User-approved only |

---

## ⚠️ Limitations (Current MVP)

* No real AI/LLM yet (rule-based summarization)
* No automation (manual approval required)
* Limited to `.txt` files
* No UI (CLI only)

---

## 🚀 Next Steps

Planned improvements:

* [ ] Auto-mode (after user approval)
* [ ] Smarter summarization (local LLM)
* [ ] More actions (rename, convert, etc.)
* [ ] CLI improvements
* [ ] Task configuration panel
* [ ] Secure logging & audit trail

---

## 💡 Vision

> Build a **trustworthy AI agent** that:

* Learns user behavior
* Respects strict boundaries
* Operates fully offline
* Gives full control to the user

---

## 🧠 Key Idea

This is not just an assistant.

It is a:

> **Controlled AI Execution Framework with Privacy Guarantees**

---

## 👨‍💻 Author

Saurabh (Engineer)

---

## 📌 Status

🟢 MVP v0.2 — Core control + memory system implemented
