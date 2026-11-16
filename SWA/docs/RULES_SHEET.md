# Rules Sheet — Shadow Work Agent v2

**Purpose:** Per Ankit's request — a human-readable document showing what the agent looks at and what it does next. This is the decision logic in plain English, not code.

---

## Rule Set 1: Event Ingestion (Module 1 — Logging Tool)

When an event arrives from any agent, the logging tool applies these rules in order:

**Rule 1.1 — Schema Check**
IF the payload does not match the expected shape (missing required fields, wrong types)
THEN reject the event, log the rejection reason in `ingestion_log`, return False.

**Rule 1.2 — Action Type Validation**
IF `action_type` is not in the closed vocabulary defined in `settings.py`
THEN reject with reason `"unknown_action_type"` and log it.

**Rule 1.3 — Target Type Validation**
IF `target_entity_type` is not in the closed vocabulary
THEN reject with reason `"unknown_target_type"` and log it.

**Rule 1.4 — Case Registration Check**
Accept only if the referenced `case_id` exists in the `cases` table.
(Other agents must register a case before writing events against it.)

**Rule 1.5 — Acceptance**
IF all validations pass
THEN insert the event into `activity_log`, log the acceptance, return True.

**Rule 1.6 — Always Log the Attempt**
Every ingestion attempt (accepted or rejected) writes a row to `ingestion_log`. We never lose track of what was tried.

---

## Rule Set 2: Case Portfolio Building

For every case in the system, we build a portfolio summarizing its history:

**Rule 2.1 — Portfolio Scope**
Pull all events for the case across its entire lifetime (not just the analysis window).

**Rule 2.2 — Timeline Construction**
Sort events chronologically. Each entry becomes one line in the case timeline showing: timestamp, actor, action, target, outcome.

**Rule 2.3 — Counters**
Compute: total events, distinct actors, distinct actions, case duration (last event - first event).

**Rule 2.4 — Per-Action Counts**
Count how many times each `action_type` occurred in the case.

**Rule 2.5 — Persistence**
Save the portfolio to `case_portfolios` table. Update timestamp = now.

---

## Rule Set 3: Pattern Detection (Module 2 — Analysis Engine)

Three heuristic detectors plus one ML detector run on the event stream. Each produces raw findings.

### Heuristic Detector 1: Repetition

**Rule 3.1** — Group events by `(actor_id, action_type, target_entity)`.
**Rule 3.2** — For each group with count ≥ `MIN_REPETITION_THRESHOLD` (default: 3), emit a finding.
**Rule 3.3** — Pattern type: `repeated_action_same_target`.

### Heuristic Detector 2: Temporal Regularity

**Rule 3.4** — For each repeating group from Rule 3.1, compute interval statistics.
**Rule 3.5** — Regularity score = 1 - (stddev / mean). Clipped to [0, 1].
**Rule 3.6** — If count ≥ threshold AND regularity ≥ `MIN_REGULARITY_SCORE` (default: 0.7), emit a finding.
**Rule 3.7** — Pattern type: `scheduled_recurring_action`.

### Heuristic Detector 3: Cross-Case

**Rule 3.8** — Group events by `(action_type, target_entity_type)` across cases.
**Rule 3.9** — Emit finding only if pattern spans ≥ 2 distinct cases AND ≥ 2 distinct targets AND count ≥ threshold.
**Rule 3.10** — Compute per-actor intervals (not global average) to avoid misleading stats.
**Rule 3.11** — Pattern type: `recurring_cross_case_action`.

### ML Detector: DBSCAN Clustering

**Rule 3.12** — Featurize every event into a vector: one-hot action_type, one-hot target_type, hour_of_day, day_of_week.
**Rule 3.13** — Standardize features using z-score normalization.
**Rule 3.14** — Run DBSCAN with `eps=0.5`, `min_samples=3` (configurable).
**Rule 3.15** — For each cluster (excluding noise cluster -1), if size ≥ threshold, emit a finding.
**Rule 3.16** — Pattern type: `unsupervised_discovered_cluster`.

---

## Rule Set 4: Scoring

For each raw finding, compute confidence, risk, and decision:

**Rule 4.1 — Sample Size Factor**
`factor = min(0.95, 1.0 - exp(-n / 6.0))` where n = occurrences.

**Rule 4.2 — Case Diversity Factor**
1.0 if ≥3 cases, 0.85 if 2 cases, 0.7 if 1 case.

**Rule 4.3 — Confidence**
`confidence = size_factor * 0.5 + regularity * 0.3 + diversity_factor * 0.2`

**Rule 4.4 — ML Cluster Regularity**
ML-detected clusters get a baseline regularity of 0.75 (they clustered, so they're similar by definition).

**Rule 4.5 — Risk Level**
- `action_type` is in approval set → HIGH risk
- `≥3 distinct actors` involved → MEDIUM risk (may be process issue, not automation opp)
- Otherwise → LOW risk

**Rule 4.6 — Decision Matrix**
- Approval-type action → ESCALATE (always, regardless of confidence)
- Confidence ≥ 0.75 AND action is automatable → RECOMMEND
- Confidence ≥ 0.50 → WATCH (continue monitoring)
- Below 0.50 → ESCALATE (not enough evidence)

---

## Rule Set 5: Deduplication

**Rule 5.1 — Dedup Key**
`(action_type, target_entity, sorted(actors_involved))`

**Rule 5.2 — Merge Strategy**
When multiple findings share the same key, keep the one with highest confidence. Record all detector sources.

**Rule 5.3 — Why This Matters (fix from v1)**
In v1, the same pattern often appeared twice: once from the repetition detector, once from temporal regularity. Dedup eliminates this.

---

## Rule Set 6: LLM Dispatch

The LLM is invoked in four explicit cases, and never elsewhere. See `docs/LLM_CASES.md` for full details. Summary:

| Case | When | What LLM Produces |
|---|---|---|
| A | Decision = recommend | Domain-aware recommendation description |
| B | Decision = escalate or watch | Human-readable escalation summary |
| C | Detector source = ML cluster | Natural-language cluster label |
| D | LLM unavailable | (none — template fallback) |

---

## Rule Set 7: Output & Persistence

**Rule 7.1** — Split enriched findings: `decision=recommend` becomes recommendations; `decision=watch` or `decision=escalate` becomes escalations.

**Rule 7.2** — Serialize as Pydantic `AgentOutput` model for type safety.

**Rule 7.3** — Write output JSON to `output/<run_id>.json`.

**Rule 7.4** — Persist full run to `analysis_runs` table for audit trail.

---

## Rule Set 8: Scoping (per Ankit's case-level request)

**Rule 8.1 — Global Scope**
`python -m agent.orchestrator` → analyze all events in the time window.

**Rule 8.2 — Case-Scoped**
`python -m agent.orchestrator --case_id <id>` → analyze only events for that one case.

**Rule 8.3 — Per-Case Sweep**
`python -m agent.orchestrator --all-cases` → run analysis once per case and produce per-case outputs.

---

## Why Each Rule Exists (Rationale Summary)

| Rule Category | Reason |
|---|---|
| Ingestion validation | Bad data corrupts analysis. Reject at the door. |
| Closed vocabulary | Consistent terminology across agents makes patterns detectable. |
| Case portfolio | Per Ankit: every case has a history; our agent's basic unit is the case. |
| Heuristic detectors | Fast, explainable, deterministic. No ML surprise. |
| ML detector | Per Ankit: unsupervised discovery of patterns we didn't think to code. |
| Scoring | Quantitative confidence means recommendations are measurable, not gut feel. |
| Deduplication | Prevents duplicate noise in the output. |
| LLM dispatch | Per Mudit: explicit cases mean we know exactly when LLM fires and why. |
| Case scoping | Per Ankit: analyst often wants to drill into ONE case, not the whole system. |
