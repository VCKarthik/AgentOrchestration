# Project AMP — Pre-Refactor Audit

Date: 2026-04-25
Scope: read-only audit before the 5-phase surgical refactor for the 2026-04-29 demo.
Findings drive Phases 1–5 (see `plan.md` and CLAUDE.md decisions D1–D13).

---

## 1. Gemini key inventory

Per **D12**, two env-var names coexist (same key value, different consumers). Confirmed:

| File:Line | Var | Consumer |
|---|---|---|
| `IAA/agent/chain.py:23` | `GOOGLE_API_KEY` | IAA chain (Gemini via LangChain) |
| `IAA/agent/chain.py:24` | `OPENAI_API_KEY` | IAA fallback provider |
| `IAA/agent/chain.py:48-53` | `GEMINI_MODEL` (default `gemini-2.0-flash`) | IAA `ChatGoogleGenerativeAI` |
| `DA/delegation_agent/services/llm_router.py:23` | `GOOGLE_API_KEY` | DA router |
| `DA/delegation_agent/services/llm_service.py:24` | `GOOGLE_API_KEY` | DA service |
| `RRA/summarizer.py:73` | `GEMINI_API_KEY` | RRA `genai.Client` |
| `RRA/summarizer.py:110` | `GROQ_API_KEY` | RRA secondary (Groq) |
| `SWA/config/settings.py:25` | `GEMINI_API_KEY` | SWA settings |
| `SWA/agent/llm_enricher.py:50-55` | `genai.configure(api_key=settings.GEMINI_API_KEY)` | SWA enricher |
| `GPA/config.py:4` | `load_dotenv()` only — no Gemini | (uses LangChain default key resolution) |

**`load_dotenv()` sites:** `orchestrator/__init__.py:1`, `IAA/agent/{chain,ingest,qdrant_client_singleton,retriever,iaa,main}.py`, `GPA/config.py`, `SWA/config/settings.py`.

**Decision (Phase 2a):** keep both var names; document in `.env.example`. Single root `.env` only — no per-agent overrides.

---

## 2. DB inventory

| Agent | DB | File:Line | Tables / Collections | Purpose |
|---|---|---|---|---|
| **CSA** | SQLite (file) | `CSA/core/db_schema.py:14,19` | `emails`, `documents`, `calendar_events`, `case_history`, `query_runs` | Case context store + run log |
| **RRA** | _none (stateless)_ | `RRA/schema.py:84-130` | — | In-memory `CaseInput` only |
| **IAA** | Qdrant (local) | `IAA/agent/qdrant_client_singleton.py:26-28`, `IAA/agent/retriever.py:19` | collection `iaa_corpus` | Process-history RAG retrieval |
| **GPA** | SQLite via SQLAlchemy | `GPA/config.py:6`, `GPA/db.py:9` | `policy_documents`, `policy_chunks`, `policy_rules`, `incoming_tasks`, `governance_decisions` (per `GPA/models.py`) | Policy + decision audit |
| **DA** | _none (stateless)_ | `DA/delegation_agent/models/task.py:91` | — | In-memory `Task` |
| **SWA** | PostgreSQL (psycopg3) | `SWA/config/settings.py:18-22`, `SWA/db/db.py:8-9,24` | `cases`, `activity_log`, `case_portfolios`, `ingestion_log`, `analysis_runs` | Event log + analysis runs |
| **Orchestrator** | _in-memory_ (LangGraph) | — | — | AmpState only |

**Drift:** three different stores (SQLite × 2, Qdrant, Postgres). Phase 3 collapses to **Qdrant + SQLite only**. SWA Postgres tables migrate into the unified `infra/state.db` plus `historical_cases` Qdrant collection where appropriate.

---

## 3. Input bloat per agent

Each FastAPI handler accepts a model and (mostly) consumes every field. The bloat is **not** unused fields — it is **oversized field contents** flowing in via the orchestrator (full AmpState slices, full email bodies, full case_history). Phase 1 fixes this with slim `orchestrator/contracts.py` models.

| Agent | Endpoint | Declared fields | Actually used | Notes |
|---|---|---|---|---|
| CSA | `/query` (`CSA/api/routes/query.py:24-30,45-48`) | `case_id`, `case_type`, `task_text`, `top_k` | all 4 | Already slim — no Phase 1 change to contract |
| RRA | `/predict` (`RRA/api.py:27-50,74-79`) | 17 fields (workflow_*, *_inputs, *_count, *_flag) | all forwarded to `CaseInput` | Already slim |
| IAA | `/predict` (`IAA/agent/api.py:58-72,157-182`) | `process_state`, `events`, `context_summary`, `risk_flags`, `risk_severity`, `policy_constraints`, `assigned_owner`, `domain_filter`, `process_type_filter` | all conditionally | **HEAVY**: orchestrator currently sends bloated `process_state.prior_actions` and unbounded retrieved-context via prompt — see §6 |
| GPA | `/predict` (`GPA/schemas.py:18-46`, `GPA/app.py:86-106`) | 18 TaskInput fields incl. `risk_assessment`, `metadata` | all via `model_dump()` | `extra="allow"` → silent over-acceptance |
| DA | endpoint (`DA/delegation_agent/api.py:32-36`, `models/task.py:91-167`) | 15 Task fields | all available | Already slim |
| SWA | _no HTTP_ | — | — | Imported in-process per D11 |

**Phase 1 priority:** IAA (the latency victim). Slim its incoming `process_state` to the bare minimum needed by the prompt (last-5 prior_actions, no full case_history, no email bodies).

---

## 4. `dict[str, Any]` inventory (29 sites)

**TYPEABLE (15)** — replace with a typed Pydantic sub-model:

| File:Line | Site |
|---|---|
| `IAA/agent/iaa.py:180` | `update: dict[str, Any] = {}` (ProcessState delta) |
| `RRA/schema.py:165` | `to_dict()` return |
| `SWA/agent/detectors.py:14,53,99,162` | finding return shape |
| `SWA/agent/escalator.py:6` | finding→escalation transform |
| `SWA/agent/ml_detector.py:64` | finding return |
| `SWA/agent/scorer.py:27,79,103` | scoring inputs/outputs |

**DYNAMIC (14)** — use `model_config = ConfigDict(extra="allow")` or keep as bag:

| File:Line | Site |
|---|---|
| `DA/delegation_agent/models/outputs.py:100,103` | `selected_owner`, `selected_assignee` |
| `GPA/decision_engine.py:19` | `task_payload` |
| `orchestrator/state.py:52` | `stage_errors` |
| `orchestrator/schemas.py:448` | `stage_errors` |
| `IAA/agent/iaa.py:134` | LangGraph `graph_state` |
| `RRA/schema.py:121` | `from_dict` input |
| `SWA/agent/logging_tool.py:43,84,105,140` | event/case payloads |
| `SWA/agent/models.py:24,35` | `context_payload`, `domain_metadata` |
| `SWA/db/db.py:37,56,115,148,165` | DB row dicts |

Phase 2b will type the SWA detector/scorer family (TYPEABLE majority) and leave SWA logging-tool/db as DYNAMIC bags (they're truly arbitrary ingestion shapes).

---

## 5. Data folder inventory

**Keep, move to unified `data/`:**
- `data/AmpState_spec.json` (9.5 KB) — schema spec (already canonical)
- `data/generate_synthetic_cases.py` (31 KB) — test data generator
- `IAA/data/synthetic_cases.json` (250 KB) → move to `data/synthetic_cases/iaa_corpus.json`
- `SWA/data/synthetic_events.json` + `synthetic_events.py` → move to `data/synthetic_cases/swa/`

**Regeneratable / deletable (after Phase 3 init script verified):**
- `CSA/data/csa.db` (60 KB) — regenerated by `data/init_db.py`
- `CSA/data/outputs/` (496 KB, 51 files) — runtime artifacts; move to `data/outputs/` (gitignored)
- `IAA/data/predictions.jsonl` (31 KB) — runtime audit log; move to `logs/iaa_predictions.jsonl`
- `data/synthetic_amp_states.json` (578 KB) — large; keep but move to `data/fixtures/`
- `data/predictions.jsonl` (2.9 KB) — runtime; move to `logs/`
- `data/fixtures/` — keep

**Net effect:** 4 dirs → 1 (`data/`) + `logs/` + `infra/`.

---

## 6. IAA latency contributors

**LLM calls per `/predict`:** 1 (single merged-prompt `.invoke()` at `IAA/agent/chain.py:229`), or 0 on the fast-path (`chain.py:200-207`, ~40–60% of calls).

**Prompt template:**
- `MERGED_SYSTEM` (`chain.py:58-62`) ≈ 460 chars
- `MERGED_USER` (`chain.py:64-106`) ≈ 1,877 chars
- Static template total ≈ **2,340 chars**

**Variable interpolations (`chain.py:217-225`):**
1. `current_stage` — short
2. `current_event_type` — short
3. `prior_actions` — last 5, joined → 50–200 chars
4. `actor`, `risk_severity` — short
5. `risk_flags`, `policy_constraints` — joined lists, 100–300 chars
6. `assigned_owner` — short
7. **`retrieved_context`** — formatted 4 docs from Qdrant top-k, **2–4 KB** ← largest contributor

**Qdrant retrieval:** runs on **every** `/predict` (`IAA/agent/iaa.py:121`). No caching. ~100–200 ms.

**Latency hypothesis:**
- Static template (~2.3 KB) + retrieved_context (~3 KB) → ~5–6 KB prompt → Gemini 2.0-flash p95 ~3–5 s.
- **52 s observed** suggests one of: (a) the previous default `gemini-2.5-flash` was slower, (b) prior_actions was unbounded (full case_history merged in), (c) retrieved_context wasn't truncated, or (d) cold-start retrieval embedding.
- D10 already switched default to `gemini-2.0-flash`. Phase 1 adds prompt-size cap by slimming `IAAInput` and trimming `retrieved_context` to top-2 with body truncation.

**Expected post-Phase 1:** prompt ≤ 1.5 KB, latency < 5 s.

---

## 7. Dead code

- `RRA/config.py:45` — `# TODO: confirm with lead — may be Governance Agent's call` (compliance_flag routing). **Keep** — real open question, not dead code.
- No large commented-out blocks detected.
- No obvious unused imports beyond linter-level noise.

The codebase is genuinely lean for its size; Phase 2e cleanup will be small.

---

## Cross-cutting issues to fix

| Issue | Phase |
|---|---|
| IAA prompt size + retrieved_context unbounded | 1 |
| 29× `dict[str, Any]` (15 typeable) | 2b |
| Postgres in SWA (kill it) | 3d |
| 4 `data/` dirs | 3a, 5 |
| No root `docker-compose.yml` / `Makefile` | 4 |
| No `HANDOFF.md` | 5 |

End of audit. Proceeding to Phase 1.
