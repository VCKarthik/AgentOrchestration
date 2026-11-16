# Shadow Work Agent v3 — Setup Guide

## Prerequisites

- Python 3.10+
- VS Code with Python extension
- A Gemini API key (for LLM enrichment — the agent runs without one, but findings won't have domain-contextualized descriptions)

No database server required. v3 uses SQLite — a single local file, auto-created on first run.

## Setup

### 1. Copy project files into VS Code

Create folder `SWA_V3_BUILD` and copy every file preserving structure.

### 2. Virtual environment

```bash
cd SWA_V3_BUILD
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

Create a `.env` file in the project root:

```
DB_PATH=swa_v3.db
GEMINI_API_KEY=<your-key>
```

`DB_PATH` is the path to the SQLite database file. The default `swa_v3.db` places it at the project root — no server, no credentials needed.

Leave `GEMINI_API_KEY` blank or omit it to run in heuristic-only mode (LLM enrichment will be skipped gracefully).

### 4. Initialise the database

```bash
python -c "from db.db import init_db; init_db()"
```

This reads `db/schema.sql` and creates the six tables inside `swa_v3.db`. You should see no output — the file will appear at the project root.

Verify:
```bash
sqlite3 swa_v3.db ".tables"
```
Expected: `activity_log  analysis_runs  case_portfolios  cases  cluster_snapshots  ingestion_log`

### 5. Generate the initial 200 cases

```bash
python -m data.synthetic_events --count 200
```

Expected output:
```
[fresh] generating 200 cases across 6 domains...
[breakdown]
  auto_claims: 33 cases
  construction: 33 cases
  healthcare_referrals: 33 cases
  legal_intake: 34 cases
  recruiting: 34 cases
  vendor_onboarding: 33 cases
[snapshot] wrote 200 cases, ~2300 events to data/synthetic_events.json
[ingest] registering 200 cases...
[ingest] ingesting ~2300 events via logging_tool...
[done] ~2300 events accepted, 0 rejected
```

### 6. Run the agent — first snapshot

```bash
python -m agent.orchestrator
```

With 200 cases and ~2,300 events the ML detector (DBSCAN) will run and find 10–15 natural clusters. The first cluster snapshot is saved automatically.

> **Fewer than 10 cases or 100 events?** The ML detector will be skipped automatically and the output will note why. Heuristic detectors always run regardless of data size, so single-case demos still produce valid recommendations.

### 7. Add 20 more cases and re-run

```bash
python -m data.synthetic_events --append --count 20
python -m agent.orchestrator
```

The output now includes a `cluster_evolution` section showing what changed since the previous run.

### 8. View the cluster timeline

```bash
python -m agent.orchestrator --evolution
```

Prints all snapshots in chronological order, showing how cluster count and event count have grown.

### 9. Open the dashboard

```bash
python app.py
```

Visit [http://localhost:5050](http://localhost:5050). Select a domain, pick a case, and see its activity log, outcome summary, recommendation, and escalation cards.

## Useful commands

```bash
# Skip case portfolios (faster on big DB)
python -m agent.orchestrator --no-portfolios

# Scope to one specific case
python -m agent.orchestrator --case_id case_vendor_0001

# Check what's in the DB
sqlite3 swa_v3.db "SELECT COUNT(*) FROM cases;"
sqlite3 swa_v3.db "SELECT COUNT(*) FROM activity_log;"

# Inspect snapshots
sqlite3 swa_v3.db "SELECT snapshot_id, total_cases, total_events, clusters_found FROM cluster_snapshots;"

# Watch the agent log live
tail -f output/agent.log
```

You can also open `swa_v3.db` directly in any SQLite GUI (DB Browser for SQLite, TablePlus, DBeaver) — no connection string or credentials needed.

## Troubleshooting

**"ModuleNotFoundError: No module named 'sklearn'"**
→ `pip install -r requirements.txt` (make sure the venv is activated)

**"no such table: cluster_snapshots"**
→ Schema wasn't initialised. Run: `python -c "from db.db import init_db; init_db()"`

**ML detector skipped — "need ≥100 events and ≥10 cases"**
→ Expected when running on a single case or a small demo dataset. Heuristic detectors still produce recommendations. To enable ML, generate enough cases: `python -m data.synthetic_events --count 200`

**"already have a venv from v2"**
→ Make a fresh one for v3 — v2 required psycopg3 which is no longer needed and may conflict.

**LLM enrichment not running**
→ Check the UI header for the key status pill, or verify `GEMINI_API_KEY` is set in `.env`. The agent runs without it — heuristic findings will use template descriptions instead.
