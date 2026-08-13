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

from project_config import collections_for, load_env, resolve_project

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


def search(query: str, collections: list[str], limit: int = 5, source: str | None = None):
    vector = get_embedding(query)
    body = {"vector": vector, "limit": limit, "with_payload": True}
    if source:
        body["filter"] = {"must": [{"key": "source", "match": {"value": source}}]}
    merged = []
    for coll in collections:
        try:
            data = qdrant_post(f"/collections/{coll}/points/search", body)
        except requests.RequestException as e:
            print(f"  [collection '{coll}' unavailable: {e}]", file=sys.stderr)
            continue
        for r in data.get("result", []):
            r["_collection"] = coll
            merged.append(r)
    merged.sort(key=lambda r: r.get("score", 0), reverse=True)
    merged = merged[:limit]
    if not merged:
        print("No results.")
        return
    for r in merged:
        p = r.get("payload", {})
        print(f"---\nScore: {r.get('score', 0):.4f}  (collection: {r.get('_collection')})")
        print(f"Source: {p.get('source')}")
        print(f"Title: {p.get('title')}")
        print(f"Text:\n{p.get('text', '')}")
        for url, path in zip(p.get("image_urls", []), p.get("image_paths", [])):
            print(f"Image: {url}")
            print(f"  Path: {path}")
    print("---")


def scroll(collections: list[str], source: str | None = None, limit: int = 10, offset: int = 0):
    body = {"limit": limit, "offset": offset, "with_payload": True}
    if source:
        body["filter"] = {"must": [{"key": "source", "match": {"value": source}}]}
    for coll in collections:
        try:
            data = qdrant_post(f"/collections/{coll}/points/scroll", body)
        except requests.RequestException as e:
            print(f"  [collection '{coll}' unavailable: {e}]", file=sys.stderr)
            continue
        points = data.get("result", {}).get("points", [])
        if not points:
            continue
        print(f"=== collection: {coll} ===")
        for r in points:
            p = r.get("payload", {})
            print(f"---\nID: {r.get('id')}")
            print(f"Source: {p.get('source')}")
            print(f"Title: {p.get('title')}")
            print(f"Text:\n{p.get('text', '')}")
            for url, path in zip(p.get("image_urls", []), p.get("image_paths", [])):
                print(f"Image: {url}")
                print(f"  Path: {path}")
        print("---")


def count(collections: list[str]):
    total_all = 0
    for coll in collections:
        try:
            data = qdrant_post(f"/collections/{coll}/points/count", {"exact": True})
        except requests.RequestException as e:
            print(f"  [collection '{coll}' unavailable: {e}]", file=sys.stderr)
            continue
        total = data.get("result", {}).get("count", 0)
        print(f"Points in '{coll}': {total}")
        total_all += total
    if len(collections) > 1:
        print(f"Total: {total_all}")


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
    collections = collections_for(project)
    print(f"Collections: {', '.join(collections)}\n")

    try:
        if args.cmd == "search":
            search(args.query, collections, args.limit, args.source)
        elif args.cmd == "scroll":
            scroll(collections, args.source, args.limit, args.offset)
        elif args.cmd == "count":
            count(collections)
    except requests.RequestException as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
