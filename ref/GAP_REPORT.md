# AMP Phase 0 — Gap Report

**Date:** 2026-04-28  
**Branch:** AMP_integrated  
**Scope:** Pre-demo data layer audit against ref/ specs before consolidation

---

## 1. CSA Gap

**Reference:** `ref/csa.db`  
**Live:** `CSA/data/csa.db` (schema defined in `CSA/core/db_schema.py`)

| Item | ref/csa.db | Live csa.db | Gap |
|---|---|---|---|
| Tables | emails, documents, calendar_events, case_history, query_runs | Same 5 tables | None |
| Column set per table | Identical | Identical | None |
| CASE-1001, CASE-2002, CASE-3003 | All 4 tables populated | All 4 tables populated | None |
| CASE-1234 (claim_review) | emails only (2 rows — E4623AB, EE7E210) | Absent | Ad-hoc test rows; not canonical |
| CASE-123456 (claim_review) | emails only (1 row — EDD08A1) | Absent | Ad-hoc test row; not canonical |
| `file_link` column | Absent | Absent | Both omit it; AmpState spec documents it as a JSON-level field returned as `null` — no DB schema change needed |

**Verdict:** Schema is identical. The two extra cases in `ref/csa.db` are ad-hoc test inserts, not canonical seed — **do not replicate to live DB.** No CSA schema changes required.

---

## 2. RRA Gap

**Reference:** `ref/rra_guide.md`  
**Live:** `RRA/schema.py`, `RRA/agent.py`

| Item | Spec (rra_guide.md) | Actual (RRA/schema.py) | Gap |
|---|---|---|---|
| RiskType values | 5: missing_input, deadline_risk, dependency_risk, historical_delay, compliance_risk | 7: adds coordination_risk, ambiguity_risk | Extension only — not a regression |
| CaseInput fields | task_id, workflow_type, workflow_state, required_inputs, received_inputs, mandatory_inputs, policy_flag, blocker_flag, prior_delay_count, prior_escalation_count | All present | None |
| RiskRadarOutput fields | task_id, workflow_state, priority, risk_items, overall_risk_level, can_proceed, escalate_to_human, escalation_target, reasoning_summary, operating_context, model_used, timestamp | All present | None |
| `monetary_value` in input | Not in guide | Not in CaseInput | **Gap — new field from AmpState spec; must flow through shim when present** |
| `required_skills` in input | Not applicable to RRA | Not in CaseInput | Not applicable |
| Decision matrix logic | 5 deterministic rules | Implemented in RRA/agent.py | None |

**Verdict:** RRA is spec-compliant. `monetary_value` flows in at `task_intake` level — no RRA source changes needed (shims handle it).

---

## 3. SWA Gap

**Reference:** `ref/swa_guide.md`, `ref/SWA_IO.md`  
**Live:** `SWA/agent/models.py`, `SWA/agent/orchestrator.py`, `SWA/config/settings.py`

| Item | Spec | Actual | Gap |
|---|---|---|---|
| `IncomingCase` fields | case_id, case_type, status, created_at, closed_at, domain_metadata | All present in models.py | None |
| `IncomingEvent` required fields | event_id, case_id, timestamp, actor_id, actor_type, action_type, target_entity, target_entity_type, outcome | All present | None |
| `IncomingEvent` optional fields | parent_task_id, context_payload | Both present | None |
| `action_type` vocabulary | 17 values across 3 categories | Matches settings.ALL_ACTION_TYPES | None |
| `target_entity_type` vocabulary | external_contact, internal_system, internal_user, task, document | Matches settings.VALID_TARGET_TYPES | None |
| Output shape | findings, escalations, case_portfolios, metrics, cluster_evolution | AgentOutput has all sections | None |
| Integration pattern | ingest_case → ingest_batch → analyze | orchestrator calls analyze() directly | **Gap — intentional demo workaround** |
| DB backend | Postgres (ingestion_log table) | settings.py configured for Postgres; not provisioned for demo | **Gap — Postgres not available demo-time** |

**AITS Integration Point (for post-demo wiring):**  
The full SWA integration requires calling `SWA.agent.logging_tool.ingest_case()` and `ingest_batch()` before `analyze()`. The orchestrator currently bypasses this by calling `analyze()` directly, passing `case_history` events in-process via `case_history_to_incoming_events()` shim. This avoids the Postgres dependency for demo but loses persistent pattern learning across runs.

**To enable full SWA:** provision Postgres, call `ingest_case` at workflow start, `ingest_batch` after each agent completes, then `analyze` at the end.

**Verdict:** SWA models are spec-compliant. The direct `analyze()` path is an acceptable demo workaround. No code changes needed for Phase 0.

---

## 4. AmpState Gap — `required_skills` and `monetary_value`

**Verified current state:** Both fields are already present everywhere they need to be.

| Field | `data/AmpState_spec.json` | `orchestrator/schemas.py` | `data/synthetic_amp_states.json` |
|---|---|---|---|
| `required_skills` | ✅ Present in `task_intake` | ✅ `TaskIntake` line 39 | ✅ Populated on all cases |
| `monetary_value` | ✅ Present in `task_intake` | ✅ `TaskIntake` line 40 | ✅ Populated on all cases |

**No action required.** These fields were added before this audit.

---

## 5. Seed Gap

| Item | Status |
|---|---|
| `data/synthetic_amp_states.json` | ✅ Exists — includes `required_skills` and `monetary_value` on all cases |
| `data/init_db.py` | ✅ Exists — initialises infra/state.db + Qdrant (idempotent) |
| `seed_db.py` (root) | ✅ Exists — seeds infra/state.db from synthetic_amp_states.json |
| CSA seed (`CSA/data/csa.db`) | ✅ Auto-seeded on FastAPI startup via `db_schema.init_db()` |

**No action required.** All seed data is present and complete.

---

## 6. Startup Gap

**Verified current state:** `start_agents.sh` already runs DB init + seed before launching agents (lines 84–88).

```bash
log "Initialising data layer (infra/state.db + Qdrant)..."
python data/init_db.py || { log "ERROR: data/init_db.py failed — aborting"; exit 1; }

log "Seeding orchestrator state (infra/state.db)..."
python seed_db.py || { log "ERROR: seed_db.py failed — aborting"; exit 1; }
```

CSA's own DB is auto-initialised at FastAPI startup — no startup script change needed for it.

**No action required.**

---

## Summary

| Area | Gaps Found | Action Required |
|---|---|---|
| CSA schema | None (ref == live) | None |
| CSA seed data | 2 ad-hoc test cases in ref only | Ignore (not canonical) |
| RRA input/output | None against spec | None |
| SWA models | None | None |
| SWA integration | Direct analyze() call skips ingest | Documented AITS point; no change for demo |
| AmpState spec | Already has required_skills + monetary_value | None |
| Seed coverage | Already has required_skills + monetary_value | None |
| Startup script | Already runs init_db + seed_db | None |

**All Phase 0 gaps are resolved. Codebase is ready for Phase 1 data layer consolidation.**
