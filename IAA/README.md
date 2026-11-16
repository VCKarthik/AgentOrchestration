# Intent Anticipation Agent (IAA)

> **Stage 2 of Project AMP** — Given a workflow case state, predicts the most likely next action using a Gemini LLM chain augmented with Qdrant RAG over historical process data. Feeds a ranked action recommendation to the Delegation Agent downstream.

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-0.3+-1C3C3C?style=flat)
![Gemini](https://img.shields.io/badge/Gemini_2.0_Flash-4285F4?style=flat&logo=google&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-DC244C?style=flat)
![sentence-transformers](https://img.shields.io/badge/all--MiniLM--L6--v2-384dim-orange?style=flat)
![Pydantic](https://img.shields.io/badge/Pydantic_v2-E92063?style=flat)
![pm4py](https://img.shields.io/badge/pm4py-process_mining-blue?style=flat)

---

## Features

- **Fast-path escalation** — skips the LLM entirely for `high` / `critical` risk or missing-doc flags (~0 ms vs ~3-5 s)
- **Gemini + RAG chain** — single-shot LLM call with top-k historical cases retrieved from Qdrant for context
- **Rule-based overrides** — post-LLM overrides enforce business rules (e.g., force `escalate_to_human` when policy constraint present)
- **Configurable model** — `GEMINI_MODEL` env var switches the Gemini model without code changes (default: `gemini-2.0-flash`)
- **Corpus ingestion** — supports BPIC XES process logs, CUAD contracts, and generic CSV / JSON event logs
- **77 unit tests** — full mock of the LLM; zero API calls in the test suite
- **Workflow timeline + task list** — structured output consumed by the Streamlit dashboard for the agent intelligence panel

---

## Architecture

```
POST /predict (PredictRequest)
     │
     ├── chain.py::_fast_path()      ← skips LLM for high/critical risk
     │         or
     ├── retriever.py                ← Qdrant semantic search (top-k cases)
     │
     ├── chain.py::run_chain()       ← LangChain + Gemini LLM call
     │
     ├── chain.py::_apply_overrides()← post-LLM rule enforcement
     │
     └── PredictResponse
           │  { recommendation: ActionRecommendation, latency_ms, corpus_size }
           → orchestrator unwraps via shims.iaa_to_amp()
```

**Qdrant collection:** `iaa_corpus` — 384-dim COSINE, all-MiniLM-L6-v2 embeddings  
**Client:** singleton per process (`qdrant_client_singleton.py`) — prevents multiple file locks in local mode

---

## Getting Started

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | |
| `GOOGLE_API_KEY` | Required for Gemini LLM calls |
| Qdrant store | Auto-created at `IAA/qdrant_store/` on first run |

### Installation

```bash
# From project root
pip install -r requirements.txt
cp .env.example .env
# Set: GOOGLE_API_KEY, LLM_PROVIDER=gemini, GEMINI_MODEL=gemini-2.0-flash
```

### Running

```bash
# From project root (PYTHONPATH=IAA is set automatically by start_agents.sh)
PYTHONPATH=IAA uvicorn IAA.agent.api:app --port 8003

# Or via start_agents.sh (recommended)
bash start_agents.sh
```

> **Note:** IAA loads the BERT model (all-MiniLM-L6-v2) on startup. Allow up to 90 seconds on first boot.

### Health check

```bash
curl http://localhost:8003/health
# {"status": "ok"}
```

---

## Usage

### Predict next action

```bash
curl -s -X POST http://localhost:8003/predict \
  -H "Content-Type: application/json" \
  -d '{
    "process_state": {
      "entity_id": "CASE-VND-001",
      "current_stage": "COMPLETE",
      "current_event_type": "document_review",
      "prior_actions": ["intake", "document_review"],
      "actor": "orchestrator",
      "timestamp": "2026-04-29T12:00:00",
      "risk_flags": ["missing_input"],
      "risk_severity": "medium",
      "operating_context": "full"
    }
  }' | python -m json.tool
```

**Response shape:**

```json
{
  "recommendation": {
    "recommended_action": "request_additional_documents",
    "predicted_actions": [...],
    "escalate_to_human": false,
    "model_used": "gemini-2.0-flash",
    "task_list": [...],
    "workflow_timeline": [...]
  },
  "latency_ms": 3241.5,
  "corpus_size": 142
}
```

### Fast-path response (no LLM)

When `risk_severity` is `high` or `critical`:

```json
{
  "recommendation": {
    "recommended_action": "escalate_to_human",
    "model_used": "fast_path/no_llm",
    "escalate_to_human": true
  },
  "latency_ms": 0.4
}
```

### Corpus ingestion

```bash
# Ingest BPIC XES process logs
cd IAA
python -c "from agent.ingest import ingest_bpic_xes; ingest_bpic_xes('data/my_log.xes')"

# Ingest generic JSON cases
python -c "from agent.ingest import ingest_csv_events; ingest_csv_events('data/cases.json')"
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_API_KEY` | — | Gemini API key |
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model ID |
| `QDRANT_PATH` | `./IAA/qdrant_store` | Local Qdrant data directory |
| `QDRANT_HOST` | `` | Leave blank for local mode; set for Docker |
| `QDRANT_PORT` | `6333` | Qdrant port (Docker mode only) |

---

## Running Tests

```bash
# Must run from IAA/ directory (IAA uses relative imports)
cd IAA && python -m pytest test_iaa.py -v          # 77 unit tests, no API key
cd IAA && python -m pytest test_iaa.py -m integration  # real Gemini key required
```

### CLI smoke test

```bash
python IAA/iaa_demo.py --case SYNTH-CLA-0174
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `POST` | `/predict` | Predict next action from `ProcessState` or `events` |

---

## Project Structure

```
IAA/
├── agent/
│   ├── api.py                      # FastAPI REST service (port 8003)
│   ├── chain.py                    # LLM chain + fast path + rule overrides
│   ├── retriever.py                # Qdrant RAG retrieval
│   ├── ingest.py                   # Corpus ingestion (BPIC / CUAD / CSV)
│   ├── schemas.py                  # Pydantic v2 models
│   ├── iaa.py                      # run_iaa() + iaa_node() (LangGraph)
│   ├── main.py                     # ADK entry point (standalone testing only)
│   └── qdrant_client_singleton.py  # One Qdrant client per process
├── data/
│   ├── synthetic_cases/            # JSON corpus for Qdrant ingestion
│   └── prediction_audit.jsonl      # Audit log of predictions
├── qdrant_store/                   # Local Qdrant file store
├── docs/                           # tech_stack, testing, data_ingestion, deployment
├── test_iaa.py                     # 77 unit tests
├── conftest.py                     # LLM mock — zero API calls in tests
└── iaa_demo.py                     # CLI demo runner
```
