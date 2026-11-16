"""
retriever.py
Domain-agnostic RAG retrieval for the IAA vector store.

Retrieves the top-k most relevant process history documents from Qdrant
based on the current process state. Uses metadata filtering to scope retrieval
without being hardcoded to any domain.
"""

from __future__ import annotations
import logging
import os
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
from .schemas import ProcessState
from .qdrant_client_singleton import get_qdrant_client, get_embedding_model

load_dotenv()

COLLECTION = "iaa_corpus"
DEFAULT_K  = 2          # was 4 — Phase 1 latency fix: smaller context, smaller prompt
MAX_DOC_CHARS = 400     # truncate retrieved doc bodies before prompt injection


def build_query(state: ProcessState) -> str:
    """
    Build a natural language query from the process state.
    This is what gets embedded and used for similarity search.
    Deliberately generic — no domain assumptions.
    """
    prior_str = " -> ".join(state.prior_actions[-3:]) if state.prior_actions else "none"
    parts = [
        f"Current process stage: {state.current_stage}",
        f"Most recent event: {state.current_event_type}",
        f"Recent prior actions: {prior_str}",
    ]
    if state.risk_severity:
        parts.append(f"Risk level: {state.risk_severity}")
    if state.risk_flags:
        parts.append(f"Risk flags: {', '.join(state.risk_flags[:3])}")
    if state.context_summary:
        parts.append(f"Context: {state.context_summary[:200]}")
    return "\n".join(parts)


class IAARetriever:
    """
    Retrieves relevant process history from Qdrant.
    Supports optional domain/process_type filtering via payload metadata.
    """

    def __init__(self, client=None, k: int = DEFAULT_K):
        self.k = k
        self._client   = client   # injected for testing; lazy-loaded otherwise
        self._embedder = None     # lazy-loaded

    @property
    def client(self):
        if self._client is None:
            from .ingest import ensure_collection
            self._client = get_qdrant_client()
            ensure_collection(self._client)
        return self._client

    def _get_embedder(self):
        if self._embedder is None:
            self._embedder = get_embedding_model()
        return self._embedder

    def retrieve(
        self,
        state: ProcessState,
        domain_filter: Optional[str] = None,
        process_type_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Retrieve top-k relevant process documents for the given state.

        Returns list of dicts with keys: id, document, metadata, distance
        Filters by domain/process_type only if explicitly provided.
        Graceful degradation: returns [] if collection is empty or search fails.
        """
        query = build_query(state)

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            # Build optional metadata filter
            qdrant_filter = None
            conditions = []
            if domain_filter:
                conditions.append(FieldCondition(key="domain", match=MatchValue(value=domain_filter)))
            if process_type_filter:
                conditions.append(FieldCondition(key="process_type", match=MatchValue(value=process_type_filter)))
            if conditions:
                qdrant_filter = Filter(must=conditions)

            embedder  = self._get_embedder()
            query_vec = embedder.encode(query).tolist()

            results = self.client.query_points(
                collection_name=COLLECTION,
                query=query_vec,
                limit=self.k,
                query_filter=qdrant_filter,
                with_payload=True,
            ).points

            return [
                {
                    "id":       str(r.id),
                    "document": r.payload.get("document", ""),
                    "metadata": {k: v for k, v in r.payload.items() if k != "document"},
                    "distance": r.score,
                }
                for r in results
            ]

        except Exception as e:
            logger.warning("retrieval failed, proceeding without context: %s", e)
            return []

    def format_for_prompt(self, retrieved: list[dict]) -> str:
        """
        Format retrieved documents into a prompt-ready string.
        Each chunk is a numbered entry with its metadata for traceability.
        """
        if not retrieved:
            return "No relevant historical cases found in the knowledge base."

        lines = []
        for i, r in enumerate(retrieved, 1):
            meta = r["metadata"]
            doc = (r.get("document") or "")
            if len(doc) > MAX_DOC_CHARS:
                doc = doc[:MAX_DOC_CHARS] + "…"
            lines.append(
                f"[Context {i}] Source: {meta.get('source','unknown')} | "
                f"Process: {meta.get('process_type','unknown')} | "
                f"Next observed: {meta.get('next_action','unknown')}\n"
                f"{doc}"
            )
        return "\n\n".join(lines)
