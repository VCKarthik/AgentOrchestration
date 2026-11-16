# Shadow Work Agent v3 — Project AMP

A logging and analysis agent that observes the entire AITS workflow,
captures every event from all agents into a structured case-portfolio log,
and runs unsupervised analysis to detect repetitive manual work.

## What's new in v3

**Incremental learning.** The agent now generates 200 cases at once across
6 domains, and supports appending more cases on top. Each run saves a
**cluster snapshot** so you can see how patterns evolve as more data flows in.

After every run, the output includes a `cluster_evolution` section showing:

```
new_clusters         : patterns we hadn't seen before
strengthened_clusters: patterns growing (more events / more cases)
stable_clusters      : patterns roughly the same as last time
dissolved_clusters   : patterns that no longer cluster
```

**SQLite database.** v3 uses a local SQLite file (`swa_v3.db`) instead of
PostgreSQL — no server to run, no credentials to configure. Open the file
directly in any SQLite browser (DB Browser for SQLite, TablePlus, DBeaver).

**Adaptive ML.** The DBSCAN clustering detector automatically skips when
there isn't enough data (fewer than 10 cases or 100 events). The three
heuristic detectors always run regardless of data size, so single-case
integration demos still produce valid recommendations.

## Two-Module Architecture (per client feedback)

```
┌─────────────────────────────────────────────────────────────┐
│  MODULE 1: LOGGING TOOL  (ingestion + storage)              │
│  • Receives events from all 5 other AITS agents             │
│  • Validates against the data dictionary                    │
│  • Sorts and stores by case_id                              │
│  • Builds case portfolios (full history per case)           │
│  • This is the SOURCE OF TRUTH for all downstream work      │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MODULE 2: ANALYSIS ENGINE  (reporting + learning)          │
│  • Runs heuristic detectors (frequency, regularity)         │
│  • Runs unsupervised ML clustering (DBSCAN) when data       │
│    is sufficient (≥10 cases, ≥100 events)                   │
│  • Saves cluster snapshots after every run                  │
│  • Compares with previous snapshot — incremental learning   │
│  • Scores and decides: recommend / watch / escalate         │
│  • LLM enrichment with explicit case-by-case usage rules    │
│  • Produces structured JSON output + persisted audit trail  │
└─────────────────────────────────────────────────────────────┘
```

## Project structure

```
swa_v3/
├── README.md
├── SETUP.md
├── requirements.txt
├── .env                        ← DB path + Gemini key (you create this)
├── swa_v3.db                   ← SQLite database (auto-created on first run)
├── config/settings.py          ← thresholds + closed vocabulary
├── db/
│   ├── schema.sql              ← SQLite schema (6 tables)
│   └── db.py                   ← connection + query helpers
├── agent/
│   ├── models.py               ← Pydantic schemas
│   ├── logging_tool.py         ← MODULE 1: ingest + store + validate
│   ├── case_portfolio.py       ← case-level history builder
│   ├── normalizer.py           ← domain-blind signature creation
│   ├── detectors.py            ← heuristic detectors
│   ├── ml_detector.py          ← DBSCAN with cluster fingerprinting
│   ├── cluster_tracker.py      ← snapshot save + comparison
│   ├── scorer.py               ← rules-based scoring
│   ├── llm_enricher.py         ← LLM with explicit case dispatch
│   ├── escalator.py            ← escalation formatting
│   └── orchestrator.py         ← pipeline controller (single entry)
├── data/
│   ├── synthetic_events.py     ← 200-case generator with --append
│   └── synthetic_events.json   ← saved snapshot
├── docs/
│   ├── DATA_DICTIONARY.md
│   ├── RULES_SHEET.md
│   ├── LLM_CASES.md
│   └── SHADOW_WORK_AGENT.md    ← agent overview document
├── app.py                      ← Flask UI server (localhost:5050)
├── templates/index.html        ← Case Intelligence dashboard
├── tests/test_agent.py         ← offline sanity tests
└── output/                     ← runtime logs + JSON outputs
```

## Quick start

```bash
# 1. Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # edit: add your Gemini API key

# 2. Initialise the SQLite database
python -c "from db.db import init_db; init_db()"

# 3. Generate the initial 200 cases
python -m data.synthetic_events --count 200

# 4. Run the agent — saves the first cluster snapshot
python -m agent.orchestrator

# 5. Add 20 more cases and re-run — see cluster evolution
python -m data.synthetic_events --append --count 20
python -m agent.orchestrator

# 6. View the snapshot timeline
python -m agent.orchestrator --evolution

# 7. Open the dashboard
python app.py                   # visit http://localhost:5050
```

## ML detector — data thresholds

The DBSCAN clustering detector only runs when there is enough data for
patterns to be statistically meaningful:

| Condition | ML detector | Heuristic detectors |
|---|---|---|
| < 10 cases **or** < 100 events | Skipped | Always run |
| ≥ 10 cases **and** ≥ 100 events | Runs | Always run |

When ML is skipped the output notes the reason:

```
ml:skipped (need ≥100 events, ≥10 cases — have 12 events, 1 case)
```

Thresholds are configurable in `.env`:
```
ML_MIN_EVENTS=100
ML_MIN_CASES=10
```

## What you'll see after step 5

The output JSON will include a `cluster_evolution` section:

```json
"cluster_evolution": {
  "previous_total_cases": 200,
  "current_clusters_count": 14,
  "delta_summary": {
    "new_clusters": 1,
    "strengthened_clusters": 6,
    "stable_clusters": 7,
    "dissolved_clusters": 0
  }
}
```

## Database

The database is a single SQLite file at the project root:

```
swa_v3.db
```

Open it with any SQLite browser — no server, no credentials needed.

| Table | Purpose |
|---|---|
| `cases` | Case registry |
| `activity_log` | All ingested events (source of truth) |
| `case_portfolios` | Per-case summaries |
| `analysis_runs` | Audit trail of every agent run |
| `cluster_snapshots` | ML cluster state per run |
| `ingestion_log` | Record of every ingest attempt |

## Useful commands

```bash
# Skip case portfolios (faster on big DB)
python -m agent.orchestrator --no-portfolios

# Scope to one specific case
python -m agent.orchestrator --case_id case_vendor_0001

# Inspect the DB directly
sqlite3 swa_v3.db "SELECT COUNT(*) FROM cases;"
sqlite3 swa_v3.db "SELECT COUNT(*) FROM activity_log;"
sqlite3 swa_v3.db "SELECT snapshot_id, total_cases, total_events, clusters_found FROM cluster_snapshots;"

# Watch the agent log live
tail -f output/agent.log
```

## What changed from v2

| | v2 | v3 |
|---|---|---|
| Database | PostgreSQL (requires server) | SQLite (single file, no server) |
| Synthetic cases | 5 cases, 3 domains | 200 cases, 6 domains |
| Synthetic events | ~20 events | ~2,300 events |
| ML clusters found | 0 (too sparse) | 10–15 (genuine patterns) |
| ML adaptive threshold | None | Skips automatically on small data |
| Append more cases | Not supported | `--append --count N` |
| Cluster tracking | None | Snapshots + delta vs previous |
| Cluster fingerprinting | None | Stable identity across runs |
| UI dashboard | None | Flask app at localhost:5050 |
