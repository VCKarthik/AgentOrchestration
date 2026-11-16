## Collaboration Rules
Use short, 3-6 word sentences. No filler, preamble or pleasantries.
Run tools first, show the result then stop. Do not narrate.
Drop articles ("Me fix code" not "I will fix code").
Do not make changes until 95% confident. Ask follow-up questions to reach that confidence.

---

## Project: Intent Anticipation Agent (IAA)

IAA is one of six agents in Project AMP (Automated Multi-agent Process).
Given a workflow case state, it predicts the next action with a confidence score.
It feeds recommendations to the Delegation Agent downstream.
FastAPI (`agent/api.py` on port 8003) is the active interface — consumed by the LangGraph orchestrator. ADK (`main.py`) remains for standalone testing but is not used in the demo flow.

## Tech Stack

| Component       | Technology                            |
|-----------------|---------------------------------------|
| LLM             | Gemini 2.0-Flash (default), GPT-4o-mini — set via `GEMINI_MODEL` env var |
| LLM Framework   | LangChain v0.3+                       |
| Embeddings      | sentence-transformers all-MiniLM-L6-v2 (local, 384-dim) |
| Vector Store    | Qdrant (local file or Docker network) |
| Agent Interface | FastAPI port 8003 (active); ADK `main.py` present but unused in demo |
| REST API        | FastAPI (`agent/api.py`)              |
| Data Validation | Pydantic v2                           |
| Process Mining  | pm4py (BPIC XES parsing)              |

## Folder Structure

```
IAA/
├── agent/
│   ├── main.py          # ADK entry point (root_agent)
│   ├── iaa.py           # run_iaa() + iaa_node() (LangGraph)
│   ├── chain.py         # Single-shot merged LLM chain + fast path + rule overrides
│   ├── retriever.py     # Qdrant RAG retrieval
│   ├── ingest.py        # Corpus ingestion (BPIC / CUAD / CSV)
│   ├── schemas.py       # Pydantic models
│   ├── api.py           # FastAPI REST service
│   └── qdrant_client_singleton.py  # Single Qdrant client per process
├── orchestrator/
│   └── orchestrator.py  # LangGraph reference — NOT active
├── docs/                # Deep-dive documentation (read before working)
├── data/                # Synthetic cases + prediction audit log
├── qdrant_store/        # Persisted vector DB (local mode)
├── test_iaa.py          # 75 unit tests
├── conftest.py          # LLM mock (zero API calls in tests)
├── iaa_demo.py          # CLI demo
└── requirements.txt
```

## Verifying Changes

```bash
cd IAA && python -m pytest test_iaa.py -v    # all 77 tests, no API key needed (run from IAA/ dir)
python iaa_demo.py --case SYNTH-CLA-0174     # single-case smoke test
# adk web                                   # ADK UI — not used in demo flow
```

Integration tests (real API key required): `pytest test_iaa.py -m integration`

## Documentation Index

Read relevant `docs/` files before starting work in that area.

- [docs/tech_stack.md](docs/tech_stack.md) — Component decisions, LLM provider switching, embedding choice, Qdrant singleton rationale
- [docs/testing.md](docs/testing.md) — How the LLM mock works, pytest commands, test structure, integration markers
- [docs/data_ingestion.md](docs/data_ingestion.md) — Corpus strategy, embedding model, ingest commands, document format
- [docs/deployment.md](docs/deployment.md) — ADK web, CLI modes, Docker Compose, API endpoints, known issues
