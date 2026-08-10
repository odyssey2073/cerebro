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

## 4. Final verification

```powershell
python scripts\register_project.py list
python scripts\query_qdrant.py --project <name> count
```

If everything responds, installation complete. Daily usage: see README,
section "Daily usage (post-install)".
