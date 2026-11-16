# Project AMP — CLAUDE.md

Project AMP is a 6-agent workflow automation system. The LangGraph orchestrator routes tasks through
CSA → [RRA, GPA, IAA as needed] → DA, with SWA running async in the background.

See @data/AmpState_spec.json for the canonical shared state schema.
See @orchestrator/shims.py for all field-mapping logic between agents.

---

## Running the agents

Each agent is a separate FastAPI server. Ports must be set explicitly — most agents
have no hardcoded port:

```bash
uvicorn CSA.api.main:app --port 8001       # Context Stitching Agent
uvicorn RRA.api:app --port 8002            # Risk Radar Agent (port 8002 is hardcoded)
uvicorn IAA.agent.api:app --port 8003      # Intent Anticipation Agent (defaults to 8000 — MUST specify 8003)
uvicorn GPA.app:app --port 8004            # Governance & Policy Agent
uvicorn DA.delegation_agent.api:app --port 8005  # Delegation Agent (port 8005 is hardcoded)
# SWA has NO FastAPI server — it is imported directly by the orchestrator
```

Health check all: `curl http://localhost:800{1..5}/health`

## Running the orchestrator

```bash
langgraph dev                          # LangGraph Studio UI at http://localhost:8123
streamlit run demo/app.py             # Streamlit client demo UI
python -c "from orchestrator.graph import get_graph; print(list(get_graph().nodes))"  # smoke test
```

To run a full programmatic workflow:
```python
from orchestrator.flow import run_amp_workflow
import asyncio
result = asyncio.run(run_amp_workflow({...}))  # pass TaskIntake fields as dict
```

## Running tests

```bash
pytest IAA/test_iaa.py -v                  # 75 IAA unit tests, no API key needed
pytest IAA/test_iaa.py -m integration      # real API key required
pytest RRA/tests/ -v                       # RRA rule engine tests
```

## LangSmith tracing

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your-key>
export LANGCHAIN_PROJECT=amp-orchestrator  # or amp-eval for eval runs
```

All `call_*` functions in `orchestrator/tools.py` are `@traceable`. ADK/LangChain calls
trace automatically when `LANGCHAIN_TRACING_V2=true`.

---

## Architecture rules — IMPORTANT

**SWA has no HTTP server.** `call_swa` imports `SWA.agent.orchestrator.analyze` directly.
Never attempt to start SWA as a uvicorn server or call it via httpx.

**Shims live only in `orchestrator/shims.py`.** All field mapping between agents goes here —
no mapping logic in tools.py, flow.py, or agent.py.

**Shims are pure functions.** No business logic, no state, no side effects. Input is
a raw dict or model instance; output is a dict of AmpState-compatible fields.

**flow.py owns execution order. tools.py owns HTTP calls. agent.py owns routing instruction.**
These responsibilities do not bleed across files.

**Never modify agent source code** (CSA/, RRA/, IAA/, GPA/, DA/, SWA/) to accommodate
orchestrator needs. Add a shim instead.

**AmpState is the single source of truth.** All inter-agent data flows through it.
Never pass raw agent outputs directly between tool functions.

---

## Pydantic rules (orchestrator only)

- Pydantic v2 throughout: `model_config = ConfigDict(...)`, never `class Config:`
- No `.dict()` — use `.model_dump()`
- All AmpState fields are `Optional` with `None` default

Note: CSA uses Pydantic v1 syntax and RRA uses stdlib dataclasses internally.
This is acceptable — the HTTP boundary isolates them. Do not "fix" agent Pydantic versions.

---

## Non-obvious gotchas

**IAA port:** IAA's `api.py` defaults to port 8000 (its dev port). Always start it with
`--port 8003`. If something calls `localhost:8000` expecting IAA, it will hit the ADK web UI instead.

**RRA response format:** RRA returns `output.to_dict()` — a plain dict, not a Pydantic model.
`risk_flags` does NOT exist in the RRA output — it must be derived via `extract_risk_flags()`
from `risk_items[].risk_type.value`. This is already handled in `shims.py::rra_to_amp()`.

**IAA response wrapping:** IAA's `/predict` returns `PredictResponse`, which wraps
`ActionRecommendation` under a `.recommendation` key. `shims.py::iaa_to_amp()` unwraps this.

**SWA sys.path:** `orchestrator/tools.py` adds the SWA folder to `sys.path` before importing.
If you move the SWA folder, update the path in `tools.py::_run_swa_background()`.

**GPA approvers field:** `GovernanceDecisionOutput.approvers` was added as part of Decision D4.
If the field is missing from a GPA response, it defaults to `[]` — this is intentional.

**Stage 2 partial failure:** If one of RRA/GPA/IAA fails in `asyncio.gather`, the others
continue. DA receives `None` for the failed agent's AmpState field. DA inspects inputs and
sets `requires_escalation=True` when insufficient — this is NOT an exception.

---

## Decision log (D1–D7)

Quick reference — full rationale in @output_CC.txt:

| Decision | Summary |
|---|---|
| D1 | `context_summary` removed from IAA `ProcessState` — CSA never generated it |
| D2 | CSA `meta.csa_version: "2.0.0"` added to both stitch functions |
| D3 | `risk_flags` is orchestrator-derived from RRA `risk_items[].risk_type.value` |
| D4 | `build_da_task()` shim merges task_intake + IAA TaskItem + GPA output for DA |
| D5 | `meta.operating_context` = "partial" if RRA or IAA reported partial context |
| D6 | SWA `swa_output` redesigned to match actual `AgentOutput` fields |
| D7 | `requires_escalation` = any of rra.escalate_to_human, gpa.requires_approval, iaa.escalate_to_human, da.escalation_required |

---

## Per-agent CLAUDE.md files

Each agent has its own CLAUDE.md with agent-specific rules:
- @IAA/CLAUDE.md — IAA collaboration rules, test commands, ADK interface

---

## Updates from the last session

### Session 2 — ADK → LangGraph migration
- `orchestrator/agent.py` — DELETED (ADK root_agent removed)
- `orchestrator/requirements.txt` — removed google-adk, added langgraph + langgraph-cli
- `requirements.txt` (root) — removed google-adk + google-generativeai, added langgraph + langgraph-cli
- `demo/app.py` — NEW: Streamlit client demo (`streamlit run demo/app.py`)
- CLAUDE.md run instructions updated to `langgraph dev` + `streamlit run demo/app.py`
- Smoke test passed: nodes: `['__start__', 'csa', 'stage2', 'da']`

### Session 3 — IAA latency, dashboard, bug fixes

**IAA — latency & correctness**
- `IAA/agent/chain.py` — Added `_fast_path()`: bypasses LLM for high/critical risk or missing-doc flags. Returns `model_used="fast_path/no_llm"` immediately (~0 ms vs ~20 s).
- `IAA/agent/chain.py` — `GEMINI_MODEL` env var controls model (default: `gemini-2.0-flash`). Previously hardcoded `gemini-2.5-flash`. Switch via `.env`.
- `orchestrator/flow_helpers.py` — Bug fix: `needs_iaa = True` always. Previous logic (`any(IAA_KEYWORDS) or not needs_rra`) accidentally excluded IAA whenever RRA fired (the common case). IAA must always run — it feeds DA.

**Demo dashboard**
- `demo/app.py` — Complete rewrite from 139-line static form to ~650-line enterprise dashboard. Three-column layout: priority queue (left), active case workspace (center), agent intelligence panel (right). Live agent progress bar (6 chips: CSA/RRA/GPA/IAA/DA/SWA), color-coded orchestration log, IAA suggested next actions, P1 auto-promotion on escalation. 3 pre-loaded demo cases. New Case dialog. Results tabs per agent after workflow completes.
- AMP header bar added at top (dark banner: "AMP | Agentic Microservices Prototyping").
- Right panel renamed "AGENT INTELLIGENCE".

**Config / environment**
- `.env.example` — `GEMINI_MODEL` added (default: `gemini-2.0-flash`).
- `.env.example` — `ADK_MODEL` removed (ADK interface unused in demo/production path).
- `.env.example` — Both `GOOGLE_API_KEY` and `GEMINI_API_KEY` annotated: same value, different var names used by different agents. Cannot consolidate without modifying agent source.

**IAA/CLAUDE.md** — ADK (`adk web`) is no longer the active demo interface. FastAPI on port 8003 is the active interface, consumed by the LangGraph orchestrator.

**Tests** — `cd IAA && python -m pytest test_iaa.py -v` → 77/77 passed. Must run from `IAA/` directory (not project root — IAA uses relative imports).

**Known LLM provider gotcha** — IAA uses `LLM_PROVIDER` env var. If set to `openai` with no valid key/quota, IAA returns HTTP 500. Set `LLM_PROVIDER=gemini` and ensure `GOOGLE_API_KEY` is set.

Full decision rationale for all sessions: see `docs/decisions.md` (D1–D13).

### Session 4 — GPA policy fix, SWA Postgres resilience, AITS docs

**GPA — policy tables + decision engine (Phase 5)**
- `GPA/seed_policies.py` — NEW: seeds `policy_documents`, `policy_chunks`, `policy_rules` from `data/policies/{procurement,claims,fraud}.md`. 3 docs, 9 rules, idempotent (skips existing). Rule extractor not used — its patterns (`"exceeding $X"`) don't fire on markdown table syntax; rules inserted directly.
- `GPA/decision_engine.py` — Rewritten: (1) falls back to `policy_type` lookup when `policy_document_ids` is empty, (2) ESCALATEs with confidence=0.30 when no policy docs found for case_type, (3) dynamic confidence formula replacing hardcoded 0.9/0.7, (4) direct escalation on `compliance_risk`/`missing_input`/`fraud_risk`/`regulatory_risk` flags.
- `orchestrator/shims.py` — `csa_to_gpa()` adds `task_type` to GPA metadata so fraud_investigation rule (`subject=task_type`) fires correctly.
- `infra/init_all.py` — Step 6 added: calls `seed_gpa_policies()` after state DB seed.

**SWA — Postgres optional (Phase 4)**
- `SWA/agent/orchestrator.py` — `db.fetch_events_in_window()` and portfolio build wrapped in `try/except`. Logs warning and continues with empty data on Postgres miss. Workflow never crashes.
- `start_agents.sh` — already correct (`python -m infra.init_all` at line 84). No changes needed; `data/init_db.py` / `seed_db.py` referenced in spec do not exist — `infra/` handles all init/seed.

**Docs**
- `docs/aits_integration.md` — NEW: AITS → AMP trigger flow, request schema, orchestrator pipeline, response format, demo simulation note.

### Session 5 — SWA SQLite write path + demo UI report cards

**SWA — SQLite write path (Phase 6)**
- `SWA/config/settings.py` — Removed all Postgres vars (`DB_HOST/PORT/NAME/USER/PASSWORD`). Added `SWA_DB_PATH` env var (default: `infra/swa.db`).
- `SWA/db/schemas.sql` — NEW: 7 tables — `cases`, `activity_log`, `case_portfolios`, `ingestion_log`, `analysis_runs`, `findings`, `escalations`. Composite PK on findings/escalations is `(run_id, finding_id)` / `(run_id, escalation_id)`.
- `SWA/db/db.py` — Full rewrite: `psycopg` → `sqlite3`, `%s` → `?` params, added `init_db()`, `upsert_finding()`, `upsert_escalation()`. All existing functions preserved with same signatures.
- `orchestrator/tools.py` — After `analyze()` succeeds in `_run_swa_background`: calls `upsert_finding` + `upsert_escalation` for each finding/escalation. Failure is suppressed (SWA never blocks primary workflow).
- `infra/init_all.py` — Step 7 added: `_init_swa_db()` calls `db.init_db()` to create SWA SQLite schema at startup. Non-fatal on failure.

**Demo UI — report cards (Phase 7)**
- `demo/app.py` — Result tabs rewritten; raw `st.json()` replaced with structured cards:
  - **DA tab**: assignment summary metrics (assigned_to, channel, confidence, escalation_required), reasons list, top-5 candidate rankings `st.dataframe`.
  - **RRA tab**: colored risk badge (green/amber/red/dark-red), can_proceed + escalate metrics, reasoning_summary caption, risk flags as colored pills.
  - **GPA tab**: decision badge (green=APPROVE / red=ESCALATE), confidence %, approvers, matched rule IDs.
  - **IAA tab**: recommended action + predicted actions kept; adds workflow timeline with status icons (✓/▶/○) and task list `st.dataframe`.
  - **SWA tab**: patterns/escalations/events metrics, window range caption, expandable findings list (empty-state handled).
- Added `_pill()` helper and `_RISK_COLORS` / `_DECISION_COLORS` constants for badge rendering.

### Session 6 — Repo hygiene, GPA policy fix, demo.txt, README refresh

**Gitignore + index cleanup**
- `.gitignore` — Added 15 new entries (anchored root patterns): `.claude/`, `/ref/`, `/docs/`, `/AUDIT.md`, `/BLOCKERS.md`, `/plan.md`, `/HANDOFF.md`, `/logs/`, `*.pids`, `*.db-shm`, `*.db-wal`, `data/synthetic_cases/`, `infra/qdrant_store/`, `CSA/data/outputs/`, `SWA/output/`. Patterns anchored with `/` so `IAA/docs/` and `SWA/docs/` remain tracked.
- `git rm --cached` — Untracked 87 previously-committed runtime files: all `__pycache__`, `*.db` files, CSA output JSONs, logs, ref/, docs/, SWA outputs, IAA Qdrant runtime files. Files remain on disk.
- **CLAUDE.md is NOT ignored** — it is essential project instructions and must stay tracked.

**GPA — policy rules fix**
- `GPA/config.py` — `DATABASE_URL` default changed from relative `sqlite:///./governance_agent.db` to absolute path anchored at `GPA/` folder (`Path(__file__).parent`). Eliminates stray root-level `governance_agent.db` created when GPA was started from the project root with the old relative path.
- `demo/app.py` — Added `monetary_value` to all 3 pre-loaded `DEMO_CASES`: `CASE-VND-001` ($150,000 → CFO approval rule), `CASE-CLM-002` ($7,500 → risk committee rule), `CASE-FRD-003` ($12,000 → SAR + Compliance Officer). Root cause of "No policy rules triggered — approved by default": demo cases had no `monetary_value`, so numeric threshold rules never matched.

**demo.txt — full rewrite**
- New structure: 3-terminal local quick start (T1: `bash start_agents.sh`, T2: `streamlit run demo/app.py`, T3: `langgraph dev`), Docker quick start (`make demo`), pre-demo checklist, per-terminal detail, updated scenarios with monetary values, Studio test payloads (JSON), feature showcase map, known gotchas.

**README updates**
- `README.md` — Updated for Sessions 2–5: 3-terminal local flow, ports table (added 8123 Studio), full env var table (added `LLM_PROVIDER`, `GEMINI_MODEL`, `SWA_DB_PATH`), data layer inventory table, project structure, key decisions table. Removed stale `data/init_db.py` reference and ADK references.
- `GPA/README.md` — NEW: API endpoints, policy domains table, confidence formula, DB location, key files.
- `orchestrator/README.md` — NEW: execution flow diagram, file responsibilities table, shim categories, AmpState field ownership, LangSmith setup, partial failure tolerance.
- `CSA/readme.md`, `RRA/README.md`, `IAA/README.md`, `SWA/README.md`, `DA/delegation_agent/README.md` — Light updates: port/stage headers added, ADK references removed from IAA, SWA updated to reflect SQLite write path (no Postgres), running sections added.
### Session 7 — SWA wholesale swap from ref/SWA + Observatory page

**SWA — replaced with ref/SWA (validated client-spec build)**
- `SWA/{agent,config,db,templates,app.py,test_agent.py,requirements.txt,README.md,SETUP.md}` — replaced wholesale from `ref/SWA/`. New `analyze()` reads events from the SWA SQLite DB and returns `tuple[AgentOutput, dict]` (the second item is run metadata). Old signature `analyze(events, cases) -> AgentOutput` is gone.
- `SWA/db/db.py` — SQLite via `settings.DB_PATH` (default `<repo_root>/swa_v3.db`). Single `schema.sql` file (no `schemas.sql`, no `findings`/`escalations` tables — those are stored as JSON inside `analysis_runs.output_json`).
- `SWA/config/settings.py` — `DB_PATH` env var, ML thresholds `ML_MIN_EVENTS=100`, `ML_MIN_CASES=10`. Postgres vars (`DB_HOST/PORT/NAME/USER/PASSWORD`) removed.

**Orchestrator wiring**
- `orchestrator/tools.py::_run_swa_background` — now ingests case + events into SWA DB via `agent.logging_tool.ingest_case` and `ingest_batch`, then calls `analyze(case_id=...)`. Unpacks the tuple. `swa_output_from_agent_output` shim unchanged — `AgentOutput` shape is identical.
- `infra/init_all.py` — Step 5/5 added: imports `SWA/db/db.py::init_db()` to create the SWA SQLite schema at startup. Non-fatal on failure.
- `.env.example` — `DB_HOST/PORT/NAME/USER/PASSWORD` removed; `DB_PATH` (commented default) added.

**Demo — SWA Observatory page**
- `demo/app.py` — Sidebar radio toggles between **Case Workspace** (existing 3-column dashboard) and **SWA Observatory**. Inserted just before the main `st.columns([...])` call so the existing UI is untouched.
- `demo/observatory.py` — NEW: dark-theme analytics page reading directly from SWA SQLite. Window date pickers + "⟳ Run analysis now" button (calls `agent.orchestrator.analyze(window_start, window_end, trigger_type="manual_observatory")`). Five tabs: Findings (confidence-filterable table + descriptions), Escalations (urgency-colored cards), Patterns/Clusters (latest `cluster_snapshots` summary), Activity Timeline (events-per-day + by-action stacked bar from `activity_log`), Per-agent Performance (success rate + events from `actor_type='agent'`).
- All Observatory queries are read-only against `analysis_runs.output_json`, `cluster_snapshots`, `activity_log`, `cases` — no LLM calls on tab open.

**Verification**
- `python -m infra.init_all` → all 5 steps green; SWA DB created at `SWA/swa_v3.db`.
- `cd SWA && python -m pytest test_agent.py -v` → 6/6 passed.
- `python -c "from orchestrator.graph import get_graph; print(list(get_graph().nodes))"` → `['__start__', 'csa', 'stage2', 'da']`.
- Smoke-called `analyze()` on empty DB → returns tuple, `AgentOutput` shape preserved.
