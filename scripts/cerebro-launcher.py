#!/usr/bin/env python3
"""
CEREBRO Launcher — local web UI to manage CEREBRO projects.

A single tool for both Claude Code and GitHub Copilot users: it replaces the
per-tool management (the /cerebro skill menu, the Copilot slash command and the
external cerebro_bridge CLI) with one browser SPA. 100% local: binds 127.0.0.1,
stdlib-only, no external calls beyond local Qdrant/Ollama.

Actions: new project, re-index, status, remove, query.

Usage:
    python scripts/cerebro-launcher.py [--port 8789]
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import project_config  # noqa: E402
try:
    project_config.load_env()
except ImportError:
    pass  # python-dotenv not installed: fall back to os.getenv defaults (standard local install)

HOST = "127.0.0.1"
DEFAULT_PORT = 8789
IS_WIN = os.name == "nt"

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0


def _subprocess_env():
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return env
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
IMAGES_PORT = os.getenv("IMAGES_PORT", "8777")


# --- helpers -----------------------------------------------------------------------------------


def read_html():
    with open(os.path.join(HERE, "launcher.html"), "r", encoding="utf-8") as f:
        return f.read()


def _venv_py():
    for c in (os.path.join(REPO_ROOT, ".venv", "Scripts", "python.exe"),
              os.path.join(REPO_ROOT, ".venv", "Scripts", "python"),
              os.path.join(REPO_ROOT, ".venv", "bin", "python")):
        if os.path.exists(c):
            return c
    return sys.executable


def _post(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_ok(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read()
        return True
    except Exception:
        return False


def _embedding(text):
    return _post(f"{OLLAMA_URL}/api/embeddings", {"model": EMBEDDING_MODEL, "prompt": text})["embedding"]


def _search(project, query, limit):
    vector = _embedding(query)
    results = []
    for coll in project_config.collections_for(project):
        try:
            data = _post(f"{QDRANT_URL}/collections/{coll}/points/search",
                         {"vector": vector, "limit": limit, "with_payload": True})
            for pt in data.get("result", []):
                p = pt.get("payload", {})
                results.append({
                    "score": round(pt.get("score", 0), 4),
                    "collection": coll,
                    "source": p.get("source", ""),
                    "title": p.get("title", ""),
                    "text": p.get("text", ""),
                    "image_urls": p.get("image_urls", []),
                    "image_paths": p.get("image_paths", []),
                })
        except Exception:
            pass
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def _count(collection):
    try:
        data = _post(f"{QDRANT_URL}/collections/{collection}/points/count", {"exact": True})
        return data.get("result", {}).get("count", 0)
    except Exception:
        return None


# --- command building --------------------------------------------------------------------------


def _limet_index_update(project):
    """Return argv to run the project's `limet-index update`, or None if not a LIMET project."""
    root = project_config.load_registry().get(project, {}).get("root", "")
    if not root:
        return None
    ps1 = os.path.join(root, "limet", "scripts", "limet-index.ps1")
    sh = os.path.join(root, "limet", "scripts", "limet-index.sh")
    if IS_WIN and os.path.exists(ps1):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                ps1, "update", "-ProjectPath", root, "-CerebroHome", REPO_ROOT]
    if os.path.exists(sh):
        return ["bash", sh, "update", "--project-path", root, "--cerebro-home", REPO_ROOT]
    return None


def build_commands(params):
    """Return the ordered list of (label, argv) for the run action."""
    action = params.get("action")
    py = _venv_py()
    reg = os.path.join(HERE, "register_project.py")
    ing = os.path.join(HERE, "ingest_docs.py")

    if action == "update":
        limet = _limet_index_update(params["project"])
        if limet:
            return [("Re-index (limet-index update)", limet)]
        return [("Re-index", [py, ing, "--project", params["project"]])]
    if action == "remove":
        return [("Remove from registry", [py, reg, "remove", params["project"]])]

    # action == "create"
    name = params["name"]
    docs = params.get("docs") or []
    root = (params.get("root") or "").strip()
    tool = params.get("tool") or "both"
    graphify = bool(params.get("graphify"))
    collections = params.get("collections") or []

    cmds = []
    add = [py, reg, "add", name, "--docs"] + docs
    if root:
        add += ["--root", root]
    if collections:
        add += ["--collections"] + collections
    cmds.append(("Register project", add))

    ins = [py, reg, "instructions", name, "--tool", tool]
    if graphify:
        ins += ["--graphify"]
    if root:
        ins += ["--root", root]
    cmds.append(("Generate agent instructions", ins))

    cmds.append(("Index documents", [py, ing, "--project", name]))
    return cmds


class Handler(BaseHTTPRequestHandler):
    server_version = "CerebroLauncher/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[launcher] " + (fmt % args) + "\n")

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _start_stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def _chunk(self, data):
        if not data:
            return
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.wfile.write(("%x\r\n" % len(data)).encode("ascii"))
        self.wfile.write(data)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def _end_stream(self):
        try:
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # --- GET -----------------------------------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = read_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif parsed.path == "/api/info":
            self._json({
                "repo_root": REPO_ROOT,
                "qdrant_up": _get_ok(f"{QDRANT_URL}/collections"),
                "ollama_up": _get_ok(OLLAMA_URL),
                "graphify_installed": shutil_which("graphify"),
                "images_port": IMAGES_PORT,
                "platform": "win" if IS_WIN else "unix",
            })
        elif parsed.path == "/api/projects":
            self._json(list(project_config.load_registry().keys()))
        elif parsed.path == "/api/status":
            registry = project_config.load_registry()
            projects = []
            for slug in sorted(registry):
                entry = registry[slug]
                coll = project_config.collection_for(slug)
                projects.append({
                    "slug": slug,
                    "collection": coll,
                    "chunks": _count(coll),
                    "root": entry.get("root", ""),
                    "docs": entry.get("docs", []),
                    "collections": entry.get("collections", []),
                })
            self._json(projects)
        elif parsed.path == "/api/shutdown":
            self._json({"ok": "shutting down"})

            def _shutdown():
                time.sleep(0.3)
                os._exit(0)
            threading.Thread(target=_shutdown).start()
        else:
            self.send_response(404)
            self.end_headers()

    # --- POST ----------------------------------------------------------------------------------

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/run":
            self._handle_run()
        elif parsed.path == "/api/query":
            self._handle_query()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_run(self):
        try:
            params = self._read_body()
        except Exception as e:
            self._json({"error": "bad request: %s" % e}, 400)
            return

        action = params.get("action")
        if action == "create" and not (params.get("name") or "").strip():
            self._json({"error": "project name is required"}, 400)
            return
        if action in ("update", "remove") and not (params.get("project") or "").strip():
            self._json({"error": "project is required"}, 400)
            return

        self._start_stream()
        ok = True
        try:
            for label, argv in build_commands(params):
                self._chunk("\n=== %s ===\n" % label)
                proc = subprocess.Popen(
                    argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    env=_subprocess_env(), creationflags=CREATE_NO_WINDOW,
                )
                for line in proc.stdout:
                    self._chunk(line)
                proc.wait()
                if proc.returncode != 0:
                    self._chunk("\n[ERRORE] '%s' exit %s — stopped.\n" % (label, proc.returncode))
                    ok = False
                    break
            self._chunk("\n" + ("Fatto.\n" if ok else ""))
        except Exception as e:
            self._chunk("\n[ERRORE] %s\n" % e)
        self._end_stream()

    def _handle_query(self):
        try:
            params = self._read_body()
            project = (params.get("project") or "").strip()
            query = (params.get("query") or "").strip()
            limit = int(params.get("limit") or 5)
            if not project or not query:
                self._json({"error": "project and query are required"}, 400)
                return
            results = _search(project, query, limit)
            self._json({"results": results})
        except Exception as e:
            self._json({"error": str(e)}, 500)


def shutil_which(name):
    import shutil
    return shutil.which(name) is not None


def main():
    port = DEFAULT_PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])

    httpd = None
    while httpd is None:
        try:
            httpd = HTTPServer((HOST, port), Handler)
        except OSError:
            port += 1

    url = "http://%s:%d/" % (HOST, port)
    print("CEREBRO launcher: %s" % url)
    print("Ctrl+C to stop.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
