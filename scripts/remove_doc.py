#!/usr/bin/env python3
"""
Removes a document's chunks from the Qdrant index.
Usage:
    python scripts/remove_doc.py --project <name> --source "relative/path/file.md"
"""
import argparse
import os

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from project_config import collection_for, load_env, resolve_project

load_env()


def main():
    parser = argparse.ArgumentParser(description="Remove a document from the Qdrant index")
    parser.add_argument("--project", help="Project name (default: PROJECT env var)")
    parser.add_argument(
        "--source",
        required=True,
        help="Relative path of the file to remove",
    )
    args = parser.parse_args()

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection_name = collection_for(resolve_project(args.project))

    qdrant = QdrantClient(url=qdrant_url)
    result = qdrant.delete(
        collection_name=collection_name,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="source", match=MatchValue(value=args.source)
                )
            ]
        ),
    )
    print(f"Document '{args.source}' removed from '{collection_name}'.")
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
