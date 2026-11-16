# Project AMP — Handoff Guide

For whoever runs or extends this system after the April 29, 2026 demo.

---

## How to run the demo

```bash
cp .env.example .env
# Fill in GOOGLE_API_KEY and GEMINI_API_KEY (same value from Google AI Studio)
make demo
# Open http://localhost:8501
```

Click one of the three pre-loaded demo cases, then ▶ RUN WORKFLOW.

---

## How to add a new agent

1. Create `NEW_AGENT/` with:
   - `api.py` — FastAPI app with `POST /predict` and `GET /health`
   - `requirements.txt` — agent-specific deps (or rely on root `requirements.txt`)
2. Pick a port (next available after 8005)
3. Add to `docker-compose.yml` as a new service following the `&agent` anchor pattern
4. Add `NEW_AGENT_URL=http://new_agent:PORT` env var to the `dashboard` service in compose
5. Add the HTTP call in `orchestrator/tools.py` (follow pattern of `_call_csa_impl`)
6. Add input/output shims in `orchestrator/shims.py`
7. Add input contract model in `orchestrator/contracts.py`
8. Wire into the LangGraph flow in `orchestrator/flow.py`

**Rule:** Never pass full AmpState to the agent. Build a slim contract via
`build_*_input()` in shims.py and send only that.

---

## How to add a new policy document

1. Drop a `.md` file into `data/policies/`
2. Name it to match a case type for automatic routing:
   - `procurement.md` → `case_type=vendor_onboarding`
   - `claims.md`      → `case_type=claim_review`
   - `fraud.md`       → `case_type=fraud_investigation`
   - anything else    → `case_type=general`
3. Re-run `make init` (or `python data/init_db.py`) to re-ingest
4. GPA and RRA will find the new policy via `policy_knowledge` Qdrant collection
   filtered by `case_type`

---

## Where logs live

| What | Where |
|---|---|
| IAA prediction audit | `logs/` (or `IAA/data/predictions.jsonl` locally) |
| SWA analysis output | `output/agent.log` |
| Docker service logs | `make logs` (tails dashboard) or `docker compose logs -f <service>` |
| LangSmith traces | Set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` in `.env` |

---

## How to reset state

```bash
make clean
# Deletes: infra/qdrant_store, infra/state.db, Docker volumes
# Does NOT delete agent-local DBs (CSA/data/csa.db, GPA/governance_agent.db)
```

To reset agent-local DBs:
```bash
rm -f CSA/data/csa.db GPA/governance_agent.db
# They will be recreated from seed data / schema on next agent start
```

---

## Known limitations (in scope for Phase 2 post-demo)

| Limitation | Status | Fix |
|---|---|---|
| SWA uses PostgreSQL (not SQLite) | Deferred (BLOCKER-1) | Rewrite `SWA/db/db.py` with SQLite DDL |
| CSA and GPA have agent-local DBs, not the shared `infra/state.db` | Deferred (BLOCKER-2) | Extract DB layer behind abstraction |
| Phase 2 FULL not applied — 14 `dict[str,Any]` dynamic sites + bare excepts in SWA/GPA/DA remain | Deferred (by choice) | Run Phase 2 option 1 if Gemini schema validation errors appear |
| SWA is detection-only | **By design** | Notification/automation is Phase 2 client scope |
| IAA Qdrant store path may need `QDRANT_HOST` set in Docker | See BLOCKER-3 | Set `QDRANT_HOST=qdrant` in `.env` when running via compose |

---

## Architecture decision log

Full rationale: `docs/decisions.md` (D1–D13)

Quick ref (`CLAUDE.md`):

| Decision | What |
|---|---|
| D1 | `context_summary` Optional[str] = None in IAA ProcessState |
| D3 | `risk_flags` is orchestrator-derived, never on RRA output |
| D8 | IAA always runs in Stage 2 (needs_iaa = True unconditionally) |
| D9 | IAA fast path skips LLM for high/critical risk or missing-doc flags |
| D10 | `GEMINI_MODEL` env var, default `gemini-2.0-flash` |
| D12 | Two key var names (`GOOGLE_API_KEY` and `GEMINI_API_KEY`) — same value |
| D13 | Dashboard at `demo/app.py`, live updates via `st.empty()` refs |

---

## Refactor summary (2026-04-25)

| Metric | Before | After |
|---|---|---|
| IAA latency | ~52 s (worst case) | ~3–5 s (LLM path), 0 ms (fast path) |
| Qdrant top-k | 4 docs (unbounded body) | 2 docs, 400 chars each |
| Orchestrator→IAA payload | Full ProcessState + all emails | 945 chars (5 events + 3 email headers) |
| Data directories | 4 (`data/`, `CSA/data/`, `IAA/data/`, `SWA/data/`) | 4 (consolidated in infra/ + policies + synthetic_cases) |
| Docker support | IAA only | All agents + qdrant + dashboard |
| One-command demo | No | `make demo` → http://localhost:8501 |
| Files to touch for demo | `.env` + multiple terminal windows | Just `.env` |
