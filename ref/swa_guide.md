# Shadow Work Agent — Integration Guide (Project AMP)
## Overview

Shadow Work Agent accepts structured case + event data.
No code changes required.

Call existing logging functions
Respect schema + vocabularies
Agent handles validation, storage, analysis
1. Input Contract
Step 1 — Register Case
from agent.logging_tool import ingest_case

ingest_case({
  "case_id": "case_vendor_0042",
  "case_type": "vendor_onboarding",
  "status": "in_progress",
  "created_at": "2026-04-27T09:00:00Z",
  "closed_at": None,
  "domain_metadata": {
    "client_name": "Acme Corp",
    "priority": "high"
  }
})
Case Fields
Field	Required	Notes
case_id	Yes	Unique primary key
case_type	Yes	Free text
status	Yes	open · in_progress · closed
created_at	Yes	ISO 8601 UTC
closed_at	No	Null if open
domain_metadata	No	Any JSON
Step 2 — Send Events
Single Event
from agent.logging_tool import ingest_event

ingest_event({
  "event_id": "evt_unique_abc123",
  "case_id": "case_vendor_0042",
  "timestamp": "2026-04-27T09:15:00Z",
  "actor_id": "context_stitching_agent",
  "actor_type": "agent",
  "action_type": "context_gathered",
  "target_entity": "sys_procurement_queue",
  "target_entity_type": "internal_system",
  "parent_task_id": "task_vendor_0042",
  "context_payload": {"system": "procurement_queue", "records_found": 3},
  "outcome": "success"
}, source_agent='context_stitching_agent')
Batch Events
from agent.logging_tool import ingest_batch

result = ingest_batch([event1, event2], source_agent='integration_layer')
# {'accepted': X, 'rejected': Y}
Event Fields
Field	Required
event_id	Yes
case_id	Yes
timestamp	Yes
actor_id	Yes
actor_type	Yes
action_type	Yes
target_entity	Yes
target_entity_type	Yes
outcome	Yes
parent_task_id	No
context_payload	No
2. Closed Vocabularies
action_type

Automatable

sent_followup
sent_reminder
status_check
requested_document
scheduled_meeting
data_lookup
policy_check

Approval

approved
rejected
escalated_to_human
manual_override
policy_exception_granted

Informational

received_message
logged_note
viewed_document
case_opened
case_closed
task_assigned
context_gathered
risk_flagged
intent_predicted
target_entity_type
external_contact
internal_system
internal_user
task
document
3. Rejections

Silent failures. Nothing crashes. Just disappears.

Cause	Reason
Unknown action_type	not in vocabulary
Unknown target_entity_type	not in vocabulary
Unregistered case_id	case not found
Missing field	schema_violation
Invalid outcome	must be success/pending/failed

Check:

SELECT * FROM ingestion_log
WHERE status='rejected'
ORDER BY timestamp DESC;
4. Full Flow
from agent.logging_tool import ingest_case, ingest_batch
from agent.orchestrator import analyze

# Register case
ingest_case({...})

# Send events
ingest_batch(events, source_agent='integration_layer')

# Analyze
output, meta = analyze(case_id='case_vendor_0042')
# or
output, meta = analyze()
5. Output Structure
{
  "agent": "shadow_work",
  "case_portfolios": [],
  "findings": [],
  "escalations": [],
  "metrics": {},
  "cluster_evolution": {}
}
Key Sections
case_portfolios → timelines, counts
findings → automation recommendations
escalations → human review cases
metrics → stats + detectors
cluster_evolution → global runs only
6. Scaling Behavior
Scale	Output
1 case	WATCH / ESCALATE
10–20 cases	RECOMMEND
50+ cases	ML clusters
200+ cases	Full intelligence
Confidence Formula
confidence =
(size × 0.5) +
(regularity × 0.3) +
(diversity × 0.2)
Low data → low confidence
Cross-case repetition → recommendations
7. Quick Reference
Required Before Events
ingest_case({ case_id, case_type, status, created_at })
Required Per Event
event_id
case_id
timestamp
actor_id
actor_type
action_type
target_entity
target_entity_type
outcome
Optional
parent_task_id
context_payload
Run Analysis
analyze(case_id='case_xxx')
analyze()