# 2. Shadow Work Agent

## 2.1 Objective

The Shadow Work Agent is responsible for observing the entire multi-agent workflow,
capturing every event into a structured case-portfolio log, and analysing those
events to detect repetitive manual work that can be automated. It acts as a
**workflow intelligence and automation recommendation layer**, surfacing hidden
inefficiencies that no single agent or human reviewer would notice on their own.

---

## 2.2 Problem Statement

Enterprise workflows generate large volumes of repetitive activity — status
checks, follow-ups, document requests, policy validations — performed across
many cases, days, and actors. Individually each action looks routine; collectively
they represent significant manual overhead. Identifying these patterns by hand
requires constant cross-case observation that is not feasible at scale.

The challenge is to design a system that can:

- Observe events emitted by every other agent in the workflow
- Build complete per-case histories (case portfolios)
- Detect structural patterns of repetition without prior domain knowledge
- Track how those patterns evolve as more data flows in
- Distinguish automation-ready behaviours from those still requiring human review

---

## 2.3 Approach and System Design

The Shadow Work Agent follows a two-module pipeline:

### Module 1 — Logging Tool (Ingestion & Storage)

**1. Event Ingestion**
Events emitted by other agents are received through a structured logging
interface using a closed action vocabulary.

**2. Validation**
Each event is validated against a data dictionary that defines allowed
action types, target types, and actor types.

**3. Case-Centric Storage**
Validated events are persisted in a PostgreSQL activity log indexed by
`case_id`, forming an immutable source of truth.

**4. Case Portfolio Building**
Per-case timelines, action counts, actor counts, and duration metrics
are aggregated into reusable case portfolios.

### Module 2 — Analysis Engine (Detection, Scoring & Recommendation)

**5. Normalization**
Domain-blind structural signatures are constructed (action + target type)
so detectors can find patterns without depending on domain-specific names.

**6. Heuristic Detection**
Three deterministic detectors run in parallel:
- Repetition detector — same actor, same action, same target, repeated
- Temporal regularity detector — clockwork-like recurrence
- Cross-case detector — the same pattern spanning multiple cases

**7. Unsupervised ML Detection**
DBSCAN clustering discovers natural groupings of similar events that
no fixed rule could predict. Each cluster is given a **stable fingerprint**
so it can be tracked across runs.

**8. Cluster Snapshot Tracking**
After every run a cluster snapshot is saved and compared against the
previous one. The agent reports new, strengthened, stable, and dissolved
patterns — this is the incremental-learning loop.

**9. Scoring and Decision**
Each finding receives a confidence score, a risk level, and a decision:
`recommend` / `watch` / `escalate`. Findings caught by multiple detectors
are deduplicated and given a corroboration boost.

**10. LLM Enrichment**
A language model (Gemini) generates business-language descriptions and
automation actions through four explicit invocation cases:
high-confidence recommendation, escalation summary, unsupervised cluster
labelling, and a template-based fallback when the LLM is unavailable.

**11. Output Splitting**
Findings with `decision = recommend` are returned as automation
recommendations; the rest are routed to escalations for human review.

---

## 2.4 Input to the Agent

The agent receives structured inputs including:

- **Event records** (event_id, case_id, timestamp, actor, action, target, outcome, context)
- **Case metadata** (case_id, case_type, status, domain_metadata)
- **Action vocabulary** (automatable, approval-type, informational sets)
- **Threshold configuration** (confidence, regularity, repetition minimums)
- **Historical snapshots** (used for incremental comparison across runs)

---

## 2.5 Output of the Agent

The Shadow Work Agent produces structured outputs containing:

- **Automation Recommendations** with aggregate confidence, decision, risk level, and proposed automation rule
- **Escalations** with pattern signature, summary for human review, recommended reviewer role, and supporting evidence
- **Case Portfolios** containing the full timeline and roll-up statistics for each case
- **Cluster Snapshots** capturing the current state of unsupervised clusters with stable fingerprints
- **Cluster Evolution** report showing new, strengthened, stable, and dissolved patterns since the previous run
- **Run Metrics** including patterns detected, recommendations made, escalations raised, processing time, and detectors used

This ensures outputs are **explainable, traceable, and actionable**.

---

## 2.6 Role in Overall System

The Shadow Work Agent functions as an **observation and intelligence layer**
parallel to the execution workflow:

```
Task → Context → IAA → Risk → Governance → Delegation → Execution
                            │
                            ▼
                  Shadow Work Agent
              (logging + analysis layer)
                            │
                            ▼
        Automation Recommendations + Escalations
```

It does not block or gate any action in the chain. Instead, it learns from
what every other agent does and continuously surfaces opportunities to
reduce manual work.

---

## 2.7 Challenges and Improvements

During development, several key challenges were encountered:

- Detecting meaningful patterns without prior domain knowledge
- Distinguishing genuine repetition from coincidental clustering
- Maintaining a stable identity for ML clusters across multiple runs
- Producing recommendations that are both explainable and business-friendly
- Operating uniformly across sparse early data and rich later data

To address these challenges:

- A normaliser produces domain-blind structural signatures so detection logic does not depend on domain-specific entity names
- Stable cluster fingerprints (action :: target :: actor-type :: time-bucket) maintain the same identity across runs even when DBSCAN labels change
- Multi-detector consensus boosts confidence — when several independent detectors find the same pattern, the system becomes measurably more confident
- LLM enrichment with explicit case dispatch produces context-aware, domain-friendly explanations rather than raw structural descriptions
- Confidence and regularity thresholds filter out coincidental clusters that do not represent real automatable behaviour

---

## 2.8 Key Features

- Two-module architecture cleanly separating logging from analysis
- Unsupervised pattern discovery with DBSCAN clustering
- Stable cluster fingerprinting that enables incremental learning across runs
- Multi-detector evidence aggregation (heuristic + ML corroboration)
- Graduated decisioning: `recommend` / `watch` / `escalate`
- Explicit LLM invocation rules for explainable, business-friendly outputs
- Cluster evolution reporting (new / strengthened / stable / dissolved)
- Web UI dashboard with per-case drill-down (domain → case → outcomes, recommendations, escalations, activity log)
- Full audit trail persisted in PostgreSQL

---

## 2.9 Future Enhancements

- **Workflow-shape ML features** — extend the ML feature space beyond action and timing to include case morphology (actor diversity, failure ratio, agent-vs-human composition) so the model discovers patterns the heuristic detectors cannot
- **Co-occurrence and sequence detection** — identify action sequences (e.g. *every status check is followed by a follow-up within 2 hours*) rather than only isolated repetitions
- **Higher-resolution confidence scoring** — recalibrate the scoring formula so confidence values are meaningfully spread across the 0–1 range
- **Real-time streaming ingestion** — move from periodic batch sweeps to continuous event processing
- **Per-domain confidence calibration** — apply domain-specific thresholds where one universal threshold under-serves certain workflows
- **Automation deployment integration** — pass approved recommendations directly into automation runtimes, closing the loop from observation to execution
- **Regression detection** — alert when previously stable patterns degrade or dissolve, indicating workflow drift or unintended changes
