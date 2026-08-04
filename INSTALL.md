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

## 3. GitHub Copilot integration (per project)

For each registered project:

```powershell
python scripts\register_project.py instructions <name> --tool copilot
```

Creates `.github\copilot-instructions.md` in the project root: Copilot Chat
loads it automatically and knows how to query the `CRB_<name>` collection.

## 4. Final verification

```powershell
python scripts\register_project.py list
python scripts\query_qdrant.py --project <name> count
```

If everything responds, installation complete. Daily usage: see README,
section "Daily usage (post-install)".
