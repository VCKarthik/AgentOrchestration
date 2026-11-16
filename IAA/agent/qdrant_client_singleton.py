"""
qdrant_client_singleton.py
Single process-wide QdrantClient instance.

Why this exists:
  The embedded Qdrant file-store takes an exclusive lock on its storage folder.
  If two QdrantClient(path=...) instances are created in the same process
  (e.g. one in ingest.py, one in retriever.py, one in streamlit_app.py),
  the second one fails with:
      "Storage folder ./qdrant_store is already accessed by another instance"
  Routing every caller through this singleton guarantees only one client
  is ever created per process.

Behaviour:
  - If QDRANT_HOST is set (Docker / remote server): use network client
  - Else: use local file-backed client at QDRANT_PATH
"""

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

QDRANT_PATH = os.getenv("QDRANT_PATH", "./qdrant_store")
QDRANT_HOST = os.getenv("QDRANT_HOST") or None
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

_client = None


def get_qdrant_client():
    """Return the process-wide QdrantClient instance, creating it on first call."""
    global _client
    if _client is not None:
        return _client
    from qdrant_client import QdrantClient
    if QDRANT_HOST:
        _client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    else:
        Path(QDRANT_PATH).mkdir(parents=True, exist_ok=True)
        _client = QdrantClient(path=QDRANT_PATH)
    return _client


# ── Local embedding model (sentence-transformers) ─────────────────────────────

_embedding_model = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


class LocalEmbeddingFn:
    def __call__(self, input):
        model = get_embedding_model()
        return model.encode(list(input)).tolist()

    def embed_documents(self, docs):
        return get_embedding_model().encode(list(docs)).tolist()

    def embed_query(self, text):
        return get_embedding_model().encode(text).tolist()
