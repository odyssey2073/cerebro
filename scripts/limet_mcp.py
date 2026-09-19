#!/usr/bin/env python3
"""LIMET MCP server — semantic RAG search over CEREBRO (Qdrant) for LIMET projects.

Exposes a single tool `limet_search(query, project?, limit?)` that embeds the query via
Ollama and searches the project's Qdrant collection(s). Stdlib-only (no MCP SDK, no
heavy deps) so startup is fast. Speaks the MCP stdio transport (newline-delimited JSON-RPC).

Register it once per tool:
  - Claude Code: `.mcp.json` in the project, or `claude mcp add limet -- python <this-file>`
  - Copilot CLI : `copilot mcp add limet -- python <this-file>`
"""
import json
import os
import sys
import urllib.error
import urllib.request

# Windows: force UTF-8 on stdio (default cp1252 chokes on doc text with unicode).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import project_config  # noqa: E402  (collections_for, sanitize_project_name)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "limet"
SERVER_VERSION = "1.0.0"


def _post(url, payload, timeout=30):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _embed(text):
    return _post(f"{OLLAMA_URL}/api/embeddings",
                 {"model": EMBED_MODEL, "prompt": text})["embedding"]


def _default_project():
    cwd = os.getcwd().rstrip("\\/")
    name = os.path.basename(cwd)
    try:
        return project_config.sanitize_project_name(name)
    except ValueError:
        return name


def search(project, query, limit):
    """Return a list of {score, collection, source, text} chunks, best first."""
    if not project:
        project = _default_project()
    vector = _embed(query)
    results = []
    for coll in project_config.collections_for(project):
        try:
            data = _post(f"{QDRANT_URL}/collections/{coll}/points/search",
                         {"vector": vector, "limit": limit, "with_payload": True})
            for pt in data.get("result", []):
                p = pt.get("payload", {}) or {}
                results.append({
                    "score": round(pt.get("score", 0.0), 4),
                    "collection": coll,
                    "source": p.get("source", ""),
                    "text": p.get("text", ""),
                })
        except urllib.error.HTTPError as e:
            results.append({"score": 0, "collection": coll,
                            "source": "ERROR", "text": f"collection '{coll}' unavailable: {e}"})
        except Exception as e:  # noqa: BLE001
            results.append({"score": 0, "collection": coll,
                            "source": "ERROR", "text": f"search error: {e}"})
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def _format(results, project, query):
    if not results:
        return f"No results in Qdrant for '{query}' (project '{project}')."
    lines = [f"Top {len(results)} chunks for '{query}' (project '{project}'):\n"]
    for r in results:
        lines.append(f"[{r['score']}] {r['source']}  (collection {r['collection']})")
        lines.append(r["text"].strip())
        lines.append("---")
    return "\n".join(lines)


TOOL = {
    "name": "limet_search",
    "description": (
        "Semantic search over this project's documentation indexed in Qdrant (CEREBRO RAG). "
        "Returns the most relevant chunks for the query. Call this BEFORE answering any "
        "question about the project, and ground your answer in the returned chunks."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string",
                      "description": "The question / topic to search for."},
            "project": {"type": "string",
                        "description": "Project slug (optional; default = current directory name)."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20,
                      "description": "Max results (default 5)."},
        },
        "required": ["query"],
    },
}


def _handle(msg):
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    def result(obj):
        return {"jsonrpc": "2.0", "id": req_id, "result": obj}

    def error(code, message):
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": code, "message": message}}

    if method == "initialize":
        proto = params.get("protocolVersion", PROTOCOL_VERSION)
        return result({
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "ping":
        return result({})
    if method == "tools/list":
        return result({"tools": [TOOL]})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name != "limet_search":
            return error(-32601, f"unknown tool: {name}")
        try:
            project = (args.get("project") or "").strip() or _default_project()
            query = (args.get("query") or "").strip()
            limit = int(args.get("limit") or 5)
            if not query:
                return error(-32602, "query is required")
            chunks = search(project, query, limit)
            return result({
                "content": [{"type": "text", "text": _format(chunks, project, query)}],
                "isError": False,
            })
        except Exception as e:  # noqa: BLE001
            return result({
                "content": [{"type": "text", "text": f"limet_search error: {e}"}],
                "isError": True,
            })
    return error(-32601, f"method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Notifications (no id) are ignored.
        if msg.get("id") is None:
            continue
        try:
            out = _handle(msg)
        except Exception as e:  # noqa: BLE001
            out = {"jsonrpc": "2.0", "id": msg.get("id"),
                   "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
