# AITS → AMP Integration Point

## Trigger Flow

AITS triages an incoming event and POSTs to the AMP orchestrator:

```
POST http://<amp-host>:8000/run
Content-Type: application/json
```

```json
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
```

## What happens next

```
Orchestrator → CSA (fetches case context from csa.db)
            → [RRA, IAA, GPA] in parallel (Stage 2)
            → DA (assigns task owner)
            → Returns AmpState JSON
```

## Response

AmpState JSON — see `data/AmpState_spec.json` for full schema.

## Demo simulation

The Streamlit dashboard simulates AITS by posting pre-loaded case payloads
via the "Run Workflow" button. No AITS connection needed for demo.
