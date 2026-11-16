# Claude Code Prompt — Project AMP Data Layer, Schema & Startup Consolidation

Paste into Claude Code from the root of the AMP repo. Execute phases in order. Commit after each phase.

---

## CONTEXT

Project AMP is a 6-agent MAS. Demo is April 29, 2026. The orchestrator (Scenario 1) receives task payloads, calls CSA first, then runs Stage 2 agents in parallel, then DA. CSA queries `CSA/data/csa.db` (SQLite) for per-case records. IAA queries Qdrant `historical_cases` for past workflow patterns.

This prompt addresses:
1. Reading 4 reference files and aligning agent I/O to them
2. Adding `required_skills` + `monetary_value` from ampstate_spec.json everywhere
3. Consolidating DB init + seed into startup
4. Documenting the AITS integration point
5. Fixing GPA hardcoded confidence + empty policy tables using ref/GPA_ref/
6. Fixing SWA SQLite write path so findings are persisted and queryable
7. Replacing raw JSON in demo tabs with human-readable report cards (no extra API calls)

## HOW TO USE YOUR JUDGMENT

Before executing any instruction in this prompt:
1. Read the actual file first. If reality differs from what the prompt assumes, follow reality — not the prompt. Flag the difference.
2. If an instruction would break working code, STOP and explain why before proceeding.
3. If you find a better implementation than described, use it and note why.
4. If a file path or field name doesn't exist, find the closest match and confirm before proceeding.
5. Treat all instructions as intent specifications, not line-by-line orders.

**After Phase 0 gap report, explicitly list any instruction that conflicts with actual code. Do not proceed on conflicts without confirmation.**

---

## PHASE 0 — READ EVERYTHING FIRST

Before touching any code, read these files in full. Do not skim.

```
ref/csa_db           # synthetic DB structure reference
ref/rra_guide.md     # RRA requirements + logic spec
ref/swa_guide        # SWA requirements spec
ref/swa_io           # SWA input/output field spec
ref/GPA_ref/         # teammate's GPA implementation — read all files
ampstate_spec.json   # canonical AmpState field spec including new fields
demo/app.py          # Streamlit dashboard (D13: asyncio.run + st.empty pattern)
orchestrator/flow.py
orchestrator/shims.py
orchestrator/schemas.py
CSA/core/context_stitcher.py
CSA/core/db_schema.py
CSA/data/ (list files only, read schema files)
RRA/schema.py
RRA/agent.py
GPA/schemas.py
GPA/decision_engine.py
GPA/governance_agent.db  # open and inspect: check policy_chunks, rules, cases tables
SWA/agent/models.py
SWA/agent/orchestrator.py
SWA/config/settings.py
SWA/db/db.py             # check what tables this creates and whether data is written
SWA/db/schemas.sql       # check table definitions
IAA/agent/schemas.py
data/init_db.py          # already exists — read before touching
seed_db.py               # already exists at root — read before touching
infra/ (list files, read any existing init/seed scripts)
start_agents.sh
```

Produce a **Gap Report** at `ref/GAP_REPORT.md` covering:

1. **CSA gap** — does `csa.db` schema match `ref/csa_db`? List missing tables/columns.
2. **RRA gap** — does RRA's input/output + logic match `ref/rra_guide.md`? List missing fields or logic gaps. Flag only meaningful differences — ignore cosmetic ones.
3. **SWA gap** — does SWA's input/output match `ref/swa_guide` + `ref/swa_io`? List missing fields or behavior gaps.
4. **AmpState gap** — which agents' input/output models are missing `required_skills` and `monetary_value` from `ampstate_spec.json`?
5. **Seed gap** — what seed data exists, what's missing, and where is `seed_db` currently located?
6. **Startup gap** — does `start_agents.sh` currently run DB init + seed before starting agents? If not, what's missing?

Commit: `chore: gap report before data layer consolidation`

---

## PHASE 1 — AMPSTATE SCHEMA UPDATES

Read `ampstate_spec.json`. The spec now includes two new fields:
- `required_skills: list[str]` — skills needed to execute the task
- `monetary_value: float | null` — estimated monetary value of the case

### 1a. Add to task_intake

In `orchestrator/schemas.py`, add to `TaskIntake` (or equivalent):
```python
required_skills: list[str] = Field(default_factory=list)
monetary_value: Optional[float] = None
```

### 1b. Propagate to slim input contracts

In `orchestrator/contracts.py`, add to `CaseMetadata`:
```python
required_skills: list[str] = Field(default_factory=list)
monetary_value: Optional[float] = None
```

These flow automatically to `CSAInput`, `RRAInput`, `IAAInput`, `GPAInput`, `DAInput` via `CaseMetadata`.

### 1c. Update synthetic cases

In `data/synthetic_cases/` — for ALL existing case JSON files, add:
```json
"required_skills": ["<role-appropriate skills based on case_type>"],
"monetary_value": <float appropriate to case complexity>
```

Use these guidelines:
- `vendor_onboarding`: skills = ["vendor_assessment", "compliance_review", "procurement"], value = 5000–50000
- `claim_review`: skills = ["claims_assessment", "policy_interpretation", "documentation_review"], value = 1000–100000
- `fraud_investigation`: skills = ["forensic_analysis", "risk_assessment", "compliance_review"], value = 10000–500000

### 1d. Update GPA policy lookup

`monetary_value` is relevant to GPA's approval threshold logic. In GPA's input handling, if `monetary_value` is present and exceeds the policy threshold (read from policy_knowledge), set `requires_approval = True`. If `monetary_value` is None, existing logic applies unchanged.

Commit: `feat: add required_skills and monetary_value to AmpState and synthetic cases`

---

## PHASE 2 — REF FILE ALIGNMENT

### 2a. CSA — align to ref/csa_db

Read `ref/csa_db` for the canonical schema. Apply all gaps identified in the Gap Report:

- Add any missing tables/columns to `CSA/core/db_schema.py`
- Ensure `CREATE TABLE IF NOT EXISTS` for all tables
- Do NOT remove existing columns — only add missing ones
- If `ref/csa_db` defines sample/seed data structure, use it in Phase 3 seed script

### 2b. RRA — align to ref/rra_guide.md

For each gap identified in the Gap Report:

- If a **required input field** is missing from `RRAInput` in `orchestrator/contracts.py`: add it
- If a **required output field** is missing from `RiskRadarOutput` in `RRA/schema.py`: add it with a sensible default so existing tests don't break
- If a **logic requirement** in the guide is not implemented and is materially different from current behavior: implement it. Add a `# NOTE: added per rra_guide.md` comment.
- If current implementation already satisfies the requirement differently: add a `# NOTE: requirement met via <method>` comment and leave it

Do NOT break D3: `risk_flags` stays orchestrator-derived, never on `RiskRadarOutput` directly.

### 2c. SWA — align to ref/swa_guide + ref/swa_io

For each gap identified in the Gap Report:

- If a **required input field** is missing from `SWAInput` in `orchestrator/contracts.py`: add it
- If a **required output field** is missing from SWA's `AgentOutput` or `SwaOutput` in `orchestrator/schemas.py`: add it
- If `ref/swa_io` defines fields not in current `SwaOutput`: add them

Do NOT add notification/reminder execution code. SWA is detection + recommendation only (client confirmed Phase 2). If the guide mentions triggering actions, add a `# NOTE: Phase 2 — detection only in MVP` comment.

Do NOT break D6: `SwaOutput` must still mirror actual `AgentOutput` fields.

Commit: `feat: align CSA/RRA/SWA to ref specs`

---

## PHASE 3 — DB INIT + SEED CONSOLIDATION

### 3a. Target structure

```
AMP/
├── infra/
│   ├── db.py                  # shared SQLite utility: get_connection(), upsert_state()
│   ├── sqlite_init.py         # creates csa.db schema + state.db schema
│   ├── qdrant_init.py         # creates historical_cases + policy_knowledge collections
│   ├── seed_csa_db.py         # populates csa.db with synthetic emails/docs/history
│   ├── seed_qdrant.py         # ingests synthetic cases + policy docs into Qdrant
│   └── init_all.py            # runs all four in order (single entry point)
├── data/
│   ├── synthetic_cases/       # all input JSON cases (one file per case)
│   ├── outputs/               # AmpState results written here (gitignored)
│   └── policies/              # policy markdown files for GPA/RRA
│       ├── procurement.md
│       ├── claims.md
│       └── fraud.md
```

### 3b. infra/sqlite_init.py

Creates two DBs:

**CSA/data/csa.db** — per-case context records (CSA reads this)
Use schema from `ref/csa_db` and `CSA/core/db_schema.py` (post Phase 2 alignment).
Tables: emails, documents, calendar_events, case_history (at minimum).
Enable WAL: `PRAGMA journal_mode=WAL;`

**infra/state.db** — orchestrator workflow state (Streamlit reads this)
```sql
CREATE TABLE IF NOT EXISTS active_workflow_state (
    case_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    agent_status TEXT NOT NULL,       -- JSON blob: {csa: "done", rra: "running", ...}
    amp_state_json TEXT NOT NULL,     -- full AmpState as JSON
    risk_score REAL,
    requires_escalation INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_updated_at ON active_workflow_state(updated_at);
PRAGMA journal_mode=WAL;
```

### 3c. infra/seed_csa_db.py

Populate `CSA/data/csa.db` with synthetic records so demo cases return real context (not PARTIAL/empty).

Use `ref/csa_db` as the reference for record structure and field names.

Seed data must cover the three demo case IDs used in `demo/app.py`:
- Case 1: Simple low-risk vendor onboard
- Case 2: Missing documentation case  
- Case 3: High-risk requires_escalation case

For each demo case, insert realistic synthetic records into:
- `emails` table: 2–3 emails per case (sender, subject, body, timestamp, case_id)
- `documents` table: 1–3 documents per case (doc_type, filename, status, case_id)
- `calendar_events` table: 1–2 events per case
- `case_history` table: 3–5 history entries per case (event_type, actor, status, timestamp)

Case 2 (missing documentation): intentionally leave `documents` table empty for this case_id — CSA should return PARTIAL validation naturally.

Case 3 (high-risk): seed with risk indicators — documents present but compliance_cert status = "expired", case_history showing prior escalation events.

### 3d. infra/qdrant_init.py

Two collections:

**`historical_cases`** — IAA RAG retrieval
- Embedder: `all-MiniLM-L6-v2` (384-dim — matches existing IAA setup, do not change)
- Embed: `executive_summary` + `resolution` fields from synthetic case JSONs
- Metadata payload: `case_id`, `case_type`, `outcome`, `priority`, `required_skills`, `monetary_value`

**`policy_knowledge`** — GPA + RRA policy lookup
- Embedder: same `all-MiniLM-L6-v2`
- Source: markdown files in `data/policies/`
- Chunk size: 500 tokens, 50 token overlap
- Metadata payload: `case_type` (tag: "procurement" | "claims" | "fraud" | "generic"), `policy_section`, `source_file`
- Query pattern: filter by `case_type` tag first, then semantic search within results
- This satisfies client requirement: "JSON case going to RRA and GPA maps to which policy knowledge to look up"

If `data/policies/` files don't exist yet, create minimal stubs:
```markdown
# data/policies/procurement.md
## Vendor Onboarding Policy
- All vendors must provide compliance certificate before onboarding proceeds.
- Vendors with monetary_value > 25000 require procurement lead approval.
- Missing documentation triggers Risk Severity: Medium, Action: Request documentation.

# data/policies/claims.md  
## Claims Review Policy
- Claims above 50000 require senior adjuster review.
- Missing adjuster report blocks claim approval.
- SLA: 5 business days from submission.

# data/policies/fraud.md
## Fraud Investigation Policy
- All fraud cases require escalation to risk_review_team.
- Cases above 100000 require human-in-the-loop approval.
- Evidence chain must be documented before case closure.
```

### 3e. infra/seed_qdrant.py

Ingest all files from `data/synthetic_cases/` into `historical_cases` collection.
Ingest all files from `data/policies/` into `policy_knowledge` collection.
Skip if collection already has documents (idempotent — safe to re-run).

### 3f. infra/init_all.py

Single entry point that runs everything in order:

```python
"""
AMP Data Layer Initialization
Run once before starting agents: python -m infra.init_all
"""
import logging
from infra.sqlite_init import init_sqlite
from infra.qdrant_init import init_qdrant
from infra.seed_csa_db import seed_csa
from infra.seed_qdrant import seed_qdrant

logger = logging.getLogger(__name__)

def main():
    logger.info("Initializing SQLite databases...")
    init_sqlite()
    logger.info("Seeding CSA database with synthetic records...")
    seed_csa()
    logger.info("Initializing Qdrant collections...")
    init_qdrant()
    logger.info("Seeding Qdrant with cases and policies...")
    seed_qdrant()
    logger.info("Data layer ready.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
```

### 3g. Move/remove seed_db

Find where `seed_db` currently lives. 
- If it's a standalone script: move its logic into `infra/seed_csa_db.py` and delete the original
- If it's called from `start_agents.sh`: update the call to point to `python -m infra.init_all`
- If it duplicates init logic: consolidate, don't keep both

Commit: `refactor: consolidate DB init and seed into infra/`

---

## PHASE 4 — UPDATE start_agents.sh

Update `start_agents.sh` to run DB init before starting any agent.

Target sequence:
```bash
#!/bin/bash
set -e

echo "=== AMP: Initializing data layer ==="
python -m infra.init_all

echo "=== AMP: Starting agents ==="
uvicorn CSA.main:app --port 8001 &
uvicorn RRA.main:app --port 8002 &
uvicorn IAA.agent.api:app --port 8003 &
uvicorn GPA.main:app --port 8004 &
uvicorn DA.main:app --port 8005 &
uvicorn SWA.main:app --port 8006 &

echo "=== AMP: Waiting for agents to start ==="
sleep 5

echo "=== AMP: Starting orchestrator ==="
uvicorn orchestrator.main:app --port 8000 &

echo "=== AMP: Starting dashboard ==="
streamlit run demo/app.py --server.port 8501

echo "=== AMP: All services running ==="
echo "Dashboard: http://localhost:8501"
```

Notes:
- Verify the exact uvicorn module:app paths by checking each agent's actual entry point
- If any agent uses a different startup command (e.g. `python -m agent`), preserve it
- `set -e` ensures script aborts if init_all fails — agents must NOT start with broken DB

Commit: `feat: start_agents.sh runs DB init before agents`

---

## PHASE 5 — AITS INTEGRATION DOCUMENTATION

Create `docs/aits_integration.md`:

```markdown
# AITS → AMP Integration Point

## Trigger Flow

AITS triages an incoming event and POSTs to the AMP orchestrator:

POST http://<amp-host>:8000/run
Content-Type: application/json

{
  "case_id": "CASE-VND-001",
  "case_type": "vendor_onboarding",
  "task_type": "vendor_onboarding",
  "title": "Onboard Acme Corp",
  "description": "...",
  "requester": "procurement_team",
  "requester_role": "vendor_manager",
  "priority": "medium",
  "urgency": "moderate",
  "estimated_effort": 4.0,
  "due_date": "2026-04-26T17:45:21+00:00",
  "business_domain": "procurement",
  "required_skills": ["vendor_assessment", "compliance_review"],
  "monetary_value": 15000.0
}

## What happens next

Orchestrator → CSA (fetches case context from csa.db)
            → [RRA, IAA, GPA] in parallel (Stage 2)
            → DA (assigns task owner)
            → Returns AmpState JSON

## Response

AmpState JSON (see ampstate_spec.json for full schema).

## Demo simulation

The Streamlit dashboard simulates AITS by posting pre-loaded case payloads
via the "Run Workflow" button. No AITS connection needed for demo.
```

Commit: `docs: AITS integration point documentation`

---

## PHASE 4 — UPDATE start_agents.sh

`data/init_db.py` and `seed_db.py` already exist. Do not recreate them.

Update `start_agents.sh` to run them before any agent starts:

```bash
#!/bin/bash
set -e

echo "=== AMP: Initializing data layer ==="
python data/init_db.py

echo "=== AMP: Seeding state database ==="
python seed_db.py

echo "=== AMP: Starting agents ==="
# verify exact uvicorn paths against actual entry points before inserting
uvicorn CSA.main:app --port 8001 &
uvicorn RRA.main:app --port 8002 &
uvicorn IAA.agent.api:app --port 8003 &
uvicorn GPA.main:app --port 8004 &
uvicorn DA.main:app --port 8005 &
uvicorn SWA.main:app --port 8006 &

echo "=== AMP: Waiting for agents ==="
sleep 5

echo "=== AMP: Starting orchestrator ==="
uvicorn orchestrator.main:app --port 8000 &

echo "=== AMP: Starting dashboard ==="
streamlit run demo/app.py --server.port 8501
```

**seed_db.py must use INSERT OR IGNORE** (never plain INSERT) so re-running start_agents.sh never duplicates rows.

**SWA Postgres check:** Read `SWA/config/settings.py`. If it still references PostgreSQL or `DATABASE_URL` for any table, replace with SQLite path or make the connection optional — log a warning and continue, never crash on missing Postgres.

Verify both init scripts run without error before proceeding.

Commit: `feat: start_agents.sh runs DB init + seed before agents`

---

## PHASE 5 — FIX GPA: POLICY TABLES + CONFIDENCE SCORE

### Known issues (confirmed by gap report + observation):
- `governance_agent.db` has empty `policy_chunks`, `docs`, `rules` tables
- Confidence score is hardcoded — same value regardless of case
- GPA approves cases even when no policy docs are available
- Teammate has implemented an alternative approach in `ref/GPA_ref/`

### Instructions:

**Step 1: Read ref/GPA_ref/ completely.** Understand what your teammate changed. Extract the intent — do not blindly copy code. His implementation may have bugs but the approach may be sound.

**Step 2: Populate policy tables.** Using files from `data/policies/` (procurement.md, claims.md, fraud.md — create stubs if missing):
- Chunk each file into 300-500 token segments
- Insert into `policy_chunks` table with columns: `id`, `case_type`, `policy_section`, `content`, `source_file`
- Insert matching rules into `rules` table if schema supports it

**Step 3: Fix confidence score.** Replace hardcoded value with a computed score based on:
- Number of matching policy chunks retrieved (more matches = higher confidence)
- Whether `monetary_value` exceeds approval threshold from policy
- Whether `risk_flags` contain compliance-related items

Formula (simple, no LLM): `confidence = min(1.0, 0.4 * chunk_matches/5 + 0.3 * threshold_check + 0.3 * risk_alignment)`

**Step 4: Fix approval logic.** GPA must NOT approve when:
- No policy chunks were found for this case_type (set decision = "ESCALATE", confidence = 0.3, requires_approval = True)
- `monetary_value` exceeds threshold defined in policy (set requires_approval = True)
- `risk_flags` contains "compliance_risk" or "missing_input" (set requires_approval = True)

**Step 5: Adopt teammate's approach IF AND ONLY IF** it improves on the above without adding LLM calls or external dependencies. If his approach adds complexity without clear benefit, use the simpler fix above and add a `# NOTE: ref/GPA_ref approach reviewed, simpler rule-based fix used instead` comment.

Do NOT break D4 (build_da_task shim) or D7 (requires_escalation OR logic).

Commit: `fix: GPA policy tables populated, confidence computed, approval logic corrected`

---

## PHASE 6 — FIX SWA SQLITE WRITE PATH

### Known issues:
- `SWA/db/db.py` and `SWA/db/schemas.sql` exist but findings/escalations may not be persisted
- SWA runs `analyze()` directly (demo workaround per D6) but results are not queryable in SQLite

### Instructions:

**Step 1: Read `SWA/db/db.py` and `SWA/db/schemas.sql`.** Check what tables are defined and whether any write path exists.

**Step 2: After `analyze()` completes** in the orchestrator's SWA call, upsert the result into SWA's SQLite tables:
- `findings` table: one row per finding in `agent_output.findings`
- `escalations` table: one row per escalation in `agent_output.escalations`
- Use `case_id` + `run_id` as composite key for upsert (INSERT OR REPLACE)

**Step 3: Ensure SWA's SQLite DB path** is initialized in `data/init_db.py` (run schemas.sql on startup if tables don't exist).

**Step 4: Remove any Postgres reference** in `SWA/config/settings.py`. Replace with SQLite path. If `DATABASE_URL` env var was used, replace with `SWA_DB_PATH` defaulting to `infra/swa.db`.

Do NOT add Postgres back. Do NOT add notification/trigger code (detection only — Phase 2).

Commit: `fix: SWA writes findings and escalations to SQLite after analyze()`

---

## PHASE 7 — DEMO UI: JSON → REPORT CARDS

### Goal
Replace raw JSON viewer in each agent tab with human-readable report cards. Zero extra API calls — parse AmpState already in memory. Reference: screenshot shows tab layout (DA, RRA, GPA, IAA, SWA) with structured cards on left and "Suggested Next Actions" panel on right (IAA output already clean).

### Per-tab layout (implement in `demo/app.py`):

**DA tab:**
```
Assignment Summary
├── Assigned to: <selected_owner.role> (<selected_owner.team>)
├── Channel: <selected_channel>
├── Confidence: <confidence_score>%
├── Escalation required: Yes/No
└── Reasons: <reasons as bullet list>
Candidate Rankings: simple table (role, team, score)
```

**RRA tab:**
```
Risk Assessment
├── Overall Risk: <overall_risk_level> (colored badge: green/amber/red)
├── Can Proceed: <can_proceed>
├── Escalate to Human: Yes/No
├── Escalation Target: <escalation_target>
└── Summary: <reasoning_summary>
Risk Flags: <risk_flags as colored tags>
```

**GPA tab:**
```
Governance Decision
├── Decision: <decision> (colored badge)
├── Confidence: <confidence>%
├── Requires Approval: Yes/No
├── Approvers: <approvers list or "None">
└── Reason: <reason>
Matched Rules: <matched_rule_ids>
```

**IAA tab — keep existing "Suggested Next Actions" panel, add:**
```
Workflow Timeline: step-by-step list
├── Step 1: <event_type> — <actor> [completed/current/predicted]
Task List: table (task_id, action, assigned_role, priority)
```

**SWA tab:**
```
Pattern Detection
├── Patterns detected: <count>
├── Escalations raised: <count>
├── Window analyzed: <start> → <end>
Findings: expandable list (empty state: "No patterns detected")
```

**Implementation rules:**
- Use `st.columns`, `st.metric`, `st.dataframe`, `st.badge` (Streamlit native — no external libs)
- Colored badges: use `st.markdown` with inline HTML for colored pill spans (safe in Streamlit)
- Keep demo/app.py under 400 lines total
- If AmpState field is None or missing, show "—" not an error
- Do NOT call any API to generate this display — parse AmpState dict directly

Commit: `feat: demo UI replaces JSON viewer with report cards per agent tab`

---



- Do not break D1–D13 from decisions.md
- Do not modify IAA's Qdrant embedder or retriever logic
- Do not add SWA notification/trigger code (detection only — Phase 2)
- If ref file specifies a field that conflicts with an existing D1–D13 decision, flag it in GAP_REPORT.md and do NOT implement the conflicting change without confirmation
- Seed data must be deterministic (fixed UUIDs/IDs) so re-running init_all doesn't create duplicates
- All new code must use `logger = logging.getLogger(__name__)` — no print()
- If start_agents.sh uvicorn paths are wrong, fix them to match actual entry points found in the codebase

---

## DELIVERABLE

After all phases, output a summary:
- Fields added to AmpState (required_skills, monetary_value propagation)
- RRA/SWA gaps found and how each was addressed
- CSA DB schema changes made
- Seed data: how many records per demo case
- Qdrant: how many documents ingested per collection
- start_agents.sh: confirmed startup sequence
