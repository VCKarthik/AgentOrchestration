Risk Radar Agent — Integration Spec

Project AMP | Phase 1 | Sprint 5–6

Pipeline
Context Stitching Agent (CSA)
        ↓
Risk Radar Agent
        ↓
Orchestrator / Human Reviewer
Overview
Consumes raw CSA output
Parses autonomously
Applies 5 deterministic rules
Emits actionable verdict
No human input required
Input — CSA Packet
Top-Level Fields
Field	Type	Required	Description
task_id	string	Yes	CSA run ID
case_id	string	Yes	Business case ID
case_type	string	Yes	Workflow category
timestamp	ISO8601	Yes	Packet creation time
context	object	Yes	emails, documents, calendar_events, case_history
validation	object	No	status, confidence_score, warnings[]
meta	object	No	Retrieval metadata
case_type → workflow_type
case_type	workflow_type	Mandatory Documents
claim_review	insurance_claim	claim_form, incident_report, policy_document
vendor_review	vendor_onboarding	tax_form, compliance_certificate, bank_details
contract_review	contract_review	draft_contract, legal_sign_off, counterparty_id
payment_review	payment_approval	invoice, purchase_order, approver_sign_off
kyc_review	customer_kyc	id_proof, address_proof, pep_screening_result, sanctions_check
loan_review	loan_approval	credit_report, income_verification, loan_application, id_proof
onboarding_review	employee_onboarding	offer_letter, id_verification, background_check, tax_withholding_form
filing_review	regulatory_filing	filing_form, legal_review_sign_off, compliance_attestation
context.documents
Filename normalized
IDs, versions, extensions removed
Keyword overlap → document type match
No manual tagging
Field	Type
id	string
filename	string
file_type	string
context.case_history → Derived Signals
event_type	Signal
delayed	+prior_delay_count
escalated	+prior_escalation_count
status=blocked	dependency_status=blocked, blocker_flag=true
status=approved/complete	dependency_status=clear
Sample Input
{
  "task_id": "CSA-20260421-F8AE4D",
  "case_id": "CASE-1001",
  "case_type": "claim_review",
  "timestamp": "2026-04-21T17:00:34Z",
  "context": {
    "documents": [
      {"id": "D001", "filename": "policy_4821.pdf", "file_type": "pdf"},
      {"id": "D002", "filename": "claim_form_4821.pdf", "file_type": "pdf"}
    ],
    "calendar_events": [
      {"title": "Review", "end_time": "2026-05-18 11:00:00", "status": "confirmed"}
    ],
    "case_history": [
      {"event_type": "created", "status": "pending"},
      {"event_type": "delayed", "status": "pending"}
    ]
  },
  "validation": {
    "status": "COMPLETE",
    "confidence_score": 1.0
  }
}
Risk Rules (Deterministic)
1. Missing Input
Missing mandatory → HIGH (blocking)
Missing + policy_flag → CRITICAL (blocking)
Missing optional → MEDIUM (non-blocking)
2. Deadline / SLA
Breached → CRITICAL
<6h → HIGH
6–24h → MEDIUM
24–72h → LOW
3. Dependency
blocked + blocker_flag → CRITICAL
blocked → HIGH
at_risk → MEDIUM
pending → HIGH
4. Historical Delay
≥5 delays OR (≥3 delays + ≥1 escalation) → HIGH
≥3 delays OR ≥2 escalations → MEDIUM
else → LOW
Never blocking
5. Compliance
policy_flag + regulatory context → CRITICAL (blocking)
prior escalations → HIGH
flag only → MEDIUM
Output — RiskRadarOutput
Top-Level Fields
Field	Type	Values
task_id	string	echo
workflow_state	string	intake, compliance_review, approval, payment, closed
priority	string	P1, P2, P3
overall_risk_level	enum	low, medium, high, critical
can_proceed	enum	proceed, caution, hold
escalate_to_human	boolean	true/false
escalation_target	string/null	reviewer role
risk_items	array	list of risks
reasoning_summary	string	explanation
operating_context	enum	full, partial
model_used	string	rules-only / rules-plus-llm-summary
timestamp	ISO8601	output time
risk_items[]
Field	Type
risk_type	enum
severity	enum
reason	string
blocking	boolean
risk_type Values
missing_input
deadline_risk
dependency_risk
historical_delay
compliance_risk
Decision Matrix
Condition	can_proceed	escalate
No risks	proceed	false
LOW/MEDIUM only	caution	false
Any HIGH	caution / hold	true
Any CRITICAL or blocking	hold	true
Sample Output
{
  "task_id": "CASE-1001",
  "workflow_state": "compliance_review",
  "priority": "P2",
  "overall_risk_level": "critical",
  "can_proceed": "hold",
  "escalate_to_human": true,
  "escalation_target": "compliance_reviewer",
  "risk_items": [
    {
      "risk_type": "missing_input",
      "severity": "critical",
      "reason": "Missing mandatory: ['incident_report']",
      "blocking": true
    }
  ],
  "reasoning_summary": "HOLD — mandatory inputs missing",
  "operating_context": "full",
  "model_used": "rules-only",
  "timestamp": "2026-04-28T09:00:00Z"
}
Notes
No null fields
Partial input → operating_context = partial
Deterministic scoring only
LLM optional for summaries only