#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook — injects CEREBRO/Qdrant RAG context per prompt.

Reads the hook JSON from stdin (Claude Code sends {prompt, ...}), searches Qdrant for the
most relevant chunks, and prints a `hookSpecificOutput.additionalContext` response.

Claude Code only (Copilot CLI has no UserPromptSubmit-equivalent hook).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from limet_mcp import search, _default_project  # noqa: E402


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    prompt = (data.get("prompt") or "").strip()

    out = {"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "",
    }}

    if not prompt:
        print(json.dumps(out, ensure_ascii=False))
        return

    try:
        project = os.environ.get("LIMET_PROJECT") or _default_project()
        chunks = search(project, prompt, 3)
    except Exception:
        chunks = []

    if chunks:
        lines = ["RAG context (from Qdrant):\n"]
        for r in chunks:
            lines.append(f"[{r['score']}] {r['source']}")
            lines.append(r["text"].strip())
            lines.append("---")
        out["hookSpecificOutput"]["additionalContext"] = "\n".join(lines)

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
