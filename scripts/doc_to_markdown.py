"""
PDF / EPUB -> Markdown conversion with image extraction.

Each function writes images to `image_dir` (deterministic `fig_NNNN.png`
names) and returns `(markdown, image_names)`.

The markdown uses RELATIVE image links: `![Figure](images/fig_NNNN.png)`.
Relative links are later resolved to absolute paths + URLs by ingest_docs.py.

PDF: uses pdfplumber (pypdfium2 backend) — text with y-position + raster image
bboxes, interleaved. Purely vector graphics (non-bitmap) do not appear in
page.images: covered only if detected as raster images.
EPUB: uses ebooklib + markdownify + beautifulsoup4 — spine chapters in order,
<img> tags with src rewritten to the extracted file.
"""
from __future__ import annotations

import posixpath
import re
from pathlib import Path

_IMG_LINK_RE = re.compile(r"!\[[^\]]*\]\(images/([^)\s]+)\)")

# EPUB media-type -> file extension
_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}

# Global counter for deterministic image names within a document.
_counter = 0


def _next_image() -> str:
    global _counter
    _counter += 1
    return f"fig_{_counter:04d}"


def _reset_counter() -> None:
    global _counter
    _counter = 0


def _write_image_bytes(data: bytes, ext: str, image_dir: Path) -> str | None:
    """Write image bytes and return the filename, or None if empty."""
    if not data:
        return None
    name = _next_image() + ext
    (image_dir / name).write_bytes(data)
    return name


def _render_region(page, bbox, image_dir: Path) -> str | None:
    """Render a page region to PNG and return the filename."""
    try:
        # bbox = (x0, top, x1, bottom) in top-origin coordinates ('top'/'bottom' keys)
        cropped = page.crop(tuple(bbox)).to_image(resolution=150)
        name = _next_image() + ".png"
        cropped.save(str(image_dir / name))
        return name
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def pdf_to_markdown(pdf_path: Path, image_dir: Path) -> tuple[str, list[str]]:
    import pdfplumber

    _reset_counter()
    image_dir.mkdir(parents=True, exist_ok=True)
    images: list[str] = []
    pages_md: list[str] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            events: list[tuple[float, str, object]] = []

            # Text with vertical position (top).
            try:
                for line in page.extract_text_lines():
                    text = (line.get("text") or "").strip()
                    if text:
                        events.append((line.get("top") or 0.0, "text", text))
            except Exception:
                pass

            # Raster images with bbox.
            try:
                for im in page.images:
                    bbox = (
                        im.get("x0") or 0.0,
                        im.get("top") or 0.0,
                        im.get("x1") or 0.0,
                        im.get("bottom") or 0.0,
                    )
                    events.append((bbox[1], "image", bbox))
            except Exception:
                pass

            if not events:
                continue

            events.sort(key=lambda e: e[0])

            lines: list[str] = []
            for _, kind, data in events:
                if kind == "text":
                    lines.append(data)
                else:  # image
                    name = _render_region(page, data, image_dir)
                    if name:
                        images.append(name)
                        lines.append(f"![Figure](images/{name})")

            if lines:
                pages_md.append("\n".join(lines))

    markdown = "\n\n".join(pages_md).strip()
    return markdown, images


# ---------------------------------------------------------------------------
# EPUB
# ---------------------------------------------------------------------------

def _resolve_href(doc_name: str, src: str) -> str:
    """Resolve a src relative to the EPUB document into a normalized href."""
    if not src or src.startswith(("data:", "http:", "https:")):
        return ""
    base = posixpath.dirname(doc_name)
    return posixpath.normpath(posixpath.join(base, src)) if base else src


def epub_to_markdown(epub_path: Path, image_dir: Path) -> tuple[str, list[str]]:
    import ebooklib
    from ebooklib import epub

    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    _reset_counter()
    image_dir.mkdir(parents=True, exist_ok=True)
    images: list[str] = []
    chapters: list[str] = []

    book = epub.read_epub(str(epub_path))

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        try:
            html = item.get_content().decode("utf-8")
        except Exception:
            continue

        doc_name = getattr(item, "get_name", lambda: "")() or ""
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(["img", "image"]):
            src = tag.get("src") or tag.get("xlink:href") or ""
            href = _resolve_href(doc_name, src)
            if not href:
                continue

            img_item = book.get_item_with_href(href)
            if img_item is None:
                continue

            ext = _MIME_EXT.get(
                getattr(img_item, "get_type", lambda: "")() or "",
                Path(href).suffix.lower() or ".png",
            )
            name = _write_image_bytes(img_item.get_content(), ext, image_dir)
            if name is None:
                continue

            images.append(name)
            if tag.name == "image":
                tag["href"] = f"images/{name}"
            else:
                tag["src"] = f"images/{name}"

        chapter = md(str(soup), heading_style="ATX").strip()
        if chapter:
            chapters.append(chapter)

    markdown = "\n\n".join(chapters).strip()
    return markdown, images


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def extract_image_names(markdown: str) -> list[str]:
    """Extract the image names referenced in the markdown (order of appearance)."""
    return [m for m in _IMG_LINK_RE.findall(markdown)]
