"""
qdrant_init.py — Create and populate Qdrant collections for AMP.

Two collections:
  iaa_corpus      — IAA RAG retrieval (process history)
  policy_knowledge — GPA + RRA policy doc retrieval (tag-filtered by case_type)

Embedder: all-MiniLM-L6-v2 (384-dim, same as IAA's existing setup).
Ingest sources:
  iaa_corpus:      data/synthetic_cases/iaa_corpus.json (if present)
  policy_knowledge: data/policies/*.md
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

EMBED_MODEL    = "all-MiniLM-L6-v2"
VECTOR_DIM     = 384
IAA_COLLECTION = "iaa_corpus"       # matches IAA/agent/retriever.py COLLECTION
GPA_COLLECTION = "policy_knowledge"

POLICIES_DIR    = Path(__file__).parent.parent / "data" / "policies"
IAA_CORPUS_FILE = Path(__file__).parent.parent / "data" / "synthetic_cases" / "iaa_corpus.json"

QDRANT_PATH = os.getenv("QDRANT_PATH", str(Path(__file__).parent / "qdrant_store"))
QDRANT_HOST = os.getenv("QDRANT_HOST", "")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))


def _get_client():
    from qdrant_client import QdrantClient
    if QDRANT_HOST:
        return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return QdrantClient(path=QDRANT_PATH)


def _get_embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL)


def _ensure_collection(client, name: str) -> None:
    from qdrant_client.models import Distance, VectorParams
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", name)
    else:
        logger.info("Collection already exists: %s", name)


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def ingest_policies(client, embedder) -> int:
    """
    Ingest policy markdown files into policy_knowledge collection.
    Tag each chunk with case_type inferred from filename:
      procurement.md -> case_type=vendor_onboarding
      claims.md      -> case_type=claim_review
      fraud.md       -> case_type=fraud_investigation
      *.md           -> case_type=general
    """
    from qdrant_client.models import PointStruct

    TYPE_MAP = {
        "procurement": "vendor_onboarding",
        "claims":      "claim_review",
        "fraud":       "fraud_investigation",
    }

    if not POLICIES_DIR.exists():
        logger.warning("Policies dir not found: %s", POLICIES_DIR)
        return 0

    _ensure_collection(client, GPA_COLLECTION)
    points: list[PointStruct] = []
    uid = 0

    for md_file in sorted(POLICIES_DIR.glob("*.md")):
        stem = md_file.stem.lower()
        case_type = TYPE_MAP.get(stem, "general")
        text = md_file.read_text(encoding="utf-8")
        chunks = _chunk_text(text)
        for i, chunk in enumerate(chunks):
            vec = embedder.encode(chunk).tolist()
            points.append(PointStruct(
                id=uid,
                vector=vec,
                payload={
                    "document":       chunk,
                    "case_type":      case_type,
                    "policy_section": f"{md_file.name}:chunk{i}",
                    "source":         md_file.name,
                },
            ))
            uid += 1

    if points:
        client.upsert(collection_name=GPA_COLLECTION, points=points)
    logger.info("Ingested %d policy chunks into %s", len(points), GPA_COLLECTION)
    return len(points)


def ingest_iaa_corpus(client, embedder) -> int:
    """
    Ingest synthetic cases into iaa_corpus collection for IAA RAG.
    Expects JSON array of {case_id, case_type, outcome, priority,
    executive_summary, resolution} objects.
    """
    from qdrant_client.models import PointStruct

    if not IAA_CORPUS_FILE.exists():
        logger.warning("IAA corpus file not found: %s — skipping", IAA_CORPUS_FILE)
        return 0

    _ensure_collection(client, IAA_COLLECTION)
    cases = json.loads(IAA_CORPUS_FILE.read_text(encoding="utf-8"))
    points: list[PointStruct] = []

    for i, case in enumerate(cases):
        text = f"{case.get('executive_summary', '')} {case.get('resolution', '')}".strip()
        if not text:
            continue
        vec = embedder.encode(text).tolist()
        points.append(PointStruct(
            id=i,
            vector=vec,
            payload={
                "document":  text,
                "case_id":   case.get("case_id", f"case-{i}"),
                "case_type": case.get("case_type", "general"),
                "outcome":   case.get("outcome", ""),
                "priority":  case.get("priority", "medium"),
                "source":    "synthetic_cases",
                "process_type": case.get("case_type", "general"),
                "next_action":  case.get("resolution", ""),
            },
        ))

    if points:
        client.upsert(collection_name=IAA_COLLECTION, points=points)
    logger.info("Ingested %d cases into %s", len(points), IAA_COLLECTION)
    return len(points)


def init_qdrant(ingest_cases: bool = True, ingest_policies_flag: bool = True) -> None:
    client  = _get_client()
    embedder = _get_embedder()
    if ingest_cases:
        ingest_iaa_corpus(client, embedder)
    if ingest_policies_flag:
        ingest_policies(client, embedder)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_qdrant()
