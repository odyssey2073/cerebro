# CEREBRO Installation

Minimal guide: prerequisites + the web launcher. For project indexing and advanced
commands see [README.md](README.md).

## 1. Prerequisites (one time only)

- **Python 3.10+**
- **Docker Desktop** (needed for Qdrant)
- **Ollama** installed

```powershell
# 1. Qdrant (persistent container)
docker pull qdrant/qdrant
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage qdrant/qdrant
curl http://localhost:6333/collections        # expected: JSON

# 2. Embedding model
ollama pull nomic-embed-text
curl http://localhost:11434                   # expected: "Ollama is running"

# 3. Clone + virtualenv
git clone https://github.com/odyssey2073/cerebro.git
cd cerebro
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Default configuration is ready in `.env.example` (Qdrant/Ollama URLs, model, dim 768).
Edit `.env` only if the services run on different hosts/ports.

## 2. CEREBRO Launcher (web SPA)

A single local web interface for **both Claude Code and GitHub Copilot** — no
per-tool skill or CLI. It manages new project, re-index, status, remove and query
from the browser:

```powershell
python scripts\cerebro-launcher.py
```

Opens http://127.0.0.1:8789. From the UI:

| Action | What it does |
|---|---|
| **New project** | name, root, docs paths, agent tools (`both`/`claude`/`copilot`), Graphify, extra collections → registers, indexes, generates agent instructions |
| **Re-index** | re-ingests docs for an existing project (incremental, no duplicates) |
| **Status** | table of projects, collections, chunk counts, docs paths |
| **Query** | semantic search with results (score, collection, source, text, images) |
| **Remove** | removes from the registry (the Qdrant collection is never auto-deleted) |

The launcher drives the same core scripts (`register_project.py`, `ingest_docs.py`,
`query_qdrant.py`, `remove_doc.py`). No `CEREBRO_HOME` variable is needed — the
launcher finds the repo and venv by its own location.

## 3. Agent awareness (automatic context)

Registering a project is not enough: the agent must be told how to query the brain.
The launcher's **New project** action generates this automatically; to run it
manually:

```powershell
python scripts\register_project.py instructions <name> --tool both [--graphify]
```

This writes a `<!-- CEREBRO:START/END -->` block into the project's `CLAUDE.md`
(Claude Code) and `.github/copilot-instructions.md` (GitHub Copilot), so both
agents query the project's Qdrant collection for documentation context at every
session. `--tool claude` / `--tool copilot` target a single agent; `--graphify`
appends a `<!-- GRAPHIFY:START/END -->` block with code-level knowledge graph
rules. Re-running updates the blocks in place.

Both files are kept in sync: re-running `instructions` updates the blocks in place
without touching the rest of the file. No manual editing needed after initial setup.
