"""
Local static server for extracted images.

Serves assets/ on http://localhost:<IMAGES_PORT>. URL:
    /<slug>/<source_rel>/images/fig_NNNN.png

Started automatically by ingest_docs.py if the port is free;
can also be run manually:
    .venv\\Scripts\\python scripts\\serve_images.py
"""
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from project_config import ASSETS_ROOT, load_env

load_env()

PORT = int(os.getenv("IMAGES_PORT", "8777"))
HOST = "127.0.0.1"


def main():
    handler = partial(SimpleHTTPRequestHandler, directory=str(ASSETS_ROOT))
    httpd = ThreadingHTTPServer((HOST, PORT), handler)
    print(f"Image server: {ASSETS_ROOT}")
    print(f"Listening on http://localhost:{PORT}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
