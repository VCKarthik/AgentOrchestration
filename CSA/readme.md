# Context Stitching Agent (CSA)

> **Stage 1 of Project AMP** — Retrieves and assembles all case context from a local SQLite database into a structured JSON packet, ready for downstream AI agents.

No LLM, no external APIs — purely local retrieval with validation.

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat&logo=sqlite&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic_v1-E92063?style=flat)
![Qdrant](https://img.shields.io/badge/Qdrant-hybrid_retrieval-DC244C?style=flat)

> Note: CSA uses Pydantic v1 syntax internally. This is intentional — the HTTP boundary isolates it from the orchestrator's Pydantic v2 models.

---

## Features

- **Zero-LLM context retrieval** — fetches emails, documents, calendar events, and case history by `case_id` + `case_type`
- **Structured validation** — reports `COMPLETE`, `PARTIAL`, or `EMPTY` context with a list of missing fields
- **Hybrid retrieval mode** — optional Qdrant vector search for free-text queries
- **CSA version tagging** — every packet carries `meta.csa_version: "2.0.0"` (Decision D2)
- **Idempotent seeding** — `infra/seed_csa_db.py` populates the three demo cases safely on every startup

---

## Architecture

```
POST /stitch
     │
     ├── retrieval_engine.py   ← SQL queries against csa.db
     │     (emails, documents, calendar_events, case_history)
     │
     ├── context_stitcher.py   ← assembles + validates the packet
     │     (stitch_structured / stitch_free_text)
     │
     └── CsaOutput (Pydantic v1)
           │
           → orchestrator receives via call_csa() in tools.py
```

CSA reads **only its own `data/csa.db`**. It does not query any other agent's database.

---

## Getting Started

### Prerequisites

- Python 3.11+
- `CSA/data/csa.db` populated (run `python -m infra.init_all` from project root)

### Installation

```bash
# From project root
pip install -r requirements.txt
python -m infra.init_all    # seeds csa.db with demo cases
```

### Running

```bash
# From project root
uvicorn CSA.api.main:app --port 8001

# Or via start_agents.sh (recommended — starts all 5 agents)
bash start_agents.sh
```

### Health check

```bash
curl http://localhost:8001/health
# {"status": "ok"}
```

---

## Usage

### Stitch a case (structured mode)

```bash
curl -s -X POST http://localhost:8001/stitch \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "CASE-VND-001",
    "case_type": "vendor_onboarding"
  }' | python -m json.tool
```

**Response shape:**

```json
{
  "task_id": "csa-run-<uuid>",
  "case_id": "CASE-VND-001",
  "case_type": "vendor_onboarding",
  "timestamp": "2026-04-29T12:00:00Z",
  "context": {
    "emails": [...],
    "documents": [...],
    "calendar_events": [...],
    "case_history": [...]
  },
  "validation": {
    "status": "COMPLETE",
    "missing_fields": [],
    "confidence_score": 1.0
  },
  "meta": {
    "csa_version": "2.0.0",
    "retrieval_mode": "structured"
  }
}
```

### Programmatic use (in-process)

```python
from CSA.core.context_stitcher import stitch_structured

packet = stitch_structured(
    case_id="CASE-CLM-002",
    case_type="claim_review",
    task_query="",
)
print(packet["validation"]["status"])   # COMPLETE | PARTIAL | EMPTY
print(packet["context"]["case_history"])
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `POST` | `/stitch` | Retrieve + assemble case context |
| `POST` | `/query` | Free-text hybrid retrieval (Qdrant-backed) |

---

## Database Schema

**File:** `CSA/data/csa.db`  
**Seeded by:** `infra/seed_csa_db.py`

| Table | Key Columns |
|-------|------------|
| `emails` | `case_id`, `case_type`, `subject`, `sender`, `date`, `body` |
| `documents` | `case_id`, `case_type`, `doc_type`, `file_path`, `status` |
| `calendar_events` | `case_id`, `case_type`, `title`, `start_time`, `attendees` |
| `case_history` | `case_id`, `case_type`, `event_type`, `actor`, `timestamp`, `status` |

### Demo cases (pre-seeded)

| Case ID | Type | Description |
|---------|------|-------------|
| `CASE-VND-001` | `vendor_onboarding` | Full context, $150k monetary value — triggers CFO approval rule |
| `CASE-CLM-002` | `claim_review` | Missing documents — triggers partial context validation |
| `CASE-FRD-003` | `fraud_investigation` | High-risk, $12k — triggers SAR + Compliance Officer escalation |

---

## Project Structure

```
CSA/
├── api/
│   ├── main.py          # FastAPI app, lifespan startup
│   └── routes/
│       ├── health.py    # GET /health
│       ├── stitch.py    # POST /stitch
│       └── query.py     # POST /query (hybrid retrieval)
├── core/
│   ├── context_stitcher.py   # stitch_structured() + stitch_free_text()
│   ├── retrieval_engine.py   # SQL fetch functions
│   ├── db_schema.py          # SQLite init + connection
│   └── qdrant_manager.py     # Qdrant indexing for hybrid mode
├── models/
│   └── schemas.py       # Pydantic v1 models (CsaOutput, etc.)
└── data/
    └── csa.db           # SQLite — emails, docs, calendar, history
```
