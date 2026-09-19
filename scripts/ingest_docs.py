#!/usr/bin/env python3
"""
Index a project's documents into Qdrant.
Usage:
    python scripts/ingest_docs.py --project <name> [path ...]
"""
import argparse
import os
import re
import hashlib
import requests
from pathlib import Path
from urllib.parse import quote
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct
)

from project_config import (
    assets_dir_for,
    collection_for,
    docs_paths_for,
    load_env,
    resolve_project,
    sanitize_project_name,
)
from doc_to_markdown import extract_image_names, epub_to_markdown, pdf_to_markdown

load_env()

# Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
IMAGES_PORT = int(os.getenv("IMAGES_PORT", "8777"))
IMAGES_BASE_URL = f"http://localhost:{IMAGES_PORT}"
CHUNK_SIZE = 100
CHUNK_OVERLAP = 20
MAX_WORDS_PER_CHUNK = 150
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2

qdrant = QdrantClient(url=QDRANT_URL)

# Supported formats:
# - plain text read directly
# - PDF/EPUB converted to markdown WITH image extraction (doc_to_markdown)
# - the rest converted to markdown via markitdown (no images)
TEXT_EXTENSIONS = {".md", ".txt"}
IMAGE_EXTENSIONS = {".pdf", ".epub"}
MARKITDOWN_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".html", ".htm"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | MARKITDOWN_EXTENSIONS

_markitdown = None


def extract_text(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return file_path.read_text(encoding="utf-8")
    global _markitdown
    if _markitdown is None:
        from markitdown import MarkItDown
        _markitdown = MarkItDown()
    return _markitdown.convert(str(file_path)).text_content


def extract_markdown(file_path: Path, image_dir: Path) -> str:
    """Convert a file to markdown, saving images to image_dir.

    PDF/EPUB use the converter with image extraction; other formats stay on
    markitdown (no images)."""
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        markdown, _ = pdf_to_markdown(file_path, image_dir)
        return markdown
    if ext == ".epub":
        markdown, _ = epub_to_markdown(file_path, image_dir)
        return markdown
    return extract_text(file_path)


def setup_collection(collection_name: str):
    existing = [c.name for c in qdrant.get_collections().collections]
    if collection_name not in existing:
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
        )
        print(f"Collection '{collection_name}' created.")
    else:
        print(f"Collection '{collection_name}' already exists.")


IMAGE_ONLY_RE = re.compile(r"^(\s*!\[[^\]]*\]\([^)]+\)\s*)+$")


def _is_image_only(para: str) -> bool:
    """True if the paragraph contains only image links (to glue to the text above)."""
    return bool(IMAGE_ONLY_RE.match(para.strip()))


def chunk_text(text: str) -> list[str]:
    paragraphs = re.split(r'\n\n+', text)
    chunks, current_chunk, current_len = [], [], 0

    for para in paragraphs:
        para_len = len(para.split())
        if current_len + para_len > CHUNK_SIZE and current_chunk and not _is_image_only(para):
            chunks.append('\n\n'.join(current_chunk))
            overlap_words, overlap_paras = 0, []
            for p in reversed(current_chunk):
                overlap_words += len(p.split())
                if overlap_words >= CHUNK_OVERLAP:
                    break
                overlap_paras.insert(0, p)
            current_chunk = overlap_paras
            current_len = sum(len(p.split()) for p in current_chunk)
        current_chunk.append(para)
        current_len += para_len

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    result = []
    for c in chunks:
        words = c.split()
        if len(words) > MAX_WORDS_PER_CHUNK:
            for i in range(0, len(words), MAX_WORDS_PER_CHUNK):
                result.append(' '.join(words[i:i + MAX_WORDS_PER_CHUNK]))
        else:
            result.append(c)

    return [c.strip() for c in result if c.strip()]


def get_embedding(text: str) -> list[float]:
    import time
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": EMBEDDING_MODEL, "prompt": text},
                timeout=30
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except Exception as e:
            if attempt < RETRY_ATTEMPTS - 1:
                print(f"    Retry {attempt + 1}/{RETRY_ATTEMPTS - 1} after error: {e}")
                time.sleep(RETRY_DELAY)
            else:
                raise


def get_chunk_id(file_path: str, chunk_index: int) -> int:
    raw = f"{file_path}::{chunk_index}"
    return int(hashlib.md5(raw.encode()).hexdigest(), 16) % (2**63)


def ingest_file(file_path: Path, docs_root: Path, collection_name: str, slug: str):
    relative_path = file_path.relative_to(docs_root)

    if str(relative_path).startswith(".obsidian/"):
        print(f"  SKIP (obsidian): {relative_path}")
        return

    if "_templates" in relative_path.parts:
        print(f"  SKIP (templates): {relative_path}")
        return

    # Asset folder for this document: assets/<slug>/<source_rel>/document.md + images/
    rel_posix = str(relative_path).replace("\\", "/")
    source_subdir = rel_posix.rsplit(".", 1)[0]
    assets_dir = assets_dir_for(slug) / source_subdir
    image_dir = assets_dir / "images"

    text = extract_markdown(file_path, image_dir)

    # Archive the markdown on disk (relative image links, co-located with images/)
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "document.md").write_text(text, encoding="utf-8")

    title = file_path.stem
    first_line = text.split('\n')[0].strip()
    if first_line.startswith('# '):
        title = first_line[2:]

    chunks = chunk_text(text)
    print(f"  {relative_path}: {len(chunks)} chunks")

    url_base = "/".join(quote(seg) for seg in f"{slug}/{source_subdir}".split("/"))
    points = []
    for i, chunk in enumerate(chunks):
        try:
            image_names = [m for m in extract_image_names(chunk)]
            vector = get_embedding(chunk)
            points.append(PointStruct(
                id=get_chunk_id(str(file_path.resolve()), i),
                vector=vector,
                payload={
                    "text": chunk,
                    "source": str(relative_path),
                    "title": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "image_paths": [str(image_dir / n) for n in image_names],
                    "image_urls": [
                        f"{IMAGES_BASE_URL}/{url_base}/images/{n}" for n in image_names
                    ],
                }
            ))
        except Exception as e:
            print(f"    SKIP chunk {i} of {relative_path}: {e}")

    if points:
        qdrant.upsert(collection_name=collection_name, points=points)


def ingest_all(docs_path: str, collection_name: str, slug: str):
    docs_root = Path(docs_path)
    if not docs_root.exists():
        print(f"Folder '{docs_path}' not found.")
        return

    setup_collection(collection_name)
    if docs_root.is_file():
        if docs_root.suffix.lower() not in SUPPORTED_EXTENSIONS:
            print(f"Unsupported format: {docs_root} "
                  f"(allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))})")
            return
        doc_files = [docs_root]
    else:
        doc_files = [f for f in docs_root.rglob("*")
                     if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
    print(f"Found {len(doc_files)} files to index in '{docs_root}'...\n")

    for file_path in doc_files:
        try:
            ingest_file(file_path, docs_root if docs_root.is_dir() else docs_root.parent, collection_name, slug)
        except Exception as e:
            print(f"  ERROR on {file_path}: {e}")

    total = qdrant.count(collection_name=collection_name).count
    print(f"\nDone. Total chunks in '{collection_name}': {total}")


def ensure_image_server():
    """Start the static image server if it is not already listening on the port."""
    import socket
    import subprocess
    import sys

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", IMAGES_PORT)) == 0:
            print(f"Image server already running on http://localhost:{IMAGES_PORT}")
            return

    script = Path(__file__).resolve().parent / "serve_images.py"
    print(f"Starting image server on http://localhost:{IMAGES_PORT} ...")
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index docs into Qdrant for a CEREBRO project")
    parser.add_argument("paths", nargs="*",
                        help="Docs folders/files (registry override; default from projects.json or projects/<name>/docs)")
    parser.add_argument("--project", help="Project name (default: PROJECT env var)")
    args = parser.parse_args()

    project = resolve_project(args.project)
    collection_name = collection_for(project)
    slug = sanitize_project_name(project)
    print(f"Project: {project} -> collection {collection_name}\n")

    ensure_image_server()

    paths = args.paths or docs_paths_for(project)
    for p in paths:
        ingest_all(p, collection_name, slug)
