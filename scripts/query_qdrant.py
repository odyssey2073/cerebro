#!/usr/bin/env python3
"""
Query Qdrant via REST.
Usage:
    python scripts/query_qdrant.py --project <name> search "query text" [--limit N] [--source FILTER]
    python scripts/query_qdrant.py --project <name> scroll [--source FILTER] [--limit N] [--offset N]
    python scripts/query_qdrant.py --project <name> count
"""
import argparse
import io
import os
import sys

import requests

from project_config import collection_for, load_env, resolve_project

load_env()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

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


def qdrant_post(path: str, payload: dict) -> dict:
    url = f"{QDRANT_URL}{path}"
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def search(query: str, collection_name: str, limit: int = 5, source: str | None = None):
    vector = get_embedding(query)
    body = {"vector": vector, "limit": limit, "with_payload": True}
    if source:
        body["filter"] = {"must": [{"key": "source", "match": {"value": source}}]}
    data = qdrant_post(f"/collections/{collection_name}/points/search", body)
    results = data.get("result", [])
    if not results:
        print("No results.")
        return
    for r in results:
        p = r.get("payload", {})
        print(f"---\nScore: {r.get('score', 0):.4f}")
        print(f"Source: {p.get('source')}")
        print(f"Title: {p.get('title')}")
        print(f"Text:\n{p.get('text', '')}")
    print("---")


def scroll(collection_name: str, source: str | None = None, limit: int = 10, offset: int = 0):
    body = {"limit": limit, "offset": offset, "with_payload": True}
    if source:
        body["filter"] = {"must": [{"key": "source", "match": {"value": source}}]}
    data = qdrant_post(f"/collections/{collection_name}/points/scroll", body)
    points = data.get("result", {}).get("points", [])
    if not points:
        print("No results.")
        return
    for r in points:
        p = r.get("payload", {})
        print(f"---\nID: {r.get('id')}")
        print(f"Source: {p.get('source')}")
        print(f"Title: {p.get('title')}")
        print(f"Text:\n{p.get('text', '')}")
    print("---")


def count(collection_name: str):
    data = qdrant_post(f"/collections/{collection_name}/points/count", {"exact": True})
    total = data.get("result", {}).get("count", 0)
    print(f"Points in '{collection_name}': {total}")


def main():
    parser = argparse.ArgumentParser(description="Query Qdrant via REST")
    parser.add_argument("--project", help="Project name (default: PROJECT env var)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="Semantic search")
    s.add_argument("query", help="Query text")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--source", help="Filter by source")

    sc = sub.add_parser("scroll", help="Scroll points")
    sc.add_argument("--source", help="Filter by source")
    sc.add_argument("--limit", type=int, default=10)
    sc.add_argument("--offset", type=int, default=0)

    sub.add_parser("count", help="Count points")

    args = parser.parse_args()

    project = resolve_project(args.project)
    collection_name = collection_for(project)

    try:
        if args.cmd == "search":
            search(args.query, collection_name, args.limit, args.source)
        elif args.cmd == "scroll":
            scroll(collection_name, args.source, args.limit, args.offset)
        elif args.cmd == "count":
            count(collection_name)
    except requests.RequestException as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
