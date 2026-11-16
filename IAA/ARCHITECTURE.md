# IAA Architecture

## Data Flow

```
User / ADK chat
      │
      ▼
agent/main.py          — ADK root_agent, two FunctionTools
      │
      ├── predict_next_action()
      │         │
      │         ├── build_process_state()   [agent/iaa.py]
      │         │       └── EventLogEntry list → ProcessState
      │         │
      │         └── run_iaa(state)          [agent/iaa.py]
      │                   │
      │                   ├── IAARetriever.retrieve()   [agent/retriever.py]
      │                   │       └── embed query → Qdrant search → top-4 docs
      │                   │
      │                   ├── run_chain(state, context)  [agent/chain.py]
      │                   │       ├── Step 1: Contextualize  (LLM call)
      │                   │       ├── Step 2: Anticipate     (LLM call → JSON)
      │                   │       └── Step 3: Recommend      (LLM call → JSON)
      │                   │
      │                   └── apply_overrides(rec, state) [agent/chain.py]
      │                           └── high risk / missing doc / low confidence
      │
      └── get_similar_cases()
                │
                └── IAARetriever.retrieve() + format_for_prompt()
```

---

## agent/ Files

| File | Role |
|---|---|
| `main.py` | ADK entry point — defines `root_agent`, two `FunctionTool` wrappers |
| `iaa.py` | `run_iaa()` (direct call) and `iaa_node()` (LangGraph node wrapper) |
| `chain.py` | Three-step LLM chain (Contextualize → Anticipate → Recommend) + rule overrides |
| `retriever.py` | Embeds process state query, searches Qdrant, formats results for prompt |
| `ingest.py` | Ingests BPIC XES, CUAD, synthetic JSON/CSV into Qdrant collection |
| `schemas.py` | Pydantic models: `ProcessState`, `ActionRecommendation`, `EventLogEntry`, `IAAState` |
| `api.py` | FastAPI REST service wrapping `run_iaa()` (alternative to ADK interface) |
| `qdrant_client_singleton.py` | Process-wide Qdrant client + local embedding model (prevents file-lock conflicts) |
| `case_store.py` | Simple JSON persistence for demo case data |

---

## orchestrator/ Folder

Contains the LangGraph multi-agent orchestrator from Sprint 4.
**Not called at runtime.** Preserved for reference and future ADK migration.

```
orchestrator/
├── orchestrator.py        — LangGraph graph: CSA → RRA → IAA → DA
└── mock_agents/
    ├── csa_mock.py        — Context Stitching Agent (mock)
    ├── rra_mock.py        — Risk Radar Agent (mock)
    └── da_mock.py         — Delegation Agent (mock)
```

The `iaa_node()` function in `agent/iaa.py` is the LangGraph-compatible interface.
It reads `process_state` / `csa_output` / `rra_output` from shared graph state
and writes `iaa_recommendation` / `iaa_routing_action` / `iaa_escalate`.

---

## Three Run Modes

### 1. ADK Web UI (primary)
```bash
adk web
```
Chat interface at `http://localhost:8000`. The agent calls `predict_next_action`
or `get_similar_cases` based on the user's message. Entry: `agent/main.py`.

### 2. CLI Demo
```bash
python iaa_demo.py --case SYNTH-CLA-0174
python iaa_demo.py --risk high
python iaa_demo.py --workflow
```
Prints structured `ActionRecommendation` to stdout. Useful for quick smoke tests
and demos without a browser. Reads cases from `data/synthetic_cases.json`.

### 3. Test Suite
```bash
python -m pytest test_iaa.py -v
```
77 unit tests, zero API calls (LLM mocked in `conftest.py`).
Tests the full pipeline end-to-end with deterministic mock responses.
