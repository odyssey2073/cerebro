---
name: cerebro
description: Guided setup and maintenance for CEREBRO (multi-project RAG brain on Qdrant). Use when: user says "/cerebro", "setup cerebro", "new cerebro project", "re-index", "cerebro status", or wants to add/register/index a project into the Qdrant brain, generate CLAUDE.md/copilot-instructions for it, re-index docs, or check collection status.
version: 1.2.0
---

# CEREBRO — guided setup and maintenance

CEREBRO lives in the folder pointed to by the **`CEREBRO_HOME`** environment
variable (e.g. `C:\Progetti\cerebro`). Scripts in `%CEREBRO_HOME%\scripts\`.
Each project → Qdrant collection `CRB_<slug>`. Registry `%CEREBRO_HOME%\projects.json`.

First of all: check that `CEREBRO_HOME` is set (`echo $env:CEREBRO_HOME`).
If missing, ask the user for the repo path and use it in place of `CEREBRO_HOME`
in all commands below.

Language: respond in the **user's language**. All commands run with cwd
`CEREBRO_HOME` and the venv python: `.venv\Scripts\python`.

## Step 0 — Banner (ALWAYS first output)

Print this block exactly, in a code block. Use the 🟧 emoji (solid orange, guaranteed rendering everywhere — do NOT use ANSI codes, they get stripped by markdown rendering):

```
🟧🟧🟧  🟧🟧🟧  🟧🟧🟧  🟧🟧🟧  🟧🟧🟧  🟧🟧🟧  🟧🟧🟧
🟧      🟧      🟧  🟧  🟧      🟧  🟧  🟧  🟧  🟧  🟧
🟧      🟧🟧    🟧🟧🟧  🟧🟧    🟧🟧🟧  🟧🟧🟧  🟧  🟧
🟧      🟧      🟧 🟧   🟧      🟧  🟧  🟧 🟧   🟧  🟧
🟧🟧🟧  🟧🟧🟧  🟧  🟧  🟧🟧🟧  🟧🟧🟧  🟧  🟧  🟧🟧🟧

      the external brain for your projects
```

## Step 1 — Menu (AskUserQuestion)

Ask what to do:

1. **New project** → setup flow (Step 2)
2. **Re-index** → ask project name → run ingest (Step 3)
3. **Status** → `register_project.py list`, then for each project `query_qdrant.py --project <slug> count` (Step 4)
4. **Remove project** → Step 5

## Step 2 — New project

### 2a. Data collection (AskUserQuestion, one question at a time)

1. **Project name** (free text). Show the resulting slug: lowercase, every non-alphanumeric sequence → `_` (e.g. `My App` → `my_app` → collection `CRB_my_app`).
2. **Project root** (absolute path, e.g. `C:\Progetti\helix`). Verify existence with `ls`; if missing, ask whether to create it or fix the path.
3. **Docs paths**: one or more paths (folders or files). Formats: `.md .txt .pdf .epub .docx .xlsx .pptx .html .htm`. Proposed default: `<root>\docs`. Validate each one. If the user has no docs ready, offer the default `CEREBRO_HOME\projects\<slug>\docs` (create it).
   - `.pdf` / `.epub` → Markdown **with extracted images**, linked as `![Figure](images/fig_NNNN.png)`; assets in `assets\<slug>\<source>\` (markdown + `images\`).
   - Images served by a local static server (port `IMAGES_PORT`, default `8777`), auto-started by ingest. In results: `image_paths` (for Claude's `Read`) + `image_urls` (browser).
   - Scanned PDFs (images only, no text) → not indexable (OCR out of scope).
4. **Agent tools**: `both` (default) / `claude` / `copilot` → which instruction files to generate.
   - `claude` → `CLAUDE.md`
   - `copilot` → `.github\copilot-instructions.md`
   - `both` → both files
5. **Graphify knowledge graph** (only if the project uses Graphify for code-level KG): yes/no.
   If yes, a `<!-- GRAPHIFY:START/END -->` block is appended to the generated instruction file(s)
   with rules for `graphify query`, `graphify path`, `graphify explain`, `graphify update .`.

### 2b. Prerequisites (stop at first error)

```powershell
curl -s http://localhost:6333/collections   # Qdrant
curl -s http://localhost:11434              # Ollama
```

- Qdrant down → `docker start qdrant` (or install: see README Docker section), then retry. Still down → stop with the remedy.
- Ollama down → suggest `ollama serve`, stop until it responds.
- If `CEREBRO_HOME\.venv` is missing → ask for confirmation and create it:
  `python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt`

### 2c. Execution (sequence, stop at first error)

```powershell
cd $env:CEREBRO_HOME
.venv\Scripts\python scripts\register_project.py add <name> --docs <path1> [<path2> ...] --root <root>
.venv\Scripts\python scripts\register_project.py instructions <name> --tool <both|claude|copilot> [--graphify]
.venv\Scripts\python scripts\ingest_docs.py --project <name>
```

Errors on single chunks during ingest: tolerated, report how many were skipped.

### 2d. Verification

```powershell
.venv\Scripts\python scripts\query_qdrant.py --project <name> count
.venv\Scripts\python scripts\query_qdrant.py --project <name> search "<typical word from the docs>" --limit 3
```

`count` = 0 → something is wrong: check docs paths and ingest log.

### 2e. Final summary

Report: slug, collection `CRB_<slug>`, files written (`CLAUDE.md`, `.github\copilot-instructions.md`), Graphify block included (yes/no), number of indexed chunks. Close with:

> Open the project and work with Claude Code or Copilot: the generated instructions tell the agent how to query the brain. Optional aliases for manual use: `cerebro-ask --project <slug> "question"` (query) and `cerebro-ingest --project <slug>` (re-index) — see README for alias installation.

## Step 3 — Re-index

Ask for the name (propose the list from `register_project.py list`), then:

```powershell
cd $env:CEREBRO_HOME
.venv\Scripts\python scripts\ingest_docs.py --project <name>
```

(If the user installed the PowerShell alias: `cerebro-ingest --project <name>`.)

Upsert: chunks of the same file are overwritten, not duplicated. If a document was deleted from the project, offer `remove_doc.py --project <name> --source "<relative path>"`.

## Step 4 — Status

```powershell
cd $env:CEREBRO_HOME
.venv\Scripts\python scripts\register_project.py list
```

For each listed project: `query_qdrant.py --project <slug> count`. Present a table: project | collection | chunks | docs paths. Add service status (Qdrant/Ollama reachable yes/no).

## Step 5 — Remove project

Ask for the name (propose the list). Explicit confirmation before running:

```powershell
cd $env:CEREBRO_HOME
.venv\Scripts\python scripts\register_project.py remove <name>
```

**Warning**: the Qdrant collection `CRB_<slug>` stays with all its data. Do NOT delete it automatically. Show the command and ask for separate confirmation:

```powershell
curl -X DELETE http://localhost:6333/collections/CRB_<slug>
```

## Quick diagnosis

| Symptom | Cause | Fix |
|---|---|---|
| `Connection refused :6333` | Qdrant down | `docker start qdrant` |
| `Connection refused :11434` | Ollama down | `ollama serve` |
| `Collection doesn't exist` | never ingested | Step 2c / 3 |
| `Project not specified` | missing `--project` | add the flag |
| `count` = 0 after ingest | empty/wrong docs paths | check with `register_project.py list`, re-register |
| Stale results | docs changed | re-index (Step 3) |

## Fixed rules

- Never invent paths: always validate existence before registering.
- Never run DELETE on Qdrant collections without double confirmation.
- If a script fails, show the exact stderr and apply the diagnosis table before retrying.
- Full README: `CEREBRO_HOME\README.md`.
