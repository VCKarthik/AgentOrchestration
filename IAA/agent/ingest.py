"""
ingest.py
Universal ingestion pipeline for the IAA vector store.

Handles:
  - BPIC XES files (2012, 2018, 2019) via pm4py
  - CUAD contract dataset via HuggingFace datasets
  - Any tabular CSV/JSON event log via column mapping config

Design:
  - All data goes into ONE Qdrant collection: "iaa_corpus"
  - Domain identity is stored as metadata (source, domain, process_type)
  - Retrieval uses metadata filtering — no separate collections per domain
  - Raw XES files are never kept after ingestion — sample 500 cases, embed, discard
  - Vectors are 768-dim (text-embedding-004), cosine distance
"""

from __future__ import annotations
import os, json, hashlib, uuid, warnings
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

from .qdrant_client_singleton import (
    get_qdrant_client,
    LocalEmbeddingFn,
    QDRANT_PATH,
    QDRANT_HOST,
    QDRANT_PORT,
)

COLLECTION  = "iaa_corpus"
VECTOR_SIZE = 384          # all-MiniLM-L6-v2 output dimension
MAX_CASES   = 500

# Column mapping configs
BPIC_COLUMN_MAP = {
    "case:concept:name": "entity_id",
    "concept:name":      "event_type",
    "time:timestamp":    "timestamp",
    "org:resource":      "actor",
    "lifecycle:transition": "outcome",
}

CUAD_COLUMN_MAP = {
    "id":      "entity_id",
    "title":   "event_type",
    "context": "stage",
}


# ── Qdrant client setup ───────────────────────────────────────────────────────

def ensure_collection(client) -> None:
    """Create the IAA corpus collection if it does not already exist."""
    from qdrant_client.models import Distance, VectorParams
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def _get_embedder():
    """Local sentence-transformers embedder (all-MiniLM-L6-v2, 384-dim)."""
    return LocalEmbeddingFn()


# ── ID helpers ────────────────────────────────────────────────────────────────

def _make_id(text: str, prefix: str = "") -> str:
    """
    Deterministic UUID from content hash — prevents duplicates on re-ingestion.
    Includes prefix in hash so same text with different prefix gets different ID.
    """
    content = f"{prefix}:{text}" if prefix else text
    h = hashlib.md5(content.encode()).digest()
    return str(uuid.UUID(bytes=h))


# ── BPIC XES ingestion ────────────────────────────────────────────────────────

def ingest_bpic_xes(
    xes_path: str,
    source_name: str,       # e.g. "bpic_2012", "bpic_2019"
    process_type: str,      # e.g. "loan_application", "purchase_order"
    domain: str = "finance",
    max_cases: int = MAX_CASES,
    client=None,
) -> int:
    """
    Convert a BPIC XES file to process-state documents and embed into Qdrant.
    Returns the number of documents ingested.

    Each document = one process state snapshot (case up to event N, next event = label).
    This gives the IAA real ground-truth next-action patterns to retrieve from.
    """
    try:
        import pm4py
    except ImportError:
        raise ImportError("pm4py required: pip install pm4py --break-system-packages")

    print(f"[ingest] Reading {xes_path} ...")
    log = pm4py.read_xes(xes_path)
    df  = pm4py.convert_to_dataframe(log)

    # Rename columns to universal schema
    rename = {k: v for k, v in BPIC_COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    df = df.sort_values("timestamp")

    _client = client or get_qdrant_client()
    ensure_collection(_client)

    docs, ids, metas = [], [], []
    case_count = 0

    for entity_id, group in df.groupby("entity_id"):
        if case_count >= max_cases:
            break
        group = group.reset_index(drop=True)
        sequence = group["event_type"].tolist()

        for i in range(1, min(len(sequence), 8)):  # cap at 8 steps per case
            prior  = sequence[:i]
            nxt    = sequence[i] if i < len(sequence) else "END"
            stage  = str(group.get("stage", group["event_type"]).iloc[i-1]) if "stage" in group.columns else prior[-1]
            actor  = str(group["actor"].iloc[i-1]) if "actor" in group.columns else "unknown"

            text = (
                f"Process: {process_type}\n"
                f"Current stage: {stage}\n"
                f"Current event: {prior[-1]}\n"
                f"Actor: {actor}\n"
                f"Prior actions: {' -> '.join(prior[:-1]) if len(prior) > 1 else 'none'}\n"
                f"Next observed action: {nxt}"
            )

            doc_id = _make_id(text, prefix=source_name)
            if doc_id in ids:
                continue

            docs.append(text)
            ids.append(doc_id)
            metas.append({
                "source":        source_name,
                "domain":        domain,
                "process_type":  process_type,
                "entity_id":     str(entity_id),
                "current_event": prior[-1],
                "stage":         stage,
                "next_action":   nxt,
                "doc_type":      "process_trace",
                "actor":         actor,
            })

        case_count += 1

    _batch_add(_client, docs, ids, metas)
    print(f"[ingest] {source_name}: {len(docs)} documents from {case_count} cases")
    return len(docs)


# ── CUAD ingestion ────────────────────────────────────────────────────────────

def ingest_cuad(
    client=None,
    max_docs: int = 200,
) -> int:
    """
    Ingest CUAD contract dataset from HuggingFace.
    Each contract clause becomes a retrievable document about contract review processes.
    """
    try:
        from datasets import load_dataset
    except ImportError:
        raise ImportError("datasets required: pip install datasets --break-system-packages")

    print("[ingest] Loading CUAD from HuggingFace ...")
    ds = load_dataset("theatticusproject/cuad", split="train", trust_remote_code=True)
    _client = client or get_qdrant_client()
    ensure_collection(_client)
    docs, ids, metas = [], [], []

    for i, row in enumerate(ds):
        if i >= max_docs:
            break
        clause_type = str(row.get("title", "unknown_clause"))
        context     = str(row.get("context", ""))[:800]
        if not context.strip():
            continue

        text = (
            f"Process: contract_review\n"
            f"Document type: {clause_type}\n"
            f"Relevant clause content:\n{context}"
        )
        doc_id = _make_id(text, prefix="cuad")
        docs.append(text)
        ids.append(doc_id)
        metas.append({
            "source":       "cuad",
            "domain":       "legal",
            "process_type": "contract_review",
            "doc_type":     "policy_clause",
            "clause_type":  clause_type,
        })

    _batch_add(_client, docs, ids, metas)
    print(f"[ingest] CUAD: {len(docs)} clause documents")
    return len(docs)


# ── Generic CSV/JSON tabular ingestion ────────────────────────────────────────

def ingest_tabular(
    file_path: str,
    column_map: dict[str, str],
    source_name: str,
    domain: str,
    process_type: str,
    client=None,
    max_rows: int = MAX_CASES,
) -> int:
    """
    Ingest any CSV or JSON event log by providing a column mapping config.
    This is the entry point for client-specific data.
    """
    path = Path(file_path)
    if path.suffix == ".csv":
        df = pd.read_csv(file_path)
    elif path.suffix == ".json":
        df = pd.read_json(file_path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix} — use .csv or .json")

    df = df.rename(columns=column_map)
    required = {"entity_id", "event_type"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"After column mapping, still missing required fields: {missing}")

    if "timestamp" in df.columns:
        df = df.sort_values("timestamp")

    _client = client or get_qdrant_client()
    ensure_collection(_client)
    docs, ids, metas = [], [], []
    case_count = 0

    for entity_id, group in df.groupby("entity_id"):
        if case_count >= max_rows:
            break
        sequence = group["event_type"].tolist()

        for i in range(1, min(len(sequence), 8)):
            prior = sequence[:i]
            nxt   = sequence[i] if i < len(sequence) else "END"
            stage = str(group.get("stage", pd.Series([prior[-1]])).iloc[i-1]) if "stage" in group.columns else prior[-1]

            text = (
                f"Process: {process_type}\n"
                f"Current stage: {stage}\n"
                f"Current event: {prior[-1]}\n"
                f"Prior actions: {' -> '.join(prior[:-1]) if len(prior) > 1 else 'none'}\n"
                f"Next observed action: {nxt}"
            )
            doc_id = _make_id(text, prefix=source_name)
            docs.append(text)
            ids.append(doc_id)
            metas.append({
                "source":        source_name,
                "domain":        domain,
                "process_type":  process_type,
                "entity_id":     str(entity_id),
                "current_event": prior[-1],
                "stage":         stage,
                "next_action":   nxt,
                "doc_type":      "process_trace",
            })
        case_count += 1

    _batch_add(_client, docs, ids, metas)
    print(f"[ingest] {source_name}: {len(docs)} documents from {case_count} cases")
    return len(docs)


# ── Batch add helper ──────────────────────────────────────────────────────────

def _batch_add(
    client,
    docs: list[str],
    ids:  list[str],
    metas: list[dict],
    batch_size: int = 100,
) -> None:
    """
    Embed and upsert documents into Qdrant in batches.

    Two-step deduplication:
      1. Dedupe within the incoming batch (same content hash → same UUID)
      2. Check the collection for already-present IDs — skip re-embedding
    """
    from qdrant_client.models import PointStruct

    if not ids:
        return

    # Step 1: deduplicate within incoming batch
    seen: dict[str, tuple] = {}
    for d, i, m in zip(docs, ids, metas):
        if i not in seen:
            seen[i] = (d, m)
    unique_ids   = list(seen.keys())
    unique_docs  = [seen[i][0] for i in unique_ids]
    unique_metas = [seen[i][1] for i in unique_ids]

    # Step 2: check what is already in the collection
    try:
        existing_points = client.retrieve(
            collection_name=COLLECTION,
            ids=unique_ids,
            with_payload=False,
            with_vectors=False,
        )
        already_in = {str(p.id) for p in existing_points}
    except Exception:
        already_in = set()

    new_items = [
        (d, i, m)
        for d, i, m in zip(unique_docs, unique_ids, unique_metas)
        if i not in already_in
    ]

    if not new_items:
        print("[ingest] All documents already present — skipping")
        return

    nd, ni, nm = zip(*new_items)
    nd, ni, nm = list(nd), list(ni), list(nm)

    embedder = _get_embedder()

    for start in range(0, len(nd), batch_size):
        batch_docs  = nd[start:start + batch_size]
        batch_ids   = ni[start:start + batch_size]
        batch_metas = nm[start:start + batch_size]

        embeddings = embedder.embed_documents(batch_docs)

        points = [
            PointStruct(
                id=bid,
                vector=emb,
                payload={**meta, "document": doc},
            )
            for doc, bid, meta, emb in zip(batch_docs, batch_ids, batch_metas, embeddings)
        ]
        client.upsert(collection_name=COLLECTION, points=points)

    print(f"[ingest] Added {len(new_items)} new documents ({len(docs) - len(new_items)} skipped)")


# ── Synthetic data helper ─────────────────────────────────────────────────────

def ingest_synthetic_cases(
    cases: list[dict],
    source_name: str = "synthetic",
    domain: str = "generic",
    process_type: str = "generic_workflow",
    client=None,
) -> int:
    """
    Ingest pre-built synthetic cases directly.
    Each case must have: entity_id, event_type, prior_actions[], next_action.
    Includes actor info in the embedded document text for LLM grounding.
    """
    _client = client or get_qdrant_client()
    ensure_collection(_client)
    docs, ids, metas = [], [], []

    for case in cases:
        prior = case.get("prior_actions", [])
        nxt   = case.get("next_action", "unknown")
        stage = case.get("stage", case.get("event_type", "unknown"))

        # Resolve actor — from actor_sequence if available, else fallback
        actor_seq = case.get("actor_sequence", [])
        current_actor = "unknown"
        if actor_seq:
            # Last entry in actor_sequence corresponds to the current event
            current_actor = actor_seq[-1].get("actor", "unknown") if actor_seq else "unknown"

        text = (
            f"Process: {process_type}\n"
            f"Current stage: {stage}\n"
            f"Current event: {case.get('event_type', 'unknown')}\n"
            f"Actor: {current_actor}\n"
            f"Prior actions: {' -> '.join(prior) if prior else 'none'}\n"
            f"Next observed action: {nxt}"
        )
        # Include entity_id in the hash so cases with identical event sequences
        # still get unique IDs — prevents dedup from dropping real cases.
        unique_text = f"{case.get('entity_id', '')}__{text}"
        doc_id = _make_id(unique_text, prefix=source_name)
        docs.append(text)
        ids.append(doc_id)
        metas.append({
            "source":        source_name,
            "domain":        domain,
            "process_type":  process_type,
            "entity_id":     str(case.get("entity_id", "unknown")),
            "current_event": case.get("event_type", "unknown"),
            "stage":         stage,
            "next_action":   nxt,
            "doc_type":      "synthetic_trace",
            "actor":         current_actor,
        })

    _batch_add(_client, docs, ids, metas)
    return len(docs)


# ── BPIC 2012 convenience wrapper ─────────────────────────────────────────────

def ingest_bpic2012(
    xes_path: str = None,
    max_cases: int = 100,
    collection=None,
) -> int:
    """
    Ingest BPIC 2012 (loan application process) into the corpus.
    If xes_path not provided, attempts download from 4TU.
    Maps to insurance claim review workflow for demo purposes.
    """
    import pm4py, pandas as pd
    from pathlib import Path

    if xes_path is None:
        xes_path = "data/raw/BPI_Challenge_2012.xes"
        Path("data/raw").mkdir(parents=True, exist_ok=True)
        if not Path(xes_path).exists():
            print("[bpic] Downloading BPIC 2012 (~25MB)...")
            import urllib.request
            url = "https://data.4tu.nl/file/533f6d6a-c8af-4cf2-8b92-5f2d9d40c1c7/2d0d7da0-6848-48db-a34f-2c09e1e09a3b"
            try:
                urllib.request.urlretrieve(url, xes_path + ".gz")
                import gzip, shutil
                with gzip.open(xes_path + ".gz", "rb") as f_in:
                    with open(xes_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                Path(xes_path + ".gz").unlink(missing_ok=True)
            except Exception as e:
                print(f"[bpic] Download failed: {e}")
                print(f"[bpic] Download manually from https://data.4tu.nl/articles/_/12696884/1")
                print(f"[bpic] Place .xes file at: {xes_path}")
                return 0

    print(f"[bpic] Reading {xes_path}...")
    log = pm4py.read_xes(xes_path)
    df  = pm4py.convert_to_dataframe(log)
    df  = df.rename(columns={
        "case:concept:name": "entity_id",
        "concept:name":      "event_type",
        "time:timestamp":    "timestamp",
        "org:resource":      "actor",
    })
    df = df.sort_values("timestamp")

    STAGE_MAP = {
        "A_SUBMITTED":              "intake",
        "A_PARTLYSUBMITTED":        "intake",
        "W_Completeren aanvraag":   "document_verification",
        "A_PREACCEPTED":            "pre_approval",
        "O_SELECTED":               "offer_review",
        "W_Nabellen offertes":      "follow_up",
        "A_ACCEPTED":               "approved",
        "A_DECLINED":               "rejected",
        "A_CANCELLED":              "cancelled",
    }

    _client = collection or get_qdrant_client()
    ensure_collection(_client)
    docs, ids, metas = [], [], []
    case_count = 0

    for entity_id, group in df.groupby("entity_id"):
        if case_count >= max_cases:
            break
        group = group.sort_values("timestamp").reset_index(drop=True)
        sequence = group["event_type"].tolist()
        actors   = group["actor"].fillna("unknown").tolist()

        for i in range(1, min(len(sequence), 8)):
            prior  = sequence[:i]
            nxt    = sequence[i] if i < len(sequence) else "END"
            stage  = STAGE_MAP.get(prior[-1], prior[-1])
            actor  = str(actors[i - 1]) if i - 1 < len(actors) else "unknown"
            amount = str(group.get("case:AMOUNT_REQ", pd.Series(["unknown"])).iloc[0])

            text = (
                f"Process: insurance_claim_review\n"
                f"Current stage: {stage}\n"
                f"Current event: {prior[-1]}\n"
                f"Actor: {actor}\n"
                f"Prior actions: {' -> '.join(prior[:-1]) if len(prior) > 1 else 'none'}\n"
                f"Case value: {amount}\n"
                f"Next observed action: {nxt}"
            )
            doc_id = _make_id(f"{entity_id}__{text}", prefix="bpic_2012")

            docs.append(text)
            ids.append(doc_id)
            metas.append({
                "source":        "bpic_2012",
                "domain":        "finance",
                "process_type":  "insurance_claim_review",
                "entity_id":     str(entity_id),
                "current_event": prior[-1],
                "stage":         stage,
                "next_action":   nxt,
                "doc_type":      "real_trace",
                "amount":        amount,
            })
        case_count += 1

    _batch_add(_client, docs, ids, metas)
    print(f"[bpic] Ingested {len(docs)} documents from {case_count} real cases")
    return len(docs)


# ── Bootstrap helper ──────────────────────────────────────────────────────────

def bootstrap_corpus(
    include_synthetic: bool = True,
    include_bpic: bool = False,
    include_cuad: bool = False,
    synthetic_path: str = "data/synthetic_cases.json",
    client=None,
) -> int:
    """
    One-shot corpus bootstrap for the IAA.
    Call this once after setting up your environment.

    Fastest path:
        bootstrap_corpus(include_synthetic=True)
    """
    _client = client or get_qdrant_client()
    ensure_collection(_client)
    total = 0

    if include_synthetic:
        synthetic_path_obj = Path(synthetic_path)
        if not synthetic_path_obj.exists():
            print(f"[bootstrap] Synthetic cases not found at {synthetic_path}")
            print(f"[bootstrap] Run: python scripts/generate_synthetic.py first")
        else:
            import json as _json
            cases = _json.load(open(synthetic_path))
            by_type: dict[str, list] = {}
            for c in cases:
                pt = c.get("process_type", "generic")
                by_type.setdefault(pt, []).append(c)
            for pt, pt_cases in by_type.items():
                n = ingest_synthetic_cases(
                    pt_cases,
                    source_name="synthetic",
                    domain=pt_cases[0].get("domain", "generic"),
                    process_type=pt,
                    client=_client,
                )
                total += n

    if include_bpic:
        for key in ["bpic_2012", "bpic_2019", "bpic_2018"]:
            try:
                total += download_bpic(key, client=_client)
            except Exception as e:
                print(f"[bootstrap] {key} failed: {e} — skipping")

    if include_cuad:
        try:
            total += ingest_cuad(client=_client)
        except Exception as e:
            print(f"[bootstrap] CUAD failed: {e} — skipping")

    try:
        count = _client.count(collection_name=COLLECTION).count
        print(f"\n[bootstrap] Corpus ready. Total documents: {count}")
    except Exception:
        print(f"\n[bootstrap] Corpus ready. Total documents ingested this run: {total}")
    return total


# ── BPIC download helpers ─────────────────────────────────────────────────────

BPIC_URLS = {
    "bpic_2012": {
        "url":          "https://data.4tu.nl/file/533f6d6a-c8af-4cf2-8b92-5f2d9d40c1c7/2d0d7da0-6848-48db-a34f-2c09e1e09a3b",
        "filename":     "BPI_Challenge_2012.xes.gz",
        "source_name":  "bpic_2012",
        "process_type": "loan_application",
        "domain":       "finance",
    },
    "bpic_2019": {
        "url":          "https://data.4tu.nl/file/35801e9a-870e-4b66-a2b3-d1a3c4f3a4e0/e00efdc5-993e-480e-9b81-4d1ca8a42c3f",
        "filename":     "BPI_Challenge_2019.xes.gz",
        "source_name":  "bpic_2019",
        "process_type": "purchase_order",
        "domain":       "procurement",
    },
    "bpic_2018": {
        "url":          "https://data.4tu.nl/file/6a668d53-3ba6-4e2f-8ecd-2b8339dce3c5/a1ea4e98-6b8b-4e8e-9c58-c0e76e7e8e9f",
        "filename":     "BPI_Challenge_2018.xes.gz",
        "source_name":  "bpic_2018",
        "process_type": "subsidy_application",
        "domain":       "government",
    },
}

BPIC_FALLBACK_URLS = {
    "bpic_2012": "https://zenodo.org/record/3968401/files/BPI_Challenge_2012.xes.gz",
}


def download_bpic(
    dataset_key: str,
    download_dir: str = "./data/raw",
    max_cases: int = MAX_CASES,
    client=None,
) -> int:
    """Download a BPIC dataset, ingest into Qdrant, and remove the raw file."""
    import urllib.request

    if dataset_key not in BPIC_URLS:
        raise ValueError(f"Unknown dataset: {dataset_key}. Choose from: {list(BPIC_URLS.keys())}")

    cfg = BPIC_URLS[dataset_key]
    Path(download_dir).mkdir(parents=True, exist_ok=True)

    gz_path  = Path(download_dir) / cfg["filename"]
    xes_path = Path(download_dir) / cfg["filename"].replace(".gz", "")

    if xes_path.exists():
        print(f"[download] {xes_path} already exists — skipping download")
    elif gz_path.exists():
        print(f"[download] {gz_path} already exists — decompressing")
        _decompress_gz(gz_path, xes_path)
    else:
        print(f"[download] Downloading {dataset_key} (~50–200MB) ...")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (research use)"}
            req = urllib.request.Request(cfg["url"], headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r, open(gz_path, "wb") as f:
                total = int(r.headers.get("Content-Length", 0))
                downloaded = 0
                chunk = 65536
                while True:
                    buf = r.read(chunk)
                    if not buf:
                        break
                    f.write(buf)
                    downloaded += len(buf)
                    if total:
                        print(f"\r[download] {downloaded/total*100:.1f}%", end="", flush=True)
            print()
            _decompress_gz(gz_path, xes_path)
        except Exception as e:
            print(f"\n[download] Download failed: {e}")
            return 0

    _client = client or get_qdrant_client()
    n = ingest_bpic_xes(
        str(xes_path),
        cfg["source_name"],
        cfg["process_type"],
        cfg["domain"],
        max_cases=max_cases,
        client=_client,
    )
    try:
        xes_path.unlink()
        if gz_path.exists():
            gz_path.unlink()
        print(f"[download] Raw files removed — embeddings persisted in Qdrant")
    except Exception:
        pass
    return n


def _decompress_gz(gz_path: Path, out_path: Path) -> None:
    import gzip
    print(f"[download] Decompressing {gz_path.name} ...")
    with gzip.open(gz_path, "rb") as f_in, open(out_path, "wb") as f_out:
        f_out.write(f_in.read())
    print(f"[download] Decompressed to {out_path}")


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys
    parser = argparse.ArgumentParser(description="IAA corpus ingestion pipeline")

    parser.add_argument("--bootstrap",      action="store_true", help="Bootstrap corpus from synthetic cases (fastest)")
    parser.add_argument("--bootstrap-full", action="store_true", help="Bootstrap with synthetic + BPIC download + CUAD")
    parser.add_argument("--bpic2012",  help="Path to BPI_Challenge_2012.xes")
    parser.add_argument("--bpic2019",  help="Path to BPI_Challenge_2019.xes")
    parser.add_argument("--bpic2018",  help="Path to BPI_Challenge_2018.xes")
    parser.add_argument("--bpic",      action="store_true", help="Ingest BPIC 2012 dataset (auto-download if needed)")
    parser.add_argument("--download",  choices=["bpic_2012","bpic_2019","bpic_2018"])
    parser.add_argument("--cuad",      action="store_true")
    parser.add_argument("--csv",       help="Path to custom CSV event log")
    parser.add_argument("--source",    default="custom")
    parser.add_argument("--domain",    default="generic")
    parser.add_argument("--process",   default="generic_workflow")
    parser.add_argument("--status",    action="store_true", help="Show corpus stats and exit")
    args = parser.parse_args()

    _client = get_qdrant_client()
    ensure_collection(_client)

    if args.status:
        try:
            count = _client.count(collection_name=COLLECTION).count
            print(f"Corpus document count: {count}")
        except Exception as e:
            print(f"Could not count documents: {e}")
        sys.exit(0)

    total = 0

    if args.bootstrap:
        total += bootstrap_corpus(include_synthetic=True, client=_client)
    elif args.bootstrap_full:
        total += bootstrap_corpus(include_synthetic=True, include_bpic=True, include_cuad=True, client=_client)
    else:
        if args.bpic:
            total += ingest_bpic2012(collection=_client)
        if args.download:
            total += download_bpic(args.download, client=_client)
        if args.bpic2012:
            total += ingest_bpic_xes(args.bpic2012, "bpic_2012", "loan_application", "finance", client=_client)
        if args.bpic2019:
            total += ingest_bpic_xes(args.bpic2019, "bpic_2019", "purchase_order", "procurement", client=_client)
        if args.bpic2018:
            total += ingest_bpic_xes(args.bpic2018, "bpic_2018", "subsidy_application", "government", client=_client)
        if args.cuad:
            total += ingest_cuad(client=_client)
        if args.csv:
            print("[ingest] Custom CSV: call ingest_tabular() directly with your column_map config")

    try:
        count = _client.count(collection_name=COLLECTION).count
        print(f"\n[ingest] Done. Total documents in corpus: {count}")
    except Exception:
        print(f"\n[ingest] Done. Documents added this run: {total}")
