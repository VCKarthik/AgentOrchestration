# Project AMP — Decision Log

All architectural and design decisions made across sessions, with rationale.
Quick reference table is in `CLAUDE.md`. This file contains the full reasoning.

---

## D1 — Remove `context_summary` from IAA `ProcessState`

**Session:** 1  
**Files:** `IAA/agent/schemas.py`, `orchestrator/shims.py`

**Problem:** The original IAA design expected CSA to produce a `context_summary` string,
which would be passed into `ProcessState` to give the LLM extra grounding. CSA was
subsequently changed to not run an LLM (to cut latency), so it no longer generates a summary.
Passing `None` was silently dropping context the IAA prompt expected.

**Decision:** `context_summary` stays as `Optional[str] = None` in `ProcessState` (removing
it would break existing tests). The shim `csa_to_iaa()` never populates it. The IAA prompt
handles `None` gracefully — retriever context replaces it.

**Rationale:** Keeping the field costs nothing. Removing it would require updating schemas,
tests, and any external callers. The retriever already provides the grounding the summary
was meant to give.

---

## D2 — CSA `meta.csa_version: "2.0.0"`

**Session:** 1  
**Files:** `orchestrator/shims.py` (both `stitch_*` functions in CSA)

**Problem:** CSA had no version field in its output, making it impossible to distinguish
responses from CSA v1 (with LLM) vs v2 (without LLM) in audit logs.

**Decision:** Both stitch functions in CSA now inject `meta.csa_version = "2.0.0"` into
their output dict. The orchestrator shim reads this into `AmpState.csa_output.meta`.

**Rationale:** Zero-cost audit trail. Enables future compatibility checks without modifying
the CSA agent's own code (shim injects it at the boundary).

---

## D3 — `risk_flags` is orchestrator-derived, not from RRA directly

**Session:** 1  
**Files:** `orchestrator/shims.py::rra_to_amp()`, `orchestrator/shims.py::extract_risk_flags()`

**Problem:** `RiskRadarOutput` has no `risk_flags` field. It has `risk_items: list[RiskItem]`,
where each item has a `risk_type` enum. Callers expecting `risk_flags: list[str]` were getting
`AttributeError` or silently empty lists.

**Decision:** `rra_to_amp()` derives `risk_flags` as `[item["risk_type"] for item in risk_items]`.
A standalone helper `extract_risk_flags()` exists for callers that have the raw RRA object.
`risk_flags` never appears on `RiskRadarOutput` — it is an orchestrator-computed field.

**Rationale:** Cannot modify RRA agent source. Shim is the correct place for this transform.
Keeping `extract_risk_flags()` as a named function makes the derivation explicit and testable.

---

## D4 — `build_da_task()` shim merges three sources for DA input

**Session:** 1  
**Files:** `orchestrator/shims.py::build_da_task()`

**Problem:** DA's `Task` input requires fields from three sources: `task_intake` (title,
description, priority, due_date, requester), an IAA `TaskItem` (task_id, action,
assigned_role), and GPA output (for approval context). No single upstream field covers all
of DA's required inputs.

**Decision:** `build_da_task()` merges all three with explicit precedence rules:
- `task_id` ← IAA TaskItem
- `title` / `description` ← task_intake if present, else derived from IAA action
- `priority` ← IAA priority overrides task_intake if set
- Required fields (`task_type`, `estimated_effort`, `due_date`, `business_domain`,
  `requester`) ← task_intake with sensible defaults + error logging to `meta.stage_errors.da_merge`
- `recommended_candidates` ← `[iaa_task_item.assigned_role]` if set

**Rationale:** DA needs a complete Task object. Building it in a shim keeps DA's own code
clean and makes the merge logic testable in isolation.

---

## D5 — `operating_context` = "partial" if either RRA or IAA reported partial

**Session:** 1  
**Files:** `orchestrator/shims.py::compute_operating_context()`, `orchestrator/flow.py`

**Problem:** Both RRA and IAA independently report whether they had full or partial context.
The final `AmpState.meta.operating_context` needs a single authoritative value for DA and
downstream consumers.

**Decision:** `compute_operating_context(rra_output, iaa_output)` returns `"partial"` if
either agent reported partial, otherwise `"full"`. Called by the orchestrator after Stage 2
completes. Neither agent is authoritative alone.

**Rationale:** Conservative — if any agent was uncertain, the whole workflow context is
partial. DA uses this to decide escalation confidence.

---

## D6 — SWA `swa_output` redesigned to match actual `AgentOutput` fields

**Session:** 1  
**Files:** `orchestrator/schemas.py::SwaOutput`, `orchestrator/shims.py::swa_output_from_agent_output()`

**Problem:** The original `SwaOutput` schema in the orchestrator was designed to a spec that
didn't match what SWA's `AgentOutput` actually returns. Fields like `findings`, `escalations`,
`window_analyzed`, and `metrics` exist on `AgentOutput` but were absent from the orchestrator schema.

**Decision:** `SwaOutput` was rebuilt to mirror `AgentOutput` exactly:
- `findings: list[dict]` — serialized `Finding` objects
- `escalations: list[dict]` — serialized `Escalation` objects
- `escalation_surfaced: bool`
- `summary_sent: bool`
- `window_analyzed: dict` (start, end, events_processed)
- `metrics: dict` (patterns_detected, recommendations_made, etc.)

**Rationale:** The HTTP boundary was the problem — SWA is imported directly, not called via
HTTP. The shim `swa_output_from_agent_output()` maps the live `AgentOutput` object to the
orchestrator's `SwaOutput` model.

---

## D7 — `requires_escalation` = OR of four independent agent signals

**Session:** 1  
**Files:** `orchestrator/shims.py::compute_requires_escalation()`, `orchestrator/flow.py`

**Problem:** Four agents independently signal escalation need via different field names:
`rra.escalate_to_human`, `gpa.requires_approval`, `iaa.escalate_to_human`,
`da.escalation_required`. The final AmpState needed one authoritative escalation flag.

**Decision:** `compute_requires_escalation()` returns `True` if ANY of the four is truthy.
This is a logical OR — any single agent's escalation signal is sufficient.

**Rationale:** Conservative by design. If any agent flags escalation, a human must review.
DA specifically sets `escalation_required=True` when it cannot assign with sufficient
confidence — that alone should surface the case.

---

## D8 — IAA always runs in Stage 2 (`needs_iaa = True`)

**Session:** 3  
**Files:** `orchestrator/flow_helpers.py`

**Problem:** `resolve_stage2_agents()` used keyword matching to decide which Stage 2 agents
to run. The IAA condition was `any(IAA_KEYWORDS in text) or not needs_rra`. IAA keywords
were: "next", "predict", "timeline", "recommend", "workflow", "schedule". For common cases
like `vendor_onboarding` or `claim_review`, none of these keywords appear in the task
description, and `needs_rra=True`, so `needs_iaa = False or False = False`. IAA was skipped
for the majority of real cases.

**Decision:** `needs_iaa = True` — IAA always runs in Stage 2.

**Rationale:** IAA's output feeds DA's assignment decision (`build_da_task()` uses IAA's
`TaskItem`). Skipping IAA means DA receives `None` for IAA fields, which forces escalation
(D7 logic). IAA is not optional — it is a core stage 2 agent regardless of task type.

---

## D9 — IAA fast path: skip LLM for deterministic override cases

**Session:** 3  
**Files:** `IAA/agent/chain.py::_fast_path()`

**Problem:** IAA's LLM call (Gemini) took ~15–30 s per request. For cases where `HARD_RULES`
in `apply_overrides()` would override the LLM output anyway (high/critical risk, missing
required documents), the LLM call produced output that was immediately discarded.

**Decision:** `_fast_path(state, retrieved_ids)` runs before `get_llm()` in `run_chain()`.
It mirrors the two deterministic hard rules:
- `risk_severity in ("high", "critical")` → return `escalate_to_human` immediately
- `risk_flags` contains "missing"/"incomplete"/"required" → return `request_missing_document` immediately

Returns `model_used="fast_path/no_llm"`. `apply_overrides()` still called but is a no-op
(override_applied already True).

**Rationale:** Eliminates ~20 s of unnecessary LLM inference for ~40–60% of production
cases. Result is identical to what the LLM + override would have produced. No loss of
information.

---

## D10 — `GEMINI_MODEL` env var controls IAA model

**Session:** 3  
**Files:** `IAA/agent/chain.py`, `.env.example`

**Problem:** IAA's LLM model was hardcoded to `gemini-2.5-flash` in `get_llm()`. Switching
to a faster model required code changes.

**Decision:** `GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")`. Default changed
from `gemini-2.5-flash` to `gemini-2.0-flash`. Override via `.env`.

**Options documented in `.env.example`:**
- `gemini-2.0-flash` — faster (~5–10 s), good quality [default]
- `gemini-2.5-flash` — slower (~15–30 s), higher quality

**Rationale:** `gemini-2.0-flash` is significantly faster for this structured JSON task
with comparable output quality. The env var allows switching without code changes.

---

## D11 — `ADK_MODEL` removed; ADK interface deprecated in demo

**Session:** 3  
**Files:** `.env.example`, `IAA/CLAUDE.md`

**Problem:** `ADK_MODEL` was in `.env.example` and referenced in `IAA/agent/main.py` (the
ADK entry point). After Session 2 migrated the orchestrator to LangGraph, the active IAA
interface became FastAPI (`IAA.agent.api:app` on port 8003). `ADK_MODEL` is only read by
`main.py`, which is not invoked in the demo flow.

**Decision:** Remove `ADK_MODEL` from `.env.example`. Leave `IAA/agent/main.py` untouched
(agent source — do not modify). Note in `IAA/CLAUDE.md` that FastAPI is now the active
interface.

**Rationale:** Removing from `.env.example` reduces confusion about which env vars are
needed. The ADK entry point remains for optional standalone `adk web` testing.

---

## D12 — Two Gemini API key variable names coexist

**Session:** 3  
**Files:** `.env.example`

**Problem:** IAA and DA read `GOOGLE_API_KEY`. RRA and SWA read `GEMINI_API_KEY`. These are
the same key from Google AI Studio, but different variable names chosen by different agent
developers. Users with one key were confused about which var to set.

**Decision:** Both vars must be set to the same value. `.env.example` annotated clearly:
```
GOOGLE_API_KEY=your_key   # read by: IAA, DA, RRA (LangChain path)
GEMINI_API_KEY=your_key   # read by: RRA (genai client), SWA
```

Cannot consolidate to one var without modifying agent source (blocked by architecture rules).

**Rationale:** The HTTP boundary between agents means each agent reads its own env. Shims
can't intercept env var reads. Documentation is the only fix available without breaking
the "never modify agent source" rule.

---

## D13 — Dashboard live-update via `asyncio.run()` + `st.empty()` refs

**Session:** 3  
**Files:** `demo/app.py`

**Problem:** Streamlit rerenders on user interaction only. `run_amp_workflow()` is an async
function that takes 10–60 s. During that time the UI would be frozen with no feedback.

**Decision:** `asyncio.run(run_amp_workflow(..., on_progress=on_progress))` blocks the main
Streamlit thread. `on_progress` receives progress message strings and calls
`st.empty().markdown()` on pre-created container references.

Because `asyncio.run()` is synchronous from Streamlit's perspective, the callback fires
in the main thread — allowing direct container writes that render immediately in the browser
without `st.rerun()`. The right-column log container reference is stored in
`st.session_state["_log_container_ref"]` so the center-column RUN handler can access it.

After `asyncio.run()` returns, `st.rerun()` fires to display the full result tabs.

**Rationale:** Avoids WebSocket polling, threading, or `st.write_stream`. Works with any
Streamlit ≥ 1.32 (required for `@st.dialog`). The trade-off is the main thread is blocked —
acceptable for a demo where only one workflow runs at a time.

# Plan: Gitignore, GPA Fix, demo.txt, README Updates

## Context

Pre-demo cleanup pass on the AMP repo. Six independent work items:
1. Extend `.gitignore` for client-facing repo hygiene
2. Investigate and fix the stray `governance_agent.db` in the project root
3. Fix GPA returning "No policy rules triggered — approved by default" (demo cases lack `monetary_value`)
4. Rewrite `demo.txt` with local + Docker instructions for all 3 terminals
5. Update root `README.md`
6. Write missing `GPA/README.md` and `orchestrator/README.md`; update existing agent READMEs

---

## Item 1 — .gitignore additions

**File:** `.gitignore`

**FLAGS (do NOT ignore these):**
- `CLAUDE.md` — **essential**: project instructions embedded in system context, explicitly checked in as codebase instructions. Must stay tracked.
- `docs/` — **ignore entire folder** (user confirmed). All three files go in .gitignore.

**Add to .gitignore:**
```
# ── Claude Code session files ──────────────────────────────────────────────────
.claude/

# ── Internal working documents ────────────────────────────────────────────────
ref/
AUDIT.md
BLOCKERS.md
plan.md
HANDOFF.md
docs/

# ── Logs and runtime state ────────────────────────────────────────────────────
logs/
*.pids
*.db-shm
*.db-wal

# ── Generated data ────────────────────────────────────────────────────────────
data/synthetic_cases/
infra/qdrant_store/
uploads/
output/
```

**Already covered:** `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `*.db`, `.env`, `.venv/`, `.idea/`, `.vscode/`

**Note:** `*.db-shm` and `*.db-wal` are SQLite WAL-mode journal files generated at runtime — they appear in `git status` as untracked (`infra/state.db-shm`, `infra/state.db-wal`).

---

## Item 2 — governance_agent.db root copy

**Root cause:** `GPA/config.py` uses `sqlite:///./governance_agent.db` (relative path). When GPA is run from the project root via `uvicorn GPA.app:app`, SQLite creates `./governance_agent.db` in the project root. When someone runs GPA directly from inside `GPA/`, it creates `GPA/governance_agent.db`. Two copies diverge.

**Both files are already gitignored** (`*.db` rule) — not a git tracking issue.

**Fix:** Update `GPA/config.py` to use an absolute path anchored to the GPA folder:
```python
from pathlib import Path
_GPA_DIR = Path(__file__).parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_GPA_DIR}/governance_agent.db")
```
This ensures both GPA (when started from any CWD) and `seed_gpa_policies()` (which imports `GPA.db.SessionLocal`) always use `GPA/governance_agent.db`. Eliminates the duplicate.

Add `GPA/governance_agent.db` to `.gitignore` explicitly (belt-and-suspenders over `*.db`).

---

## Item 3 — GPA "No policy rules triggered" fix

**Root cause (confirmed by tracing `decision_engine.py`):**
- All `vendor_onboarding` and `claim_review` rules match on `monetary_value` (numeric threshold)
- The 3 demo cases in `demo/app.py` (lines 171–211) have **no `monetary_value` field**
- `csa_to_gpa` passes `metadata["monetary_value"] = None` → filtered out → no match → APPROVE by default
- The `fraud_investigation` rule on `task_type == "fraud_investigation"` SHOULD fire correctly once the DB is seeded

**Fixes:**

**A. Add `monetary_value` to demo cases** (`demo/app.py`, `DEMO_CASES` list):
- `CASE-VND-001` vendor_onboarding: `"monetary_value": 150000` (triggers CFO approval rule ≥ $100k)
- `CASE-CLM-002` claim_review: `"monetary_value": 7500` (triggers risk committee rule >$5k)
- `CASE-FRD-003` fraud_investigation: `"monetary_value": 12000` (triggers SAR filing rule ≥$5k)

**B. Fix DATABASE_URL** in `GPA/config.py` (see Item 2) so seeded rules are in the same DB GPA queries.

**C. Verify seeding path** — `infra/init_all.py` step 6 already calls `seed_gpa_policies()`. No change needed. But add a note in `start_agents.sh` header comment that `init_all` seeds GPA policies.

**Verification:** After `bash start_agents.sh`, run the fraud case in Streamlit → GPA tab should show ESCALATE with Compliance Officer approver, confidence ≥ 0.75.

---

## Item 4 — demo.txt rewrite

**File:** `demo.txt` (currently 22 KB of scenario narration; needs structure + local/Docker split)

**New structure:**
```
PROJECT AMP — DEMO GUIDE
========================

QUICK START (LOCAL)
  Terminal 1 — Agents:        bash start_agents.sh
  Terminal 2 — Dashboard:     streamlit run demo/app.py
  Terminal 3 — Orchestrator:  langgraph dev

QUICK START (DOCKER)
  make demo            # build + start all services
  # Dashboard: http://localhost:8501
  # LangGraph: http://localhost:8123

TERMINAL DETAILS
  T1 start_agents.sh: what it does (init_all, health checks, PIDs)
  T2 Streamlit: URL, 3 pre-loaded cases, New Case dialog
  T3 langgraph dev: Studio URL, how to submit a test payload, how to inspect node outputs

PRE-DEMO CHECKLIST
  (existing checklist from current demo.txt)

DEMO SCENARIOS (condensed)
  Scenario A — Vendor Onboarding (CASE-VND-001, monetary_value: $150k → CFO approval)
  Scenario B — Insurance Claim (CASE-CLM-002, monetary_value: $7.5k → risk committee)
  Scenario C — Fraud Investigation (CASE-FRD-003 → SAR + Compliance Officer)

AGENT HEALTH CHECKS
  (existing curl commands)

KNOWN ISSUES / GOTCHAS
  (IAA port, LLM provider, SWA in-process)
```

---

## Item 5 — Root README.md update

**File:** `README.md`

Update to reflect current state (Sessions 2–5):
- Architecture diagram section: add SWA (async, in-process)
- Quick start: show the 3-terminal local flow prominently; keep `make demo` for Docker
- Ports table: verify all correct (8001–8005, 8501, 8123)
- Environment variables: add `GEMINI_MODEL`, `LLM_PROVIDER`, `SWA_DB_PATH`
- Data layer: mention AmpState spec, shims.py, contracts.py
- Remove any ADK references (ADK was removed in Session 2)
- Add "Running tests" section (`pytest IAA/test_iaa.py -v`)

---

## Item 6 — Agent README updates

### CREATE: `GPA/README.md`
- Agent role: policy governance, SQLite-backed, seeded at startup
- API: `POST /predict`, `GET /documents`, `GET /rules/{id}`, `POST /dev/upload-policy`
- DB: `GPA/governance_agent.db` (SQLite, seeded by `infra/init_all.py`)
- Policy domains: procurement, claims, fraud
- Decision logic: rule match → APPROVE/ESCALATE, dynamic confidence, risk flag override
- Running: `uvicorn GPA.app:app --port 8004`

### CREATE: `orchestrator/README.md`
- Role: LangGraph orchestrator, routes CSA → Stage2(parallel) → DA
- Files: `flow.py` (execution), `tools.py` (HTTP calls), `shims.py` (field mapping), `contracts.py` (slim inputs), `schemas.py` (AmpState)
- Running: `langgraph dev` (Studio at localhost:8123) or `from orchestrator.flow import run_amp_workflow`
- Key decisions D1–D7 summary

### UPDATE existing READMEs (light touch — verify accuracy, add session changes):
- `CSA/readme.md` — verify ports, DB path
- `RRA/README.md` — confirm rules-only mode note
- `IAA/README.md` — confirm `--port 8003` requirement, remove ADK references
- `SWA/README.md` — update to reflect SQLite write path (no Postgres for demo)
- `DA/delegation_agent/README.md` — verify

---

## Critical files to modify

| File | Change |
|---|---|
| `.gitignore` | Add ~10 new entries |
| `GPA/config.py` | Fix DATABASE_URL to absolute path |
| `demo/app.py` | Add `monetary_value` to 3 DEMO_CASES entries |
| `demo.txt` | Full rewrite with local + Docker + 3-terminal instructions |
| `README.md` | Update to reflect Sessions 2–5 changes |
| `GPA/README.md` | CREATE |
| `orchestrator/README.md` | CREATE |
| `CSA/readme.md` | Light update |
| `RRA/README.md` | Light update |
| `IAA/README.md` | Light update |
| `SWA/README.md` | Light update |
| `DA/delegation_agent/README.md` | Light update |

---

## Verification

1. `git status` — confirm new .gitignore entries remove the untracked noise
2. `bash start_agents.sh` → all 5 agents healthy
3. `streamlit run demo/app.py` → run CASE-VND-001 → GPA tab shows ESCALATE (CFO approver, monetary threshold reason)
4. Run CASE-FRD-003 → GPA tab shows ESCALATE (Compliance Officer, SAR filing reason)
5. `langgraph dev` → submit test payload via Studio UI → inspect node outputs

---

## Open question for user

Should `docs/` stay tracked (it has `decisions.md` and `aits_integration.md` which are useful client-facing documentation), or should the whole folder be gitignored? The third file (`amp_data_layer_prompt.md`) is clearly internal and should be ignored regardless.
