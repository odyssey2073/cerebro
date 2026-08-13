#!/usr/bin/env python3
"""
CEREBRO bridge: retrieves context from Qdrant and builds an enriched prompt,
usable with any agent (Claude Code, Copilot, other).
Usage:
    python scripts/cerebro_bridge.py --project <name> "how do I implement worktree support?"
"""
import argparse
import os
import subprocess

import requests

from project_config import collections_for, load_env, resolve_project

load_env()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")


def get_embedding(text: str) -> list[float]:
    resp = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBEDDING_MODEL, "prompt": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def search_qdrant(query: str, collections: list[str], limit: int = 5):
    vector = get_embedding(query)
    body = {"vector": vector, "limit": limit, "with_payload": True}
    merged = []
    for coll in collections:
        try:
            resp = requests.post(
                f"{QDRANT_URL}/collections/{coll}/points/search",
                json=body,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [collection '{coll}' unavailable: {e}]")
            continue
        for r in resp.json().get("result", []):
            r["_collection"] = coll
            merged.append(r)
    merged.sort(key=lambda r: r.get("score", 0), reverse=True)
    return merged[:limit]


def build_prompt(query: str, results: list, project: str) -> str:
    lines = [f"Context from project {project}:"]
    for r in results:
        p = r.get("payload", {})
        coll = r.get("_collection", "")
        header = f"{coll}/{p.get('source')}" if coll else p.get("source", "")
        lines.append(f"\n--- {header} ---\n{p.get('text', '')}")
        paths = p.get("image_paths", [])
        if paths:
            lines.append("\nAssociated images (open with the Read tool to view them):")
            for url, path in zip(p.get("image_urls", []), paths):
                lines.append(f"- path: {path}")
                lines.append(f"  url: {url}")
    lines.append("\n---")
    lines.append(f"Question: {query}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="CEREBRO bridge: prompt enriched with RAG context")
    parser.add_argument("--project", help="Project name (default: PROJECT env var)")
    parser.add_argument("query", nargs="+", help="Question")
    args = parser.parse_args()

    project = resolve_project(args.project)
    collections = collections_for(project)
    query = " ".join(args.query)

    print(f"Searching context for: {query} (collections {', '.join(collections)})\n")
    results = search_qdrant(query, collections)
    prompt = build_prompt(query, results, project)
    print("\n=== ENRICHED PROMPT ===\n")
    print(prompt)
    print("\n=======================\n")
    try:
        subprocess.run(
            ["gh", "copilot", "suggest", "-t", "shell", prompt],
            check=False,
        )
    except FileNotFoundError:
        print("gh CLI not found. Copy the prompt above and use it manually.")


if __name__ == "__main__":
    main()
