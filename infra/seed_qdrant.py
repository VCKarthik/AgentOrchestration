"""
seed_qdrant.py — Ingest synthetic cases and policy docs into Qdrant.

Collections:
  iaa_corpus      — IAA RAG (process history from synthetic_amp_states.json)
  policy_knowledge — GPA/RRA policy docs from data/policies/*.md

Idempotent: skips collection if it already contains documents.
Generates data/synthetic_cases/iaa_corpus.json from synthetic_amp_states.json
if the file is absent.

Run via: python -m infra.seed_qdrant
Or called from infra/init_all.py.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT              = Path(__file__).parent.parent
SYNTHETIC_STATES  = ROOT / "data" / "synthetic_amp_states.json"
IAA_CORPUS_FILE   = ROOT / "data" / "synthetic_cases" / "iaa_corpus.json"
POLICIES_DIR      = ROOT / "data" / "policies"


def _build_iaa_corpus() -> None:
    """
    Derive data/synthetic_cases/iaa_corpus.json from synthetic_amp_states.json.
    Each entry is shaped for ingest_iaa_corpus: {case_id, case_type, outcome,
    priority, executive_summary, resolution}.
    """
    if IAA_CORPUS_FILE.exists():
        logger.info("iaa_corpus.json already present — skipping generation")
        return

    if not SYNTHETIC_STATES.exists():
        logger.warning("synthetic_amp_states.json not found — iaa_corpus will be empty")
        IAA_CORPUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        IAA_CORPUS_FILE.write_text("[]", encoding="utf-8")
        return

    states = json.loads(SYNTHETIC_STATES.read_text(encoding="utf-8"))
    corpus = []
    for s in states:
        intake = s.get("task_intake") or {}
        da     = s.get("da_output") or {}
        rra    = s.get("risk_output") or {}
        iaa    = s.get("iaa_output") or {}

        rec_action = iaa.get("recommended_action") or {}
        resolution = rec_action.get("label") or da.get("assignment_reason") or ""

        summary_parts = [
            intake.get("title", ""),
            intake.get("description", ""),
        ]
        executive_summary = " — ".join(p for p in summary_parts if p)

        corpus.append({
            "case_id":           intake.get("case_id") or intake.get("task_id") or "",
            "case_type":         intake.get("case_type") or "general",
            "outcome":           da.get("status") or "unknown",
            "priority":          intake.get("priority") or "medium",
            "required_skills":   intake.get("required_skills") or [],
            "monetary_value":    intake.get("monetary_value"),
            "executive_summary": executive_summary,
            "resolution":        resolution,
        })

    IAA_CORPUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    IAA_CORPUS_FILE.write_text(json.dumps(corpus, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Generated iaa_corpus.json with %d entries", len(corpus))


def _collection_has_data(client, collection_name: str) -> bool:
    try:
        info = client.get_collection(collection_name)
        return info.points_count > 0
    except Exception:
        return False


def seed_qdrant() -> None:
    """Ingest cases + policies into Qdrant. Skips populated collections."""
    from infra.qdrant_init import (
        _get_client, _get_embedder,
        IAA_COLLECTION, GPA_COLLECTION,
        ingest_iaa_corpus, ingest_policies,
    )

    _build_iaa_corpus()

    client  = _get_client()
    embedder = _get_embedder()

    if _collection_has_data(client, IAA_COLLECTION):
        logger.info("Collection '%s' already populated — skipping", IAA_COLLECTION)
    else:
        n = ingest_iaa_corpus(client, embedder)
        logger.info("Ingested %d cases into %s", n, IAA_COLLECTION)

    if _collection_has_data(client, GPA_COLLECTION):
        logger.info("Collection '%s' already populated — skipping", GPA_COLLECTION)
    else:
        n = ingest_policies(client, embedder)
        logger.info("Ingested %d policy chunks into %s", n, GPA_COLLECTION)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_qdrant()
