# CEREBRO Installation — prerequisites and skill

Minimal guide: prerequisites + Claude Code integration (`/cerebro` skill) and
GitHub Copilot (instructions files). For project indexing and advanced commands
see [README.md](README.md).

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

## 2. `/cerebro` skill for Claude Code (optional but recommended)

The skill guides project setup and maintenance via interactive questions.

```powershell
# copy the skill among Claude Code user skills
xcopy /E /I skills\cerebro "$env:USERPROFILE\.claude\skills\cerebro"
```

Then set the `CEREBRO_HOME` environment variable to the absolute path of the
repo (e.g. `C:\Progetti\cerebro`): the skill uses it to find scripts and the
venv. Alternatively edit the first section of
`%USERPROFILE%\.claude\skills\cerebro\SKILL.md` and replace the `CEREBRO_HOME`
references with the real path.

### Claude Code — automatic context via CLAUDE.md

After registering a project, generate the `CLAUDE.md` instructions:

```powershell
python scripts\register_project.py instructions <name> --tool claude
```

This writes a `<!-- CEREBRO:START/END -->` block into the project's `CLAUDE.md`.
Claude Code reads this file at session start and automatically knows how to query
the project's Qdrant collection for documentation context.

If the project uses [Graphify](https://github.com/algorithmic-archives/graphify)
for code-level knowledge graphs, add `--graphify`:

```powershell
python scripts\register_project.py instructions <name> --tool claude --graphify
```

This appends a `<!-- GRAPHIFY:START/END -->` block with code graph rules
(`graphify query`, `graphify path`, `graphify explain`, `graphify update .`).

Re-running `instructions` updates the blocks in place — no duplication, no
manual cleanup needed.

### GitHub Copilot — automatic context via copilot-instructions.md

Same as Claude, but targets `.github/copilot-instructions.md`:

```powershell
python scripts\register_project.py instructions <name> --tool copilot
python scripts\register_project.py instructions <name> --tool copilot --graphify
```

GitHub Copilot Chat loads this file automatically. Structure and capabilities
are identical to the Claude Code setup.

### Both agents at once

```powershell
python scripts\register_project.py instructions <name> --tool both --graphify
```

Writes both `CLAUDE.md` and `.github/copilot-instructions.md` with the same
CEREBRO RAG block (and optional Graphify block).

## 4. `/cerebro` slash command for GitHub Copilot

GitHub Copilot doesn't have a skill system like Claude Code, but you can add
CEREBRO as a **global custom instruction** that makes `/cerebro` work as a
slash command in Copilot Chat (VS Code, JetBrains, CLI).

### Setup

Open Copilot Chat settings and add the following to your **Custom Instructions**
(VS Code: `github.copilot.chat.customInstructions`, or edit
`~/.github-copilot/copilot-instructions.md` directly):

````markdown
## CEREBRO — /cerebro slash command

When the user types `/cerebro`, run the CEREBRO interactive menu for
managing the multi-project RAG brain. CEREBRO lives at `C:\Progetti\CEREBRO`
(adjust the path to your install):

- Scripts: `C:\Progetti\CEREBRO\scripts\`
- Python: `C:\Progetti\CEREBRO\.venv\Scripts\python.exe` (or system python)
- Registry: `C:\Progetti\CEREBRO\projects.json`

### Menu

When `/cerebro` is invoked, present these options (AskUserQuestion style):

1. **New project** — guided setup (name, root, docs paths, agent tools, Graphify)
2. **Re-index** — re-ingest docs for an existing project
3. **Status** — list all projects, collections, chunk counts
4. **Remove project** — remove from registry

### New project flow

Ask one question at a time:
1. Project name → show slug (lowercase, non-alphanumeric → `_`)
2. Project root path (verify with ls)
3. Docs paths (folders/files, default `<root>\docs`)
4. Agent tools: `both` / `claude` / `copilot`
5. Graphify knowledge graph: yes/no (appends `<!-- GRAPHIFY:START/END -->` block)

Then run in sequence (stop on first error):
```powershell
cd C:\Progetti\CEREBRO
.venv\Scripts\python scripts\register_project.py add <name> --docs <paths> --root <root>
.venv\Scripts\python scripts\register_project.py instructions <name> --tool <tool> [--graphify]
.venv\Scripts\python scripts\ingest_docs.py --project <name>
```

Verify with:
```powershell
.venv\Scripts\python scripts\query_qdrant.py --project <name> count
.venv\Scripts\python scripts\query_qdrant.py --project <name> search "<query>" --limit 3
```

### Other commands

- **Re-index**: `.venv\Scripts\python scripts\ingest_docs.py --project <name>`
- **Status**: `.venv\Scripts\python scripts\register_project.py list` then count per project
- **Remove**: `.venv\Scripts\python scripts\register_project.py remove <name>` (double-confirm; Qdrant collection is NEVER auto-deleted)
- **Manual query**: `.venv\Scripts\python scripts\query_qdrant.py --project <name> search "<query>"`

### Rules

- Always validate paths before registering
- Never DELETE Qdrant collections without double confirmation
- If a script fails, show stderr and apply diagnosis table
- Prerequisites: Qdrant on :6333, Ollama on :11434 (docker start qdrant / ollama serve if down)
````

Replace `C:\Progetti\CEREBRO` with your actual CEREBRO install path.

Once configured, typing `/cerebro` in Copilot Chat opens the menu. Copilot
acts as the interactive guide, asking questions and running scripts — the
same experience as the Claude Code skill.

```powershell
python scripts\register_project.py list
python scripts\query_qdrant.py --project <name> count
```

If everything responds, installation complete. Daily usage: see README,
section "Daily usage (post-install)".
