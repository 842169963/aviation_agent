"""
Step 5: Build Vector Index
==========================
Build a local ChromaDB index from output/extracted.json.

This is the vector side of Hybrid RAG v1:
- one document per procedure
- embeddings from an OpenAI-compatible endpoint
- metadata keeps procedure identity and provenance

Usage:
    python scripts/05_build_vector_index.py
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI


if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACTED_FILE = PROJECT_ROOT / "output" / "extracted.json"
VECTOR_DIR = PROJECT_ROOT / "output" / "vector_index"
COLLECTION_NAME = "aviation_procedures"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def slugify(value: str) -> str:
    """Create a stable id fragment from a procedure name."""
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")[:60] or "procedure"


def load_embedding_client() -> tuple[OpenAI, str]:
    """Load an OpenAI-compatible embedding client from .env."""
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    base_url = os.getenv("OPENAI_BASE_URL") or None
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    model = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)

    if provider == "gemini" and not base_url:
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

    if not api_key:
        raise RuntimeError("No API key found. Set OPENAI_API_KEY or GEMINI_API_KEY in .env.")

    return OpenAI(api_key=api_key, base_url=base_url), model


def build_procedure_document(proc: dict) -> str:
    """Convert one procedure to a retrieval document."""
    lines = [
        f"Procedure: {proc.get('name', '')}",
        f"Trigger: {proc.get('trigger_condition', '')}",
        f"Phase: {proc.get('aircraft_phase', '')}",
        f"Source: {proc.get('source_file', '')}",
        f"Section: {proc.get('source_section', '')}",
        f"Excerpt: {proc.get('source_excerpt', '')}",
        "",
        "Steps:",
    ]

    for step in proc.get("steps", []):
        number = step.get("step_number", "")
        step_type = step.get("step_type", "")
        action = step.get("action", "")
        expected = step.get("expected_result", "")
        excerpt = step.get("source_excerpt", "")
        type_suffix = f" [{step_type}]" if step_type else ""
        lines.append(f"{number}. {action}{type_suffix}")
        if expected:
            lines.append(f"   Expected result: {expected}")
        if excerpt:
            lines.append(f"   Evidence: {excerpt}")

    warnings = proc.get("warnings", [])
    if warnings:
        lines.extend(["", "Warnings:"])
        for warning in warnings:
            desc = warning.get("description", "")
            if desc:
                lines.append(f"- {desc}")

    return "\n".join(lines).strip()


def metadata_for_procedure(proc: dict, index: int) -> dict:
    """Create Chroma-compatible metadata. Values cannot be None."""
    return {
        "procedure_index": index,
        "procedure_name": proc.get("name") or "",
        "source_file": proc.get("source_file") or "",
        "source_section": proc.get("source_section") or "",
        "aircraft_phase": proc.get("aircraft_phase") or "",
    }


def embed_texts(client: OpenAI, model: str, texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """Embed texts in small batches to keep provider behavior predictable."""
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        embeddings.extend(item.embedding for item in response.data)
    return embeddings


def build_index(reset: bool = True) -> None:
    if not EXTRACTED_FILE.exists():
        raise FileNotFoundError(f"Missing extracted data: {EXTRACTED_FILE}")

    with EXTRACTED_FILE.open(encoding="utf-8") as f:
        extracted = json.load(f)

    procedures = extracted.get("procedures", [])
    if not procedures:
        raise RuntimeError("No procedures found in extracted.json.")

    ids = []
    documents = []
    metadatas = []
    for index, proc in enumerate(procedures):
        name = proc.get("name") or f"procedure_{index}"
        ids.append(f"proc_{index}_{slugify(name)}")
        documents.append(build_procedure_document(proc))
        metadatas.append(metadata_for_procedure(proc, index))

    print("Building vector index")
    print(f"extracted_file={EXTRACTED_FILE}")
    print(f"procedure_documents={len(documents)}")

    client, model = load_embedding_client()
    print(f"embedding_model={model}")

    embeddings = embed_texts(client, model, documents)
    if not embeddings:
        raise RuntimeError("Embedding provider returned no vectors.")

    print(f"embedding_dimensions={len(embeddings[0])}")

    chroma_client = chromadb.PersistentClient(path=str(VECTOR_DIR))
    if reset:
        try:
            chroma_client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )

    print(f"collection={COLLECTION_NAME}")
    print(f"vector_index={VECTOR_DIR}")
    print("status=OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build aviation procedure vector index")
    parser.add_argument("--no-reset", action="store_true", help="Append to existing index instead of rebuilding it")
    args = parser.parse_args()

    build_index(reset=not args.no_reset)


if __name__ == "__main__":
    main()
