#!/usr/bin/env python3
"""
CEREBRO project registry management (projects.json).
Usage:
    python scripts/register_project.py add <name> --docs <path> [<path> ...] [--root <path>]
    python scripts/register_project.py remove <name>
    python scripts/register_project.py list
    python scripts/register_project.py instructions <name> [--tool claude|copilot|both] [--root <path>]
"""
import argparse
import re
import sys
from pathlib import Path

from project_config import (
    collection_for,
    docs_paths_for,
    load_registry,
    sanitize_project_name,
    save_registry,
)

SCRIPTS_DIR = Path(__file__).resolve().parent
QUERY_SCRIPT = SCRIPTS_DIR / "query_qdrant.py"

BLOCK_START = "<!-- CEREBRO:START -->"
BLOCK_END = "<!-- CEREBRO:END -->"

INSTRUCTIONS_BODY = """\
## CEREBRO RAG — project context

This project's documentation is semantically indexed in the Qdrant
collection `{collection}` at http://localhost:6333
(embeddings generated via Ollama with the `nomic-embed-text` model).

When you need information about architecture, features, conventions or project
plans, retrieve context with:

```bash
python "{query_script}" --project {slug} search "<query>" --limit 5
```

Rules:
- do not assume project conventions unless verified in the retrieved documents;
- if you modify code, check consistency with the documented conventions;
- if Qdrant or Ollama are unreachable, say so and proceed without RAG context.
"""


def cerebro_block(project: str) -> str:
    slug = sanitize_project_name(project)
    body = INSTRUCTIONS_BODY.format(
        collection=collection_for(slug),
        query_script=QUERY_SCRIPT,
        slug=slug,
    )
    return f"{BLOCK_START}\n{body}{BLOCK_END}"


def upsert_block(path: Path, block: str) -> str:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END)
    if re.search(pattern, text, re.DOTALL):
        text = re.sub(pattern, lambda _: block, text, flags=re.DOTALL)
        action = "updated block"
    elif text:
        text = text.rstrip() + "\n\n" + block + "\n"
        action = "added block"
    else:
        text = block + "\n"
        action = "created"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return action


def cmd_add(args):
    slug = sanitize_project_name(args.name)
    registry = load_registry()
    entry = {"docs": args.docs}
    if args.root:
        entry["root"] = args.root
    registry[slug] = entry
    save_registry(registry)
    print(f"Project '{slug}' registered -> collection {collection_for(slug)}")
    for d in args.docs:
        print(f"  docs: {d}")
    if args.root:
        print(f"  root: {args.root}")


def cmd_remove(args):
    slug = sanitize_project_name(args.name)
    registry = load_registry()
    if slug not in registry:
        print(f"Project '{slug}' not found in registry.")
        sys.exit(1)
    del registry[slug]
    save_registry(registry)
    print(f"Project '{slug}' removed from registry (Qdrant collection untouched).")


def cmd_list(_args):
    registry = load_registry()
    if not registry:
        print("Registry empty.")
        return
    for slug in sorted(registry):
        print(f"{slug} -> {collection_for(slug)}")
        if registry[slug].get("root"):
            print(f"  root: {registry[slug]['root']}")
        for d in docs_paths_for(slug):
            print(f"  docs: {d}")


def cmd_instructions(args):
    slug = sanitize_project_name(args.name)
    entry = load_registry().get(slug, {})
    root = args.root or entry.get("root")
    if not root:
        raise SystemExit(
            f"Root of project '{slug}' unknown. "
            "Pass --root <path> or register it with: add ... --root <path>"
        )
    root = Path(root)
    if not root.is_dir():
        raise SystemExit(f"Root '{root}' does not exist.")

    block = cerebro_block(slug)
    targets = []
    if args.tool in ("claude", "both"):
        targets.append(root / "CLAUDE.md")
    if args.tool in ("copilot", "both"):
        targets.append(root / ".github" / "copilot-instructions.md")

    for target in targets:
        action = upsert_block(target, block)
        print(f"{action}: {target}")


def main():
    parser = argparse.ArgumentParser(description="CEREBRO project registry management")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Register or update a project")
    a.add_argument("name", help="Project name (sanitized into a slug)")
    a.add_argument("--docs", nargs="+", required=True, help="Project docs folders/files")
    a.add_argument("--root", help="Project root (for instructions generation)")
    a.set_defaults(func=cmd_add)

    r = sub.add_parser("remove", help="Remove a project from the registry")
    r.add_argument("name", help="Project name")
    r.set_defaults(func=cmd_remove)

    l = sub.add_parser("list", help="List registered projects")
    l.set_defaults(func=cmd_list)

    i = sub.add_parser("instructions", help="Generate/update CLAUDE.md and/or copilot-instructions.md in the project")
    i.add_argument("name", help="Project name")
    i.add_argument("--tool", choices=["claude", "copilot", "both"], default="both",
                   help="Target: CLAUDE.md, .github/copilot-instructions.md or both (default: both)")
    i.add_argument("--root", help="Project root (registry override)")
    i.set_defaults(func=cmd_instructions)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
