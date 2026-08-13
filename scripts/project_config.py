"""
Shared CEREBRO helper: project resolution -> Qdrant collection.

Naming: project "My App" -> collection "CRB_my_app".
Project resolution: --project flag > PROJECT env var > error.
Registry: projects.json in the repo root, maps slug -> {"docs": [path, ...]}.
Docs fallback: <repo>/projects/<slug>/docs.
"""
import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "projects.json"
ENV_PATH = REPO_ROOT / ".env"
ASSETS_ROOT = REPO_ROOT / "assets"


def assets_dir_for(project: str) -> Path:
    """Asset folder (markdown + images) for a project/collection."""
    return ASSETS_ROOT / sanitize_project_name(project)


def load_env() -> None:
    """Load variables from .env in the repo root (if present)."""
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH)


def sanitize_project_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise ValueError(f"Invalid project name: {name!r}")
    return slug


def collection_for(project: str) -> str:
    return f"CRB_{sanitize_project_name(project)}"


def resolve_project(explicit: str | None = None) -> str:
    project = explicit or os.getenv("PROJECT")
    if not project:
        raise SystemExit(
            "Project not specified. Use --project <name> or set the PROJECT variable."
        )
    return project


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(registry: dict) -> None:
    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def docs_paths_for(project: str) -> list[str]:
    slug = sanitize_project_name(project)
    entry = load_registry().get(slug)
    if entry and entry.get("docs"):
        return entry["docs"]
    return [str(REPO_ROOT / "projects" / slug / "docs")]
