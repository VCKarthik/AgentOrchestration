"""
generate_synthetic_cases.py
Generates 50 complete AmpState JSON cases for Project AMP.

Distribution:
  20 vendor_onboarding  (8 happy, 7 partial, 5 escalation)
  15 claim_review       (6 happy, 5 partial, 4 escalation)
  15 fraud_investigation(6 happy, 6 partial, 5 escalation  — fraud skews high-risk)
  Total happy=20, partial=17, escalation=13  ≈ 40/34/26% — within spec

Closed vocabularies used:
  ALL_ACTION_TYPES   — SWA/config/settings.py
  TaskType           — DA/delegation_agent/models/task.py
  RiskType           — RRA/schema.py
  Priority           — DA/delegation_agent/models/task.py
  AssignmentStatus   — DA/delegation_agent/models/outputs.py

Usage:
  python data/generate_synthetic_cases.py
  python data/generate_synthetic_cases.py --out data/synthetic_amp_states.json
"""
from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ── Closed vocabularies (copied from source-of-truth files) ──────────────────
# SWA/config/settings.py → Settings.ALL_ACTION_TYPES
ALL_ACTION_TYPES = {
    # AUTOMATABLE
    "sent_followup", "sent_reminder", "status_check",
    "requested_document", "scheduled_meeting",
    # APPROVAL
    "approved", "rejected", "escalated_to_human",
    "manual_override", "policy_exception_granted",
    # INFORMATIONAL
    "received_message", "logged_note", "viewed_document",
    "case_opened", "case_closed",
}
ALL_ACTION_TYPES_LIST = sorted(ALL_ACTION_TYPES)

# DA/delegation_agent/models/task.py → TaskType
TASK_TYPES = [
    "claim_review", "customer_inquiry", "technical_support",
    "vendor_onboarding", "compliance_review", "financial_approval", "general",
]

# RRA/schema.py → RiskType
RISK_TYPES = [
    "missing_input", "deadline_risk", "dependency_risk",
    "compliance_risk", "historical_delay", "coordination_risk", "ambiguity_risk",
]

# DA/delegation_agent/models/task.py → Priority
PRIORITIES = ["critical", "high", "medium", "low"]

# DA/delegation_agent/models/outputs.py → AssignmentStatus
ASSIGNMENT_STATUSES = ["assigned", "escalated", "unassigned", "review_required"]

# DA/delegation_agent/models/outputs.py → ExecutionChannel
CHANNELS = ["human_owner", "specialized_agent", "automation", "supervisor_review", "manual_triage"]

# IAA/agent/schemas.py → action_id labels used by IAA
IAA_ACTION_IDS = [
    "request_missing_document", "schedule_review_meeting", "escalate_to_human",
    "send_status_update", "assign_to_specialist", "initiate_compliance_check",
    "flag_for_fraud_review", "approve_and_forward", "request_additional_info",
    "escalate_for_review",
]

RNG = random.Random(42)  # fixed seed for reproducibility


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now(offset_days: int = 0) -> str:
    dt = datetime(2026, 4, 23, 12, 0, 0, tzinfo=timezone.utc) + timedelta(days=offset_days)
    return dt.isoformat().replace("+00:00", "Z")


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.UUID(int=RNG.getrandbits(128)).hex[:8].upper()}"


def _pick(*choices):
    return RNG.choice(list(choices) if len(choices) == 1 and hasattr(choices[0], '__iter__')
                      else choices)


def _case_history_events(case_id: str, case_type: str, difficulty: str, n: int = 4) -> list[dict]:
    """Return case_history records using only ALL_ACTION_TYPES values for event_type."""
    informational = ["case_opened", "logged_note", "viewed_document", "received_message"]
    automatable = ["sent_followup", "sent_reminder", "status_check", "requested_document"]
    approval = ["approved", "rejected", "escalated_to_human"]

    events = []
    # Always start with case_opened
    events.append({
        "id": _uid("EVT-"),
        "case_id": case_id,
        "case_type": case_type,
        "event_type": "case_opened",
        "actor": "user_intake",
        "timestamp": _now(-14),
        "notes": f"Case opened for {case_type.replace('_', ' ')}",
        "status": "open",
    })

    pool = automatable + informational
    if difficulty == "escalation":
        pool = approval + automatable
    elif difficulty == "partial":
        pool = automatable + informational

    for i in range(1, n):
        events.append({
            "id": _uid("EVT-"),
            "case_id": case_id,
            "case_type": case_type,
            "event_type": RNG.choice(pool),
            "actor": RNG.choice(["user_042", "user_088", "user_055", "system"]),
            "timestamp": _now(-14 + i * 3),
            "notes": f"Step {i} activity",
            "status": "pending" if difficulty != "happy" else "open",
        })

    return events


# ── Per-section generators ────────────────────────────────────────────────────

def generate_case_id(case_type: str, index: int) -> str:
    prefix = {"vendor_onboarding": "VO", "claim_review": "CL", "fraud_investigation": "FR"}.get(
        case_type, "GN"
    )
    return f"CASE-{prefix}-{index:04d}"


def generate_task_intake(case_type: str, difficulty: str, index: int) -> dict:
    task_type_map = {
        "vendor_onboarding": "vendor_onboarding",
        "claim_review":      "claim_review",
        "fraud_investigation": "compliance_review",
    }
    priority_map = {"happy": "medium", "partial": "high", "escalation": "critical"}
    urgency_map  = {"happy": "moderate", "partial": "urgent", "escalation": "immediate"}

    case_id = generate_case_id(case_type, index)
    domain_map = {
        "vendor_onboarding":  "procurement",
        "claim_review":       "claims",
        "fraud_investigation":"fraud_ops",
    }

    return {
        "task_id":          f"T-{case_id}",
        "case_id":          case_id,
        "case_type":        case_type,
        "task_type":        task_type_map.get(case_type, "general"),
        "title":            f"{case_type.replace('_', ' ').title()} — Case {index}",
        "description":      f"Automated intake for {case_type} case {case_id}. Difficulty: {difficulty}.",
        "requester":        RNG.choice(["alice.wang", "john.doe", "priya.patel", "mike.chen"]),
        "requester_role":   RNG.choice(["senior_analyst", "case_manager", "compliance_officer"]),
        "priority":         priority_map[difficulty],
        "urgency":          urgency_map[difficulty],
        "estimated_effort": RNG.choice([1.5, 2.0, 3.0, 4.0, 8.0]),
        "due_date":         _now(7 if difficulty == "happy" else 2 if difficulty == "partial" else 1),
        "business_domain":  domain_map.get(case_type, "general"),
        "timestamp":        _now(-15),
    }


def generate_csa_output(task_intake: dict, difficulty: str) -> dict:
    case_id   = task_intake["case_id"]
    case_type = task_intake["case_type"]

    history = _case_history_events(case_id, case_type, difficulty)

    n_docs   = 0 if difficulty == "partial" else 2
    n_emails = 1 if difficulty == "escalation" else 2
    missing  = ["documents"] if difficulty == "partial" else []

    confidence = (
        RNG.uniform(0.75, 0.99) if difficulty == "happy"
        else RNG.uniform(0.45, 0.70) if difficulty == "partial"
        else RNG.uniform(0.55, 0.80)
    )
    confidence = round(confidence, 2)
    total = n_docs + n_emails + len(history) + 1  # +1 calendar

    emails = [
        {
            "id": _uid("E"),
            "case_id": case_id, "case_type": case_type,
            "subject": f"Re: {case_type.replace('_', ' ').title()} — action required",
            "sender": "agent@system.internal",
            "recipients": f"{task_intake['requester']}@corp.com",
            "date": _now(-10),
            "body": "Please review the attached documentation and confirm next steps.",
            "attachments": ["summary.pdf"] if n_docs > 0 else [],
            "thread_id": _uid("THREAD-"),
            "file_path": None, "file_link": None,
        }
        for _ in range(n_emails)
    ]

    documents = [
        {
            "id": _uid("D"),
            "case_id": case_id, "case_type": case_type,
            "filename": f"policy_{i+1}.pdf", "file_type": "pdf",
            "description": f"Supporting document {i+1}",
            "tags": ["policy", case_type],
            "created_at": _now(-12),
            "file_path": f"/data/files/{case_id}/doc{i+1}.pdf",
            "file_link": f"file:///data/files/{case_id}/doc{i+1}.pdf",
        }
        for i in range(n_docs)
    ]

    calendar_events = [
        {
            "id": _uid("CAL-"),
            "case_id": case_id, "case_type": case_type,
            "title": "Review meeting",
            "start_time": _now(3),
            "end_time":   _now(3),
            "attendees":  [task_intake["requester"], "reviewer@corp.com"],
            "location":   "Virtual",
            "description": "Scheduled case review",
            "status":     "confirmed",
        }
    ]

    warnings = [f"No documents found for this case."] if "documents" in missing else []

    return {
        "task_id":   f"CSA-{_uid()}",
        "task_text": task_intake["title"],
        "case_id":   case_id,
        "case_type": case_type,
        "timestamp": _now(-14),
        "context": {
            "emails":          emails,
            "documents":       documents,
            "calendar_events": calendar_events,
            "case_history":    history,
        },
        "validation": {
            "status":           "PARTIAL" if missing else "COMPLETE",
            "missing_fields":   missing,
            "warnings":         warnings,
            "confidence_score": confidence,
            "total_sources":    total,
        },
        "meta": {
            "total_sources":    total,
            "sql_hits":         total,
            "qdrant_hits":      0,
            "keywords_used":    [case_type, task_intake["requester"]],
            "retrieval_method": "exact_match_sql",
            "csa_version":      "2.0.0",
        },
    }


def generate_rra_output(task_intake: dict, csa_output: dict, difficulty: str) -> dict:
    risk_map = {
        "happy":     [],
        "partial":   [RNG.choice(["missing_input", "deadline_risk"])],
        "escalation": RNG.sample(["missing_input", "compliance_risk", "deadline_risk", "historical_delay"], 2),
    }
    risk_items = risk_map[difficulty]
    risk_flags = risk_items  # shim: [i.risk_type.value for i in rra_output.risk_items]

    severity_map   = {"happy": "low", "partial": "medium", "escalation": "high"}
    can_proceed_map = {"happy": "proceed", "partial": "caution", "escalation": "hold"}
    escalate       = difficulty == "escalation"

    return {
        "task_id":            task_intake["task_id"],
        "workflow_state":     "in_review",
        "priority":           task_intake["priority"],
        "risk_flags":         risk_flags,
        "overall_risk_level": severity_map[difficulty],
        "can_proceed":        can_proceed_map[difficulty],
        "escalate_to_human":  escalate,
        "escalation_target":  "senior_risk_officer" if escalate else None,
        "reasoning_summary":  (
            "No significant risks detected. Case may proceed."
            if difficulty == "happy"
            else f"Risk flags: {', '.join(risk_flags)}. Proceed with caution."
            if difficulty == "partial"
            else f"High-risk flags detected: {', '.join(risk_flags)}. Human review required."
        ),
        "operating_context":  "full" if csa_output["validation"]["status"] == "COMPLETE" else "partial",
        "model_used":         "rules-plus-llm-summary",
        "timestamp":          _now(),
    }


def generate_gpa_output(task_intake: dict, rra_output: dict) -> dict:
    requires = rra_output["escalate_to_human"] or task_intake["priority"] == "critical"
    return {
        "task_id":           task_intake["task_id"],
        "decision":          "ESCALATE" if requires else "APPROVE",
        "reason":            (
            "Policy threshold exceeded — escalation required."
            if requires
            else "All policy checks passed."
        ),
        "confidence":        0.9 if requires else 0.75,
        "requires_approval": requires,
        "next_agent":        "human_review_agent" if requires else "delegation_agent",
        "matched_rule_ids":  [1, 4] if requires else [2],
        "matched_chunk_ids": [10, 22] if requires else [5],
        "approvers":         ["compliance_director"] if requires else [],
    }


def generate_iaa_output(task_intake: dict, rra_output: dict, difficulty: str) -> dict:
    action_id  = (
        "escalate_to_human"         if difficulty == "escalation"
        else "request_missing_document" if difficulty == "partial"
        else RNG.choice(["approve_and_forward", "assign_to_specialist", "schedule_review_meeting"])
    )
    confidence = (
        RNG.uniform(0.80, 0.99) if difficulty == "happy"
        else RNG.uniform(0.50, 0.74) if difficulty == "partial"
        else 0.99
    )
    confidence = round(confidence, 2)
    escalate   = difficulty == "escalation" or confidence < 0.45

    label_map = {
        "escalate_to_human":          "Escalate to human reviewer",
        "request_missing_document":   "Request missing document",
        "approve_and_forward":        "Approve and forward to delegation",
        "assign_to_specialist":       "Assign to domain specialist",
        "schedule_review_meeting":    "Schedule review meeting",
    }
    label = label_map.get(action_id, action_id.replace("_", " ").title())

    task_id_iaa = f"T{RNG.randint(1,9):03d}"
    task_list = [
        {
            "task_id":       task_id_iaa,
            "action":        action_id,
            "assigned_role": RNG.choice(["senior_analyst", "compliance_officer", "case_manager"]),
            "priority":      task_intake["priority"],
            "depends_on":    [],
            "reasoning":     f"Recommended based on {rra_output['overall_risk_level']} risk level.",
        }
    ]

    return {
        "predicted_actions": [
            {"action_id": action_id, "label": label, "confidence": confidence,
             "reasoning": f"Primary recommendation for {task_intake['case_type']}."},
        ],
        "recommended_action": {
            "action_id": action_id, "label": label, "confidence": confidence,
            "reasoning": f"Highest confidence action for current state.",
        },
        "override_applied":      difficulty == "escalation",
        "override_reason":       "Rule 'high_risk_escalation' fired." if difficulty == "escalation" else None,
        "retrieved_context_ids": [_uid("CTX-") for _ in range(3)],
        "escalate_to_human":     escalate,
        "operating_context":     rra_output["operating_context"],
        "model_used":            "gemini/gemini-2.5-flash",
        "timestamp":             _now(),
        "task_list":             task_list,
        "workflow_timeline": [
            {"step": 1, "event_type": "case_opened",    "actor": "intake_system", "status": "completed", "timestamp": _now(-14)},
            {"step": 2, "event_type": "context_stitched","actor": "csa",           "status": "completed", "timestamp": _now(-14)},
            {"step": 3, "event_type": "risk_assessed",  "actor": "rra",           "status": "completed", "timestamp": _now()},
            {"step": 4, "event_type": action_id,        "actor": None,            "status": "predicted", "timestamp": None},
        ],
    }


def generate_da_output(task_intake: dict, iaa_output: dict, gpa_output: dict) -> dict:
    escalate = gpa_output["requires_approval"] or iaa_output["escalate_to_human"]
    status   = "escalated" if escalate else "assigned"
    channel  = "supervisor_review" if escalate else RNG.choice(["human_owner", "specialized_agent"])
    assignee = {
        "assignee_id":  _uid("USR-"),
        "name":         RNG.choice(["Sarah Chen", "James Okafor", "Priya Nair", "Tom Eriksson"]),
        "role":         RNG.choice(["senior_analyst", "specialist", "case_manager"]),
        "department":   task_intake["business_domain"],
    }

    return {
        "assignment_id":       f"ASN-{_uid()}",
        "task_id":             task_intake["task_id"],
        "status":              status,
        "assignment_reason":   "supervisor_review" if escalate else "skill_match",
        "confidence_score":    round(RNG.uniform(60, 95), 1),
        "reasons":             [
            f"Domain match: {task_intake['business_domain']}",
            "Skill alignment confirmed.",
        ] + (["Escalation policy triggered."] if escalate else []),
        "selected_channel":    channel,
        "selected_owner_type": "human",
        "selected_owner":      assignee,
        "selected_assignee":   assignee,
        "candidate_rankings":  [
            {
                "assignee_id":             assignee["assignee_id"],
                "name":                    assignee["name"],
                "role":                    assignee["role"],
                "skill_match_score":       round(RNG.uniform(0.7, 0.99), 2),
                "domain_match_score":      round(RNG.uniform(0.7, 0.99), 2),
                "capacity_score":          round(RNG.uniform(0.5, 0.99), 2),
                "priority_handling_score": round(RNG.uniform(0.6, 0.99), 2),
                "recommendation_boost":    0.0,
                "composite_score":         round(RNG.uniform(70, 95), 1),
                "utilization_percent":     round(RNG.uniform(30, 75), 1),
                "availability_status":     "available",
                "seniority":               "senior",
                "hard_rule_passed":        True,
                "disqualification_reason": None,
            }
        ],
        "decision_factors": {
            "skill_match_score":              round(RNG.uniform(0.7, 0.99), 2),
            "prior_case_ownership":           False,
            "current_utilization":            round(RNG.uniform(0.3, 0.7), 2),
            "availability_status":            "available",
            "domain_match":                   True,
            "sla_at_risk":                    task_intake["urgency"] == "immediate",
            "priority_override_applied":      False,
            "recommended_candidate_boosted":  False,
        },
        "escalation_required": escalate,
        "escalation_reason":   "Human review required by policy." if escalate else None,
        "escalation_urgency":  task_intake["urgency"] if escalate else None,
        "audit_log_id":        f"AUD-{_uid()}",
        "timestamp":           _now(),
        "expected_completion": _now(1),
        "orchestrator_action": "route_to_supervisor" if escalate else "assign_and_notify",
    }


def generate_swa_output(csa_output: dict, difficulty: str) -> dict:
    run_id    = f"sw_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{_uid()[:4].lower()}"
    case_id   = csa_output["case_id"]
    n_history = len(csa_output["context"]["case_history"])

    findings = []
    escalations = []

    if difficulty in ("partial", "escalation"):
        action = RNG.choice(["sent_followup", "status_check", "requested_document"])
        finding = {
            "finding_id":       f"{run_id}_f_000",
            "detector_source":  "heuristic:repetition",
            "pattern_type":     "recurring_manual_action",
            "pattern_signature": f"action:{action} → target_type:external_contact",
            "occurrences":      RNG.randint(3, 7),
            "actors_involved":  ["user_042"],
            "cases_involved":   [case_id],
            "temporal_signature": {
                "mean_interval_hours":   round(RNG.uniform(24, 72), 1),
                "stddev_interval_hours": round(RNG.uniform(0.5, 3.0), 2),
                "regularity_score":      round(RNG.uniform(0.6, 0.95), 2),
            },
            "description":      f"{action} repeated {RNG.randint(3,7)} times — candidate for automation.",
            "domain_contextualized_description": None,
            "automation_recommendation": {
                "type":    "scheduled_automation_rule",
                "trigger": "after 48h with no resolution",
                "action":  f"Automate {action}",
                "estimated_time_saved_per_week_hours": round(RNG.uniform(1.5, 4.0), 1),
            },
            "confidence":             round(RNG.uniform(0.70, 0.92), 2),
            "risk_level":             "medium" if difficulty == "partial" else "high",
            "decision":               "recommend" if difficulty == "partial" else "escalate",
            "requires_human_approval": difficulty == "escalation",
            "evidence_event_ids":     [e["id"] for e in csa_output["context"]["case_history"][:3]],
        }
        if difficulty == "escalation":
            escalations.append({
                "escalation_id":         f"sw_e_{_uid()[:8].lower()}",
                "reason":                "High-confidence anomaly pattern — human review required.",
                "pattern_signature":     finding["pattern_signature"],
                "occurrences":           finding["occurrences"],
                "recommended_human_role": "operations_coordinator",
                "summary_for_human":     f"Pattern '{action}' repeated {finding['occurrences']} times. Review recommended.",
                "evidence_event_ids":    finding["evidence_event_ids"],
            })
        else:
            findings.append(finding)

    window_start = _now(-30)
    window_end   = _now()
    return {
        "run_id":               run_id,
        "findings":             findings,
        "escalations":          escalations,
        "escalation_surfaced":  len(escalations) > 0,
        "summary_sent":         len(findings) > 0,
        "window_analyzed": {
            "start":            window_start,
            "end":              window_end,
            "events_processed": n_history,
        },
        "metrics": {
            "patterns_detected":    len(findings) + len(escalations),
            "recommendations_made": len(findings),
            "escalations_raised":   len(escalations),
            "events_processed":     n_history,
            "processing_time_ms":   round(RNG.uniform(80, 350), 1),
            "detectors_used":       ["heuristic:repetition", "heuristic:temporal_regularity"],
        },
        "timestamp": _now(),
    }


def compute_meta(
    task_intake: dict,
    rra_output: dict,
    iaa_output: dict,
    gpa_output: dict,
    da_output:  dict,
    difficulty: str,
) -> dict:
    # D5: operating_context
    operating_context = (
        "partial"
        if "partial" in rra_output["operating_context"] or "partial" in iaa_output["operating_context"]
        else "full"
    )

    # D7: requires_escalation
    requires_escalation = any([
        rra_output["escalate_to_human"],
        gpa_output["requires_approval"],
        iaa_output["escalate_to_human"],
        da_output["escalation_required"],
    ])

    stage_errors: dict = {}
    if difficulty == "partial":
        stage_errors["swa_validation"] = []
        stage_errors["da_merge"] = ["task_intake.estimated_effort defaulted to 1.0 (example)"] if difficulty == "partial" else []
        # Remove empty lists
        stage_errors = {k: v for k, v in stage_errors.items() if v}

    return {
        "amp_version":        "1.0.0",
        "run_id":             f"AMP-RUN-{_uid()}",
        "timestamp":          _now(),
        "operating_context":  operating_context,
        "requires_escalation": requires_escalation,
        "stage_errors":       stage_errors,
    }


def generate_amp_state(case_type: str, difficulty: str, index: int) -> dict:
    task_intake     = generate_task_intake(case_type, difficulty, index)
    csa_output      = generate_csa_output(task_intake, difficulty)
    rra_output      = generate_rra_output(task_intake, csa_output, difficulty)
    gpa_output      = generate_gpa_output(task_intake, rra_output)
    iaa_output      = generate_iaa_output(task_intake, rra_output, difficulty)
    da_output       = generate_da_output(task_intake, iaa_output, gpa_output)
    swa_output      = generate_swa_output(csa_output, difficulty)
    meta            = compute_meta(task_intake, rra_output, iaa_output, gpa_output, da_output, difficulty)

    return {
        "task_intake":      task_intake,
        "csa_output":       csa_output,
        "risk_output":      rra_output,
        "governance_output": gpa_output,
        "iaa_output":       iaa_output,
        "da_output":        da_output,
        "swa_output":       swa_output,
        "meta":             meta,
    }


def generate_all_cases() -> list[dict]:
    """Generate 50 AmpState cases across 3 types and 3 difficulty levels."""
    plan = [
        # (case_type,            happy, partial, escalation)  — must sum to type total
        ("vendor_onboarding",    8,     7,       5),   # 20 total
        ("claim_review",         6,     5,       4),   # 15 total
        ("fraud_investigation",  6,     4,       5),   # 15 total  (fraud skews escalation)
    ]
    cases = []
    idx = 1
    for case_type, n_happy, n_partial, n_esc in plan:
        for _ in range(n_happy):
            cases.append(generate_amp_state(case_type, "happy", idx)); idx += 1
        for _ in range(n_partial):
            cases.append(generate_amp_state(case_type, "partial", idx)); idx += 1
        for _ in range(n_esc):
            cases.append(generate_amp_state(case_type, "escalation", idx)); idx += 1

    assert len(cases) == 50, f"Expected 50 cases, got {len(cases)}"
    return cases


def extract_agent_pairs(amp_state: dict) -> dict:
    """
    Extract per-agent input/output pairs for use as unit test fixtures.
    Returns a dict keyed by agent name with {input, output} sub-dicts.
    """
    return {
        "csa": {
            "input":  {"case_id": amp_state["task_intake"]["case_id"],
                       "case_type": amp_state["task_intake"]["case_type"],
                       "task_text": amp_state["task_intake"]["title"]},
            "output": amp_state["csa_output"],
        },
        "rra": {
            "input":  {"task_id": amp_state["task_intake"]["task_id"],
                       "workflow_type": amp_state["task_intake"]["case_type"],
                       "workflow_state": "in_review",
                       "priority": amp_state["task_intake"]["priority"]},
            "output": amp_state["risk_output"],
        },
        "gpa": {
            "input":  amp_state["task_intake"],
            "output": amp_state["governance_output"],
        },
        "iaa": {
            "input":  {"risk_flags":    amp_state["risk_output"]["risk_flags"],
                       "risk_severity": amp_state["risk_output"]["overall_risk_level"],
                       "case_type":     amp_state["task_intake"]["case_type"]},
            "output": amp_state["iaa_output"],
        },
        "da": {
            "input":  {"task_id":        amp_state["task_intake"]["task_id"],
                       "priority":       amp_state["task_intake"]["priority"],
                       "business_domain": amp_state["task_intake"]["business_domain"]},
            "output": amp_state["da_output"],
        },
        "swa": {
            "input":  {"case_history": amp_state["csa_output"]["context"]["case_history"]},
            "output": amp_state["swa_output"],
        },
    }


def _validate_case(case: dict, idx: int) -> list[str]:
    """Return a list of consistency violations for a generated case."""
    errs = []
    meta = case["meta"]
    rra  = case["risk_output"]
    iaa  = case["iaa_output"]
    gpa  = case["governance_output"]
    da   = case["da_output"]
    csa  = case["csa_output"]

    # All required top-level keys present
    for key in ("task_intake","csa_output","risk_output","governance_output",
                "iaa_output","da_output","swa_output","meta"):
        if key not in case:
            errs.append(f"[{idx}] missing top-level key: {key}")

    # case_history event_types in ALL_ACTION_TYPES
    for ev in csa["context"]["case_history"]:
        if ev["event_type"] not in ALL_ACTION_TYPES:
            errs.append(f"[{idx}] invalid event_type: {ev['event_type']}")

    # csa_version present
    if "csa_version" not in csa.get("meta", {}):
        errs.append(f"[{idx}] csa_output.meta.csa_version missing")

    # D7 consistency
    computed_esc = any([
        rra["escalate_to_human"], gpa["requires_approval"],
        iaa["escalate_to_human"], da["escalation_required"],
    ])
    if meta["requires_escalation"] != computed_esc:
        errs.append(f"[{idx}] meta.requires_escalation mismatch")

    return errs


# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate 50 synthetic AmpState cases")
    parser.add_argument("--out", default="data/synthetic_amp_states.json",
                        help="Output file path (default: data/synthetic_amp_states.json)")
    parser.add_argument("--validate", action="store_true",
                        help="Run consistency checks after generation")
    args = parser.parse_args()

    print("Generating 50 AmpState cases...")
    cases = generate_all_cases()

    if args.validate:
        all_errors = []
        for i, case in enumerate(cases):
            all_errors.extend(_validate_case(case, i + 1))
        if all_errors:
            print(f"\n{len(all_errors)} validation error(s):")
            for e in all_errors:
                print(f"  {e}")
        else:
            print("All 50 cases passed validation.")

    by_type  = {}
    by_diff  = {}
    for c in cases:
        ct = c["task_intake"]["case_type"]
        by_type[ct] = by_type.get(ct, 0) + 1
        esc = c["meta"]["requires_escalation"]
        has_err = bool(c["meta"].get("stage_errors"))
        diff = "escalation" if esc else ("partial" if has_err else "happy")
        by_diff[diff] = by_diff.get(diff, 0) + 1

    print(f"\nDistribution by case_type: {by_type}")
    print(f"Distribution by difficulty: {by_diff}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cases, indent=2, default=str))
    print(f"\nWrote {len(cases)} cases to {out_path}")

    # Also write one fixture per agent for easy test import
    fixtures_dir = out_path.parent / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    for agent in ("csa", "rra", "gpa", "iaa", "da", "swa"):
        pairs = [extract_agent_pairs(c)[agent] for c in cases]
        (fixtures_dir / f"{agent}_fixtures.json").write_text(
            json.dumps(pairs, indent=2, default=str)
        )
    print(f"Agent fixtures written to {fixtures_dir}/")


if __name__ == "__main__":
    main()
