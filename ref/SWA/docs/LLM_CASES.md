# LLM Usage Cases — Shadow Work Agent v2

**Purpose:** Per Mudit's question "have you created cases where in this case LLM should do this, in other case it should do that?" — this document enumerates every scenario where the LLM is invoked, what it receives, what it produces, and what happens when it's unavailable.

---

## Design Principle

The LLM is NOT the brain of the agent. Detection, scoring, and escalation decisions are all deterministic Python. The LLM is a **presentation layer** that generates human-readable descriptions. The agent works (with lower quality output) even if the LLM is completely unavailable.

---

## The Four Cases

### CASE A: High-Confidence Recommendation

**When it fires**
- A finding has `decision = "recommend"`
- Confidence ≥ 0.75
- Action type is in the automatable set
- Detector source is a heuristic detector (repetition, temporal, cross-case)

**What the LLM receives**
```json
{
  "action_type": "sent_followup",
  "target_entity_type": "external_contact",
  "occurrences": 4,
  "mean_interval_hours": 48.3,
  "sample_context_payloads": [
    {"doc_type": "plot_layout", "subject": "...", "channel": "email"},
    ...
  ]
}
```

**What the LLM produces**
```json
{
  "description": "Structural description, domain-neutral, one sentence",
  "domain_contextualized_description": "Business-language description using context hints, 1-2 sentences",
  "automation_action": "Concrete automation rule in imperative mood"
}
```

**Why LLM here**
The structural description is useful but generic. The LLM reads the opaque `context_payload` and produces a business-friendly summary like "A procurement associate repeatedly emails a vendor every 48 hours to obtain a plot layout document." That phrasing lands better with clients than raw action type names.

---

### CASE B: Escalation Summary

**When it fires**
- A finding has `decision = "escalate"` OR `decision = "watch"`
- Either confidence is too low to auto-recommend, or the action type is approval-type

**What the LLM receives**
```json
{
  "action_type": "sent_followup",
  "target_entity_type": "external_contact",
  "occurrences": 3,
  "reason_for_escalation": "confidence below threshold — needs human review",
  "sample_context_payloads": [...]
}
```

**What the LLM produces**
```json
{
  "description": "Plain structural description",
  "summary_for_human": "2-3 sentence summary explaining what was observed and what the reviewer should decide",
  "automation_action": "If approved, what automation would we apply"
}
```

**Why LLM here**
Human reviewers don't want to read machine output. The LLM translates "pattern: sent_followup, 3 occurrences, confidence 0.68" into "This claims processor has sent 3 follow-ups in 5 days to obtain a police report. Recommend reviewing whether this is worth automating or if the vendor has a communication problem."

---

### CASE C: Unsupervised Cluster Labeling

**When it fires**
- A finding's `detector_source = "ml:dbscan_clustering"`
- Applies regardless of the finding's decision

**What the LLM receives**
```json
{
  "dominant_action": "status_check",
  "dominant_target_type": "internal_system",
  "cluster_size": 7,
  "n_actors": 1,
  "n_cases": 1,
  "mean_interval_hours": 24.0,
  "sample_context_payloads": [...]
}
```

**What the LLM produces**
```json
{
  "cluster_name": "Daily Approvals Queue Polling",
  "description": "What this cluster represents, one sentence",
  "domain_contextualized_description": "Business description with context",
  "automation_action": "Proposed automation"
}
```

**Why LLM here**
DBSCAN discovers clusters without labels. The LLM names them. Without this step, the output would say "Cluster 0: 7 events, action=status_check" — not useful. With the LLM, it says "Daily Approvals Queue Polling — user_088 manually checks the approvals queue every day at ~2pm."

---

### CASE D: LLM Unavailable (Fallback)

**When it fires**
- No `GEMINI_API_KEY` environment variable set
- API call raises an exception (rate limit, network, etc.)
- API returns malformed response that can't be parsed

**What the LLM receives**
(nothing — LLM not called)

**What the fallback produces**
Template-based descriptions using string interpolation. Example for Case A:
```
description: "sent followup action occurred 4 times against external contact entities, mean interval 48.3h"
domain_contextualized_description: (same as description — no domain enrichment available)
automation_action: "Automate sent followup after 48.3h interval"
```

**Why this exists**
The agent must work even when the LLM is down. In the last client meeting, you hit your Gemini API limit mid-demo. With this fallback, the agent would still have produced recommendations — just less richly worded.

---

## When the LLM is NEVER Invoked

To keep costs and complexity controlled, the LLM is NOT called for:

| Scenario | Reason |
|---|---|
| Event ingestion validation | Deterministic — use closed vocabulary checks |
| Pattern detection | Deterministic — use pandas and DBSCAN |
| Confidence scoring | Deterministic — mathematical formula |
| Deduplication | Deterministic — key-based merging |
| Findings below "watch" threshold | Discarded before enrichment — no point |
| Template fallback cases | LLM is unavailable by definition |
| Case portfolio building | Pure data aggregation — no language needed |

---

## Decision Tree (the dispatcher)

```
enriched_findings = []
for finding in scored_findings:
    if finding.detector_source == "ml:dbscan_clustering":
        → CASE C: enrich_cluster(finding)
    elif finding.decision == "recommend":
        → CASE A: enrich_recommendation(finding)
    else:  # "escalate" or "watch"
        → CASE B: enrich_escalation(finding)
```

If any LLM call fails → CASE D template fallback for that finding.

---

## Rate Limit Strategy

Gemini free tier gives 1,500 requests per day. With the dispatcher above:
- Typical run produces 5-10 findings total
- Each finding makes 1 LLM call
- So typical run costs 5-10 requests

Even running 50 analyses per day = 500 requests, well within the free tier.

---

## Prompt Engineering Notes

Each case has a **different prompt** tuned for its output shape. See `agent/llm_enricher.py` functions:
- `enrich_recommendation()` — Case A prompt
- `enrich_escalation()` — Case B prompt
- `enrich_cluster()` — Case C prompt

All prompts:
- Ask for strict JSON output
- Specify exact field names
- Include "no fencing, no commentary" instruction
- Provide sample context payloads as hints

---

## Testing

To test the dispatcher without burning LLM calls:
1. Unset `GEMINI_API_KEY` in `.env`
2. Run the agent — it will use template fallback for all cases
3. Verify templates produce valid, if less rich, output

All deterministic logic (detection, scoring, decisions) can be unit-tested without the LLM.
