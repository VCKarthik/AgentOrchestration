# Project AMP — Agentic Microservices Prototyping

> A production-ready **6-agent workflow automation system** that routes complex operational cases through parallel AI analysis and assigns them to the right owner — automatically.

Cases flow through a LangGraph-orchestrated pipeline: **context retrieval → parallel risk / governance / intent analysis → intelligent task delegation**, with a shadow monitoring agent running continuously in the background.

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat&logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-FF6B35?style=flat)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B?style=flat&logo=streamlit&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_2.0_Flash-Google_AI-4285F4?style=flat&logo=google&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat&logo=sqlite&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-DC244C?style=flat)
![Pydantic](https://img.shields.io/badge/Pydantic_v2-E92063?style=flat)

---

## Features

- **Multi-stage LangGraph pipeline** — CSA enriches the case; RRA / GPA / IAA run in parallel; DA assigns
- **LLM-powered intent prediction** — IAA uses Gemini 2.0 Flash + Qdrant RAG over process history to recommend the next action
- **Rule-based governance** — GPA evaluates tasks against seeded policy documents with dynamic confidence scoring
- **Risk radar** — RRA applies 5 rule categories (deadline, compliance, missing input, dependency, historical delay) with no LLM latency
- **Fast-path escalation** — IAA bypasses the LLM for high / critical risk or missing-doc flags (~0 ms vs ~3-5 s)
- **Shadow work monitoring** — SWA runs as an in-process background agent, analysing patterns and detecting bottlenecks
- **Enterprise dashboard** — Streamlit UI with priority queue, live 6-chip agent progress bar, and per-agent result cards
- **Partial failure tolerance** — if RRA, GPA, or IAA fails, DA receives `None` and sets `requires_escalation=True`; workflow never crashes
- **Full observability** — LangSmith tracing on every `call_*` tool function via `@traceable`

---

## Architecture

```
  ┌──────────────────────────────────────────┐
  │    Streamlit Dashboard  :8501            │
  │    demo/app.py                           │
  └───────────────────┬──────────────────────┘
                      │  run_amp_workflow()
                      ▼
            orchestrator/flow.py
                      │
         ┌────────────▼────────────┐
         │      Stage 1: CSA       │  ← fetches emails, docs, history from csa.db
         │         :8001           │    + SWA shadow analysis (async background)
         └────────────┬────────────┘
                      │ AmpState
         ┌────────────▼────────────────────────────────┐
         │           Stage 2 — parallel                │
         │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
         │  │   RRA    │  │   GPA    │  │   IAA    │  │
         │  │  :8002   │  │  :8004   │  │  :8003   │  │
         │  │   Risk   │  │  Policy  │  │  Intent  │  │
         │  └──────────┘  └──────────┘  └──────────┘  │
         └────────────┬────────────────────────────────┘
                      │ AmpState
         ┌────────────▼────────────┐
         │      Stage 3: DA        │  ← selects owner, channel, assignee
         │         :8005           │
         └─────────────────────────┘
```

**AmpState** (`data/AmpState_spec.json`) is the single source of truth — all inter-agent data flows through it.  
**Shims** (`orchestrator/shims.py`) own all field mapping between agents — no mapping logic anywhere else.

### Agent Summary

| Agent | Port | Role | LLM? |
|-------|------|------|------|
| CSA — Context Stitching Agent | 8001 | Retrieves emails, docs, calendar events, and history from SQLite | No |
| RRA — Risk Radar Agent | 8002 | Applies 5 risk rules; produces severity + proceed decision | Optional |
| IAA — Intent Anticipation Agent | 8003 | Predicts next action via Gemini + Qdrant RAG | Yes (Gemini) |
| GPA — Governance & Policy Agent | 8004 | Matches task against seeded policy rules; APPROVE or ESCALATE | No |
| DA — Delegation Agent | 8005 | Selects owner, channel, and assignee | No |
| SWA — Shadow Work Agent | in-process | Detects patterns and bottlenecks across the portfolio | Optional |

---

## Getting Started

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | `python --version` |
| Google AI Studio key | Required for IAA LLM calls |
| Docker + Compose | Optional — only needed for `make demo` |

### Installation

```bash
# 1. Clone the repo
git clone <repo-url>
cd ProjectAMP26

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows (Git Bash): source .venv/Scripts/activate

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Open .env and set:
#   GOOGLE_API_KEY=<your-google-ai-studio-key>
#   GEMINI_API_KEY=<same value>
#   LLM_PROVIDER=gemini
```

### Initialize the data layer (run once, then on every restart)

```bash
python -m infra.init_all
# Steps run by init_all (production mode):
#   1. infra/state.db — orchestrator run/state SQLite
#   2. CSA/data/csa.db — emails, documents, calendar, case_history seeded for
#      the three canonical workflows (CASE-1001, CASE-2001, CASE-3001)
#   3. Qdrant collections — historical_cases + policy_knowledge
#   4. SWA/swa_v3.db — empty schema (no synthetic seed in production mode)
# Safe to re-run — all steps are idempotent.
# Customer data (policies, workflow contexts, team roster) is loaded at
# runtime via the Streamlit sidebar — see "Demo flow" below.
```

### Running the agents and demo

**Option A — `start_agents.sh` (Linux / Git-Bash / bash 4+):**
```bash
bash start_agents.sh
# Starts CSA :8001 · RRA :8002 · IAA :8003 · GPA :8004 · DA :8005
# Note: the script uses associative arrays — needs bash 4+. macOS ships
# bash 3.2, so use Option B on macOS.
```

**Option B — direct uvicorn (macOS / any platform):**
```bash
# 1. Load env vars (Gemini key etc.)
set -a; source .env; set +a

# 2. Add IAA + GPA to PYTHONPATH (their internal imports need it)
export PYTHONPATH="IAA:GPA:${PYTHONPATH:-}"

# 3. Start all 5 agents in the background
mkdir -p logs
for entry in \
    "CSA.api.main:app|8001|csa" \
    "RRA.api:app|8002|rra" \
    "IAA.agent.api:app|8003|iaa" \
    "GPA.app:app|8004|gpa" \
    "DA.delegation_agent.api:app|8005|da"; do
    module="${entry%%|*}"; rest="${entry#*|}"
    port="${rest%%|*}"; name="${rest#*|}"
    nohup python3 -m uvicorn "$module" --port "$port" --log-level warning \
        >> "logs/agent_${name}.log" 2>&1 &
done

# 4. Wait for agents to come up (CSA + IAA load BERT — ~30-90 s on first run)
for port in 8001 8002 8003 8004 8005; do
    until curl -sf "http://localhost:$port/health" > /dev/null 2>&1; do sleep 2; done
    echo ":$port healthy"
done

# 5. Start Streamlit (without IAA/GPA on PYTHONPATH — those entries
#    shadow SWA's `config` package and break the orchestrator import)
unset PYTHONPATH
python3 -m streamlit run demo/app.py --server.port 8501
# Open http://localhost:8501
```

**Stop everything:**
```bash
pkill -f "uvicorn.*api:app|uvicorn.*GPA.app|streamlit run demo/app.py"
```

### Docker quick start

```bash
make demo    # build images + start everything (~3 min first run)
# Open http://localhost:8501
make stop    # shut down
make clean   # stop + delete all data volumes
```

### Running tests

```bash
# IAA unit tests — no API key needed (run from IAA/ directory)
cd IAA && python -m pytest test_iaa.py -v

# IAA integration tests — real Gemini key required
cd IAA && python -m pytest test_iaa.py -m integration

# RRA rule-engine tests
pytest RRA/tests/ -v
```

---

## Demo flow — running the three workflows end-to-end

The system runs in **production mode**: every customer-specific data layer
(SWA case corpus, GPA policies, DA team roster) starts empty and is loaded at
runtime through the Streamlit sidebar. The three canonical workflows are
pre-wired with intake records in CSA's DB but their downstream context comes
from uploads.

### Step 1 — Open the dashboard

```
http://localhost:8501
```

The Case Queue (left column) shows three cases pre-loaded for demo:

| Case ID    | Workflow              | Description |
|------------|-----------------------|-------------|
| `CASE-1001` | vendor_onboarding    | TechSupply Inc. — insurance certificate missing, NDA pending |
| `CASE-2001` | interview_scheduling | Sarah Johnson — background check + competitor conflict of interest |
| `CASE-3001` | claim_review         | David Kim — $1,200 medical claim, all docs verified |

### Step 2 — Load customer-specific data (sidebar)

Open the sidebar (top-left ☰). Three upload panels stack below the View
selector. Sample files ship in [`data/`](data/):

| Sidebar panel | Sample files | What gets populated |
|---|---|---|
| **Workflow Context** | `data/workflow_contexts/{vendor_onboarding,claim_review,interview_scheduling}_context.json` | SWA's case corpus (past cases + activity events) |
| **Policy Documents** | `data/policies/{procurement,claims,interview_scheduling}.md` | GPA's `policy_documents`, `policy_chunks`, `policy_rules` |
| **Team Roster** | `data/assignee_rosters/sample_roster.json` | DA's assignee pool (9 people across 6 departments) |

Each panel has a **Reset … database** button that wipes only that agent's
runtime data — useful between demos.

### Step 3 — Run a case

1. Click a case in the left queue.
2. Press **Run workflow**.
3. Watch the agent progress chips light up (CSA → RRA · GPA · IAA → DA).
4. Each agent's result card appears below with detail (risk items, policy
   matches, predicted next action, assigned owner, etc.).

### Step 4 — Observatory (optional)

Switch to **SWA Observatory** in the sidebar:
- The DB content shows what's loaded (cases / events / findings / escalations).
- Click **Run analysis now** to mine patterns from the loaded corpus —
  findings + escalations + cluster snapshots are written to the DB and
  surfaced across five tabs.
- SWA does **not** auto-analyze on case submission; it only ingests new
  cases. You control when pattern mining runs.

### Step 5 — Reset between demos

Each agent's data layer has its own reset:
- **Reset SWA database** (in Workflow Context panel) — clears cases, events, findings, escalations, cluster snapshots.
- **Reset GPA database** (in Policy Documents panel) — clears policy documents, chunks, rules.
- **Reset team roster** (in Team Roster panel) — deletes `data/assignee_rosters/active_roster.json`. DA falls back to "no candidates" until a roster is uploaded again.

A clean demo cycle: **reset all three → upload three policies → upload three
contexts → upload roster → run a case.**

---

## Usage

### Programmatic workflow run

```python
from orchestrator.flow import run_amp_workflow
import asyncio

result = asyncio.run(run_amp_workflow({
    "task_id":         "TASK-1001",
    "case_id":         "CASE-1001",
    "task_type":       "vendor_onboarding",
    "title":           "Vendor onboarding — incomplete documents — TechSupply Inc.",
    "description":     "TechSupply Inc. onboarding stalled. Insurance certificate "
                       "missing and NDA pending review.",
    "priority":        "high",
    "urgency":         "urgent",
    "requester":       "procurement@acme.com",
    "requester_role":  "procurement_manager",
    "business_domain": "procurement",
    "monetary_value":  150000,
    "estimated_effort": 4.0,
}))

print(result["da_output"]["selected_owner"])       # assigned team / agent
print(result["da_output"]["escalation_required"])  # True / False
print(result["risk_output"]["overall_risk_level"]) # low / medium / high / critical
print(result["governance_output"]["decision"])      # APPROVE / ESCALATE
```

> **Note:** Programmatic runs assume policies, workflow contexts, and a
> roster have been uploaded — otherwise GPA returns no rule matches and DA
> escalates with "no eligible assignees". Either upload via the Streamlit
> sidebar first, or seed programmatically (see
> `data/policies/`, `data/workflow_contexts/`, `data/assignee_rosters/`).

### Health-check all agents

```bash
for port in 8001 8002 8003 8004 8005; do
    echo -n "  :$port → "
    curl -sf http://localhost:$port/health
    echo
done
```

### LangGraph Studio test payload

```json
{
  "task_intake": {
    "task_id":         "TASK-1001",
    "case_id":         "CASE-1001",
    "task_type":       "vendor_onboarding",
    "title":           "Vendor onboarding — incomplete documents — TechSupply Inc.",
    "description":     "TechSupply Inc. onboarding stalled. Insurance certificate missing and NDA pending review.",
    "priority":        "high",
    "urgency":         "urgent",
    "requester":       "procurement@acme.com",
    "requester_role":  "procurement_manager",
    "business_domain": "procurement",
    "monetary_value":  150000,
    "estimated_effort": 4.0
  }
}
```

Or substitute `CASE-2001` (interview_scheduling) / `CASE-3001` (claim_review)
for the other two demo workflows.

### LangSmith tracing

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your-langsmith-key>
export LANGCHAIN_PROJECT=amp-orchestrator
# All call_* functions in orchestrator/tools.py trace automatically
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_API_KEY` | — | Google AI Studio key (IAA + optional RRA summarizer) |
| `GEMINI_API_KEY` | — | Same value — different agents use different var names |
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` — IAA LLM backend |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model ID passed to IAA |
| `SWA_DB_PATH` | `infra/swa.db` | SWA SQLite write-path |
| `LANGCHAIN_TRACING_V2` | `false` | Enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | — | LangSmith API key |
| `LANGCHAIN_PROJECT` | `amp-orchestrator` | LangSmith project name |

---

## Project Structure

```
ProjectAMP26/
├── CSA/                    # Context Stitching Agent (port 8001)
├── RRA/                    # Risk Radar Agent (port 8002)
├── IAA/                    # Intent Anticipation Agent (port 8003)
├── GPA/                    # Governance & Policy Agent (port 8004)
├── DA/                     # Delegation Agent (port 8005)
├── SWA/                    # Shadow Work Agent (in-process, no HTTP server)
├── orchestrator/           # LangGraph flow, tools, shims, contracts
├── demo/
│   ├── app.py              # Streamlit dashboard
│   ├── observatory.py      # SWA Observatory page
│   ├── workflow_context.py # Sidebar uploader for SWA case corpus
│   ├── policy_context.py   # Sidebar uploader for GPA policies
│   └── assignee_context.py # Sidebar uploader for DA team roster
├── infra/                  # DB init, seed scripts, state.db
├── data/
│   ├── policies/                # Sample policy markdown (procurement, claims, …)
│   ├── workflow_contexts/       # Sample SWA backdrop JSONs (one per workflow)
│   ├── assignee_rosters/        # Sample team roster JSON
│   └── AmpState_spec.json       # Canonical inter-agent schema
├── docs/                   # Decision log, AITS integration guide
├── start_agents.sh         # One-command agent launcher (bash 4+)
└── .env.example            # Environment variable template
```

---

## Key Design Decisions

| ID | Decision |
|----|---------|
| D1 | `context_summary` removed from IAA `ProcessState` — CSA never generated it |
| D3 | `risk_flags` derived by orchestrator from `risk_items[].risk_type.value` |
| D4 | `build_da_task()` shim merges task_intake + IAA TaskItem + GPA output for DA |
| D5 | `meta.operating_context = "partial"` if RRA or IAA reported partial context |
| D7 | `requires_escalation` = any of four agent escalation signals (OR logic) |

Full rationale with history: `docs/decisions.md`
