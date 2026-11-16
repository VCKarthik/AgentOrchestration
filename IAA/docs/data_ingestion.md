# Data Ingestion — IAA

## Corpus Strategy

All documents go into a single Qdrant collection: `iaa_corpus`.
Domain identity is encoded as payload metadata, not separate collections.
Retrieval scopes to a domain via payload filter at query time.

Current corpus composition (approximate):
- ~200 synthetic process cases (generated, covers claims/approvals/audits)
- ~100 BPIC real event log traces (loan, permit, purchase order workflows)
- Optional CUAD contract clauses (legal domain, loaded on demand)

Target: 300–500 documents is sufficient for useful RAG at this task scale.

## Embedding Model

Model: `sentence-transformers/all-MiniLM-L6-v2`
Dimension: 384, Distance metric: cosine
Loader: `agent/qdrant_client_singleton.py:52` (`get_embedding_model()`)

Local model download on first use (~80 MB, cached by sentence-transformers).
No API key required. Runs on CPU — fast enough for 500 documents.

## Document Format

Each document stored in Qdrant has:
- `document` — natural-language description of the process state
- `source` — origin tag (`synthetic`, `bpic_2012`, `bpic_2018`, `cuad`)
- `domain` — domain category (`financial`, `legal`, `procurement`)
- `process_type` — specific process name (`loan_application`, `claim_processing`)
- `next_action` — ground-truth next action observed in the historical log
- `entity_id` — original case ID for traceability

Document text is constructed from event sequence + stage + metadata.
Format defined in `agent/ingest.py` around line 80–140.

## Ingest Commands

```bash
# Bootstrap: generate synthetic cases + embed into Qdrant
python scripts/generate_synthetic.py
python -m agent.ingest --bootstrap

# Add BPIC XES files (place .xes files in data/bpic/ first)
python -m agent.ingest --bpic

# Check corpus status
python -m agent.ingest --status

# Add a custom CSV event log
python -m agent.ingest --csv data/my_log.csv --domain financial --process-type claim
```

## BPIC XES Support

BPIC files parsed via pm4py. Supported datasets:
- BPIC 2012 (loan applications, ~13k cases) — `agent/ingest.py` BPIC_COLUMN_MAP
- BPIC 2018 (permit requests)
- BPIC 2019 (purchase orders)

XES files are parsed, sampled to `MAX_CASES=500`, embedded, then discarded.
Raw XES files are not stored in the repo (too large).

## Duplicate Prevention

Document IDs are deterministic UUIDs derived from content hash.
Re-running ingest on the same data is safe — duplicates are skipped.
ID generation at `agent/ingest.py:78` (`_make_id()`).

## Docker Notes

Inside Docker, Qdrant runs as a separate service.
Volume `./qdrant_store:/qdrant/storage` persists the corpus across container restarts.
Bootstrap commands must be run once inside the container:

```bash
docker compose exec iaa_app python scripts/generate_synthetic.py
docker compose exec iaa_app python -m agent.ingest --bootstrap
```
