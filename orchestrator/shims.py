"""
Orchestrator shims — field transformations between agents.

These functions live here only. They do not modify any agent's internal code.
Two categories:
  - Input-building shims: csa_to_rra, csa_to_gpa, csa_to_iaa
    Build the request payload sent to each Stage 2 agent from AmpState.
  - Output-mapping shims: rra_to_amp, gpa_to_amp, iaa_to_amp, da_to_amp
    Map each agent's raw response dict into the corresponding AmpState field model.
  - Cross-agent shims: case_history_to_incoming_events (CSA → SWA)
  - Orchestrator decision shims: extract_risk_flags (D3), compute_operating_context (D5),
    compute_requires_escalation (D7), build_da_task (D4)
  - Phase 1 slim contract builders: build_case_metadata, build_iaa_input, build_swa_input,
    build_da_input, build_gpa_input, build_rra_input. Produce orchestrator/contracts.py
    instances. Used by tools.py to construct tightly-scoped agent payloads.
"""
from __future__ import annotations

import os
import sys

# ── Import SWA's closed action vocabulary ────────────────────────────────────
_SWA_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "SWA")
if _SWA_CONFIG_PATH not in sys.path:
    sys.path.insert(0, _SWA_CONFIG_PATH)

from config.settings import settings  # SWA/config/settings.py

_ALL_ACTION_TYPES: set[str] = settings.ALL_ACTION_TYPES


# ── case_history → IncomingEvent ──────────────────────────────────────────────

def case_history_to_incoming_events(case_history: list[dict]) -> list[dict]:
    """
    Transform CSA case_history records to SWA IncomingEvent format.

    CSA case_history DB schema:
      id, case_id, case_type, event_type, actor, timestamp, notes, status

    SWA IncomingEvent required fields:
      event_id, case_id, timestamp, actor_id, actor_type,
      action_type, target_entity, target_entity_type, outcome

    Missing fields are filled with validated defaults:
    - actor_type: inferred from actor value
        "system" → "agent"          (system actors are agents, not humans)
        "@" in actor → "human"      (email-style IDs are humans)
        else → "human"              (safe default — human until proven otherwise)
    - target_entity: case_id as fallback (the case itself is the target)
    - target_entity_type: "task" (default — case_history events are task-level)
    - action_type: event_type if in ALL_ACTION_TYPES, else "logged_note"
        (logged_note is always valid — INFORMATIONAL_ACTIONS category)
    - outcome: mapped from status field:
        "open" | "pending" → "pending"
        "closed" | "resolved" → "success"
        else → "pending"
    - event_id: id field from case_history record
    """
    result = []
    for record in case_history:
        actor = record.get("actor") or "unknown"
        action_type = record.get("event_type") or "logged_note"
        status = (record.get("status") or "").lower()
        case_id = record.get("case_id", "")

        # actor_type inference
        if actor.lower() == "system":
            actor_type = "agent"
        elif "@" in actor:
            actor_type = "human"
        else:
            actor_type = "human"

        # action_type validation against closed vocabulary
        if action_type not in _ALL_ACTION_TYPES:
            action_type = "logged_note"

        # outcome mapping
        if status in ("open", "pending"):
            outcome = "pending"
        elif status in ("closed", "resolved"):
            outcome = "success"
        else:
            outcome = "pending"

        result.append({
            "event_id":           record.get("id", ""),
            "case_id":            case_id,
            "timestamp":          record.get("timestamp", ""),
            "actor_id":           actor,
            "actor_type":         actor_type,
            "action_type":        action_type,
            "target_entity":      case_id,          # fallback: the case itself
            "target_entity_type": "task",
            "parent_task_id":     None,
            "context_payload":    {},
            "outcome":            outcome,
        })

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Input-building shims — build request payloads from AmpState
# ─────────────────────────────────────────────────────────────────────────────

def csa_to_rra(csa_output) -> dict:
    """
    Build RRAPredictRequest-compatible payload from AmpState.csa_output.

    RRAPredictRequest fields sourced from CsaOutput:
      task_id         ← csa_output.task_id (CSA run ID)
      workflow_type   ← csa_output.case_type (e.g. "vendor_onboarding")
      workflow_state  ← csa_output.validation.status (COMPLETE | PARTIAL | EMPTY)
      required_inputs ← validation.missing_fields + known document types
      received_inputs ← all doc types present (document types seen in context)
      mandatory_inputs← validation.missing_fields (treat missing as mandatory gaps)
      policy_flag     ← True if validation status is PARTIAL or EMPTY
      blocker_flag    ← False by default (no dependency info at this stage)
    """
    validation = getattr(csa_output, "validation", None) or {}
    if hasattr(validation, "model_dump"):
        validation = validation.model_dump()

    missing_fields: list[str] = validation.get("missing_fields", []) or []
    status: str = (validation.get("status") or "COMPLETE").upper()

    # derive received_inputs from what we have in context
    context = getattr(csa_output, "context", None) or {}
    if hasattr(context, "model_dump"):
        context = context.model_dump()
    received: list[str] = []
    if context.get("emails"):
        received.append("emails")
    if context.get("documents"):
        received.append("documents")
    if context.get("calendar_events"):
        received.append("calendar_events")
    if context.get("case_history"):
        received.append("case_history")

    all_expected = ["emails", "documents", "calendar_events", "case_history"]

    return {
        "task_id":          csa_output.task_id or "unknown",
        "workflow_type":    csa_output.case_type or "general",
        "workflow_state":   status,
        "required_inputs":  all_expected,
        "received_inputs":  received,
        "mandatory_inputs": missing_fields,
        "policy_flag":      status in ("PARTIAL", "EMPTY"),
        "blocker_flag":     False,
        "prior_delay_count": 0,
        "prior_escalation_count": 0,
    }


def csa_to_gpa(task_intake, csa_output) -> dict:
    """
    Build TaskInput-compatible payload from task_intake + csa_output for GPA.

    GPA TaskInput fields:
      task_id           ← task_intake.task_id
      task_type         ← task_intake.task_type
      timestamp         ← csa_output.timestamp
      username          ← task_intake.requester
      requester_role    ← task_intake.requester_role
      task_description  ← task_intake.description
      priority          ← task_intake.priority
      organization      ← task_intake.business_domain
      requested_action  ← task_intake.task_type (best proxy)
      policy_document_ids ← [] (no specific docs targeted at intake)
      risk_assessment   ← empty (RRA runs concurrently, not yet available)
    """
    intake: dict = {}
    if hasattr(task_intake, "model_dump"):
        intake = task_intake.model_dump()
    elif isinstance(task_intake, dict):
        intake = task_intake

    return {
        "task_id":          intake.get("task_id", "unknown"),
        "task_type":        intake.get("task_type", "general"),
        "timestamp":        getattr(csa_output, "timestamp", None) or intake.get("timestamp"),
        "username":         intake.get("requester", "orchestrator"),
        "user_email":       None,
        "requester_role":   intake.get("requester_role"),
        "task_description": intake.get("description", ""),
        "issue_summary":    intake.get("title", ""),
        "priority":         intake.get("priority", "medium"),
        "status":           "open",
        "organization":     intake.get("business_domain", "general"),
        "location":         None,
        "entities":         {},
        "questions_raised": [],
        "people_involved":  [],
        "keywords":         [],
        "source":           {},
        "requested_action": intake.get("task_type", "general"),
        "policy_document_ids": [],
        "policy_type":      intake.get("case_type"),
        "metadata": {
            "monetary_value": intake.get("monetary_value"),
            "task_type":      intake.get("task_type", "general"),
        },
    }


def csa_to_iaa(csa_output, risk_output=None) -> dict:
    """
    Build PredictRequest-compatible payload from csa_output + optional risk_output.

    IAA PredictRequest accepts either process_state or events.
    We always send process_state (more structured).

    ProcessState fields:
      entity_id         ← csa_output.case_id
      current_stage     ← csa_output.validation.status (COMPLETE | PARTIAL | EMPTY)
      current_event_type← last case_history event_type, or "intake"
      prior_actions     ← [e.event_type for e in case_history]
      actor             ← csa_output.task_id (orchestrator run ID as actor proxy)
      timestamp         ← csa_output.timestamp
      risk_flags        ← risk_output.risk_flags if available
      risk_severity     ← risk_output.overall_risk_level if available
      policy_constraints← [] (GPA runs concurrently — not available yet)
      operating_context ← "full" or "partial" based on validation
    """
    validation = getattr(csa_output, "validation", None) or {}
    if hasattr(validation, "model_dump"):
        validation = validation.model_dump()

    context = getattr(csa_output, "context", None) or {}
    if hasattr(context, "model_dump"):
        context = context.model_dump()

    history: list[dict] = context.get("case_history", []) or []
    prior_actions = [e.get("event_type", "") for e in history if e.get("event_type")]
    current_event = prior_actions[-1] if prior_actions else "intake"

    status = (validation.get("status") or "COMPLETE").upper()
    operating_context = "partial" if status in ("PARTIAL", "EMPTY") else "full"

    risk_flags: list[str] = []
    risk_severity: str | None = None
    if risk_output is not None:
        risk_flags = getattr(risk_output, "risk_flags", []) or []
        risk_severity = getattr(risk_output, "overall_risk_level", None)

    process_state = {
        "entity_id":          csa_output.case_id or "unknown",
        "current_stage":      status,
        "current_event_type": current_event,
        "prior_actions":      prior_actions,
        "prior_steps":        [],
        "actor":              csa_output.task_id,
        "timestamp":          getattr(csa_output, "timestamp", None) or "2026-01-01T00:00:00",
        "metadata":           {},
        "risk_flags":         risk_flags,
        "risk_severity":      risk_severity,
        "policy_constraints": [],
        "assigned_owner":     None,
        "operating_context":  operating_context,
    }

    return {"process_state": process_state}


# ─────────────────────────────────────────────────────────────────────────────
# Output-mapping shims — map raw agent response dicts to AmpState models
# ─────────────────────────────────────────────────────────────────────────────

def rra_to_amp(raw: dict) -> dict:
    """
    Map RRA to_dict() response → AmpState.risk_output field dict.

    Key transform: risk_flags derived from risk_items (D3).
    RiskRadarOutput.risk_items is a list of dicts with "risk_type" key.
    overall_risk_level, can_proceed are str values from Severity/ProceedDecision enums.
    """
    risk_items = raw.get("risk_items", []) or []
    risk_flags = [
        item.get("risk_type") or item.get("risk_type", "")
        for item in risk_items
        if item.get("risk_type")
    ]
    return {
        "task_id":           raw.get("task_id"),
        "workflow_state":    raw.get("workflow_state"),
        "priority":          raw.get("priority"),
        "risk_flags":        risk_flags,
        # Forward the rich per-item structure so the Case Workspace can
        # render severity + reason for each flag, not just the flag name.
        "risk_items":        risk_items,
        "overall_risk_level": raw.get("overall_risk_level"),
        "can_proceed":       raw.get("can_proceed"),
        "escalate_to_human": raw.get("escalate_to_human", False),
        "escalation_target": raw.get("escalation_target"),
        "reasoning_summary": raw.get("reasoning_summary"),
        "operating_context": raw.get("operating_context"),
        "model_used":        raw.get("model_used"),
        "timestamp":         str(raw.get("timestamp")) if raw.get("timestamp") else None,
    }


def gpa_to_amp(raw: dict) -> dict:
    """
    Map GPA GovernanceDecisionOutput response → AmpState.governance_output field dict.
    Direct field mapping — GPA output matches AmpState.governance_output after D4 fix.
    """
    return {
        "task_id":           raw.get("task_id"),
        "decision":          raw.get("decision"),
        "reason":            raw.get("reason"),
        "confidence":        raw.get("confidence"),
        "requires_approval": raw.get("requires_approval", False),
        "next_agent":        raw.get("next_agent"),
        "matched_rule_ids":  raw.get("matched_rule_ids", []),
        "matched_chunk_ids": raw.get("matched_chunk_ids", []),
        "approvers":         raw.get("approvers", []),
        "reason_list":       raw.get("reason_list", []),
    }


def iaa_to_amp(raw: dict) -> dict:
    """
    Map IAA PredictResponse → AmpState.iaa_output field dict.

    IAA wraps ActionRecommendation in PredictResponse:
      { "recommendation": ActionRecommendation, "latency_ms": float, "corpus_size": int }
    Unwrap .recommendation to get the actual ActionRecommendation fields.
    """
    rec = raw.get("recommendation") or raw
    if hasattr(rec, "model_dump"):
        rec = rec.model_dump()

    ts = rec.get("timestamp")
    if ts is not None and not isinstance(ts, str):
        ts = str(ts)

    return {
        "predicted_actions":    rec.get("predicted_actions", []),
        "recommended_action":   rec.get("recommended_action"),
        "override_applied":     rec.get("override_applied", False),
        "override_reason":      rec.get("override_reason"),
        "retrieved_context_ids": rec.get("retrieved_context_ids", []),
        "escalate_to_human":    rec.get("escalate_to_human", False),
        "operating_context":    rec.get("operating_context"),
        "model_used":           rec.get("model_used"),
        "timestamp":            ts,
        "task_list":            rec.get("task_list", []),
        "workflow_timeline":    rec.get("workflow_timeline", []),
    }


def da_to_amp(raw: dict) -> dict:
    """
    Map DA AssignmentDecision.model_dump() → AmpState.da_output field dict.
    Direct field mapping — DA output matches AmpState.da_output exactly.
    Enum values are already strings (use_enum_values=True on DA models).
    """
    ts = raw.get("timestamp")
    if ts is not None and not isinstance(ts, str):
        ts = str(ts)
    ec = raw.get("expected_completion")
    if ec is not None and not isinstance(ec, str):
        ec = str(ec)

    return {
        "assignment_id":      raw.get("assignment_id"),
        "task_id":            raw.get("task_id"),
        "status":             raw.get("status"),
        "assignment_reason":  raw.get("assignment_reason"),
        "confidence_score":   raw.get("confidence_score"),
        "reasons":            raw.get("reasons", []),
        "selected_channel":   raw.get("selected_channel"),
        "selected_owner_type": raw.get("selected_owner_type"),
        "selected_owner":     raw.get("selected_owner"),
        "selected_assignee":  raw.get("selected_assignee"),
        "candidate_rankings": raw.get("candidate_rankings", []),
        "decision_factors":   raw.get("decision_factors"),
        "escalation_required": raw.get("escalation_required", False),
        "escalation_reason":  raw.get("escalation_reason"),
        "escalation_urgency": raw.get("escalation_urgency"),
        "audit_log_id":       raw.get("audit_log_id"),
        "timestamp":          ts,
        "expected_completion": ec,
        "orchestrator_action": raw.get("orchestrator_action"),
    }


# ── D3: RRA risk_flags extraction shim ───────────────────────────────────────

def extract_risk_flags(rra_output) -> list[str]:
    """
    Extract risk_flags list[str] from RiskRadarOutput.
    risk_flags never appear on RiskRadarOutput directly —
    they are derived from risk_items per Decision D3.
    """
    return [item.risk_type.value for item in rra_output.risk_items]


# ── D5: operating_context computation ────────────────────────────────────────

def compute_operating_context(rra_output, iaa_output) -> str:
    """
    Compute meta.operating_context after Stage 2 completes.
    Returns "partial" if either agent reported partial context, else "full".
    Neither agent is authoritative — orchestrator decides.
    """
    rra_ctx = rra_output.operating_context
    # RRA returns OperatingContext enum; normalize to str
    rra_str = rra_ctx.value if hasattr(rra_ctx, "value") else str(rra_ctx)
    iaa_str = iaa_output.operating_context  # already a str

    if "partial" in rra_str or "partial" in iaa_str:
        return "partial"
    return "full"


# ── D7: requires_escalation computation ──────────────────────────────────────

def compute_requires_escalation(
    rra_output,
    governance_output,
    iaa_output,
    da_output,
) -> bool:
    """
    True if ANY of the four escalation signals is set.
    Decision D7.
    """
    return any([
        getattr(rra_output,        "escalate_to_human",   False),
        getattr(governance_output, "requires_approval",   False),
        getattr(iaa_output,        "escalate_to_human",   False),
        getattr(da_output,         "escalation_required", False),
    ])


# ── D4: DA Task merge shim ────────────────────────────────────────────────────

def build_da_task(
    task_intake: dict,
    iaa_task_item,
    gpa_output_raw: dict,
    meta: dict,
) -> dict:
    """
    Merge task_intake + IAA TaskItem + GPA raw dict into a DA Task-compatible dict.

    Precedence rules:
    - task_id:         IAA task_item.task_id
    - title:           task_intake["title"] if present, else title-case of iaa_task_item.action
    - description:     task_intake["description"] if present, else iaa_task_item.reasoning
    - priority:        IAA priority overrides task_intake priority if present
    - task_type:       task_intake["task_type"] (required)
    - estimated_effort: task_intake["estimated_effort"] (required; default 1.0 + log)
    - due_date:        task_intake["due_date"] (required; default now+24h + log)
    - business_domain: task_intake["business_domain"] (required)
    - requester:       task_intake["requester"] (required)
    - assigned_role → recommended_candidates: [iaa_task_item.assigned_role] if set

    Fields NOT forwarded to DA: depends_on, reasoning (IAA-internal only).
    Missing required fields get sensible defaults logged to meta["stage_errors"]["da_merge"].
    """
    from datetime import datetime, timezone, timedelta

    errors: list[str] = []

    def _require(field: str, default):
        val = task_intake.get(field)
        if val is None:
            errors.append(f"task_intake.{field} missing — defaulted to {default!r}")
            return default
        return val

    title = task_intake.get("title") or iaa_task_item.action.replace("_", " ").title()
    description = task_intake.get("description") or iaa_task_item.reasoning

    # IAA priority overrides if present (not the default "medium")
    iaa_priority = getattr(iaa_task_item, "priority", None)
    priority = iaa_priority if iaa_priority else task_intake.get("priority", "medium")

    now = datetime.now(timezone.utc)
    result = {
        "task_id":          iaa_task_item.task_id,
        "task_type":        _require("task_type", "general"),
        "title":            title,
        "description":      description,
        "priority":         priority,
        "urgency":          task_intake.get("urgency", "moderate"),
        "estimated_effort": _require("estimated_effort", 1.0),
        "due_date":         _require("due_date", (now + timedelta(hours=24)).isoformat()),
        "business_domain":  _require("business_domain", "general"),
        "requester":        _require("requester", "orchestrator"),
        "source_system":    task_intake.get("source_system", "orchestrator"),
    }

    # Map assigned_role → recommended_candidates
    assigned_role = getattr(iaa_task_item, "assigned_role", None)
    if assigned_role:
        result["recommended_candidates"] = [assigned_role]

    if errors:
        stage_errors = meta.setdefault("stage_errors", {})
        stage_errors.setdefault("da_merge", []).extend(errors)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Slim contract builders (orchestrator/contracts.py)
# Each agent receives only what it needs. AmpState stays full internally,
# but HTTP/in-process payloads are tight. The IAA latency fix lives here:
# case_history_summary capped at 5, recent_communications capped at 3 (no
# bodies, no attachments).
# ─────────────────────────────────────────────────────────────────────────────


def _safe_dump(obj):
    """Pydantic v1/v2 + dict tolerant dump."""
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, dict):
        return obj
    return {}


def build_case_metadata(task_intake) -> dict:
    """Project AmpState.task_intake → CaseMetadata-compatible dict."""
    intake = _safe_dump(task_intake)
    return {
        "case_id":         intake.get("case_id") or intake.get("task_id") or "unknown",
        "case_type":       intake.get("case_type") or "general",
        "priority":        intake.get("priority") or "medium",
        "due_date":        intake.get("due_date"),
        "title":           intake.get("title") or "",
        "description":     intake.get("description") or "",
        "requester":       intake.get("requester") or "orchestrator",
        "business_domain": intake.get("business_domain") or "general",
    }


def build_csa_input(task_intake) -> dict:
    """CSAInput payload — CSA reads only case identifiers + a query text."""
    return {"case": build_case_metadata(task_intake)}


def build_rra_input(task_intake, csa_output) -> dict:
    """RRAInput payload — slim summary of CSA validation, document and history counts."""
    validation = _safe_dump(getattr(csa_output, "validation", None))
    context = _safe_dump(getattr(csa_output, "context", None))
    docs = context.get("documents", []) or []
    history = context.get("case_history", []) or []
    return {
        "case": build_case_metadata(task_intake),
        "context_validation": {
            "status":           validation.get("status", "COMPLETE"),
            "missing_fields":   validation.get("missing_fields", []) or [],
            "confidence_score": validation.get("confidence_score", 1.0),
        },
        "document_count":     len(docs),
        "case_history_count": len(history),
    }


def build_gpa_input(task_intake, risk_output=None) -> dict:
    """GPAInput payload — case + risk_flags only. Estimated value reserved for future."""
    flags: list[str] = []
    if risk_output is not None:
        flags = getattr(risk_output, "risk_flags", []) or []
    return {
        "case": build_case_metadata(task_intake),
        "risk_flags": flags,
        "estimated_value": None,
    }


def build_iaa_input(
    task_intake,
    csa_output,
    risk_output=None,
    governance_output=None,
) -> dict:
    """
    IAAInput payload — last-5 case_history events, last-3 emails (subject/from/date only).
    No email bodies, no attachments. This is the IAA latency fix:
    keeps the LLM prompt small and bounded.
    """
    context = _safe_dump(getattr(csa_output, "context", None))
    history = context.get("case_history", []) or []
    emails  = context.get("emails", []) or []

    # Last 5 events, smallest viable shape
    history_summary: list[dict] = []
    for h in history[-5:]:
        h_dump = _safe_dump(h) if not isinstance(h, dict) else h
        history_summary.append({
            "timestamp":  h_dump.get("timestamp"),
            "actor":      h_dump.get("actor"),
            "event_type": h_dump.get("event_type"),
            "status":     h_dump.get("status"),
        })

    # Last 3 emails — header fields only, no body, no attachments
    recent_comms: list[dict] = []
    for e in emails[-3:]:
        e_dump = _safe_dump(e) if not isinstance(e, dict) else e
        recent_comms.append({
            "from":      e_dump.get("sender"),
            "subject":   e_dump.get("subject"),
            "timestamp": e_dump.get("date"),
        })

    risk_flags: list[str] = []
    if risk_output is not None:
        risk_flags = getattr(risk_output, "risk_flags", []) or []

    governance_decision = None
    requires_approval = False
    if governance_output is not None:
        governance_decision = getattr(governance_output, "decision", None)
        requires_approval = getattr(governance_output, "requires_approval", False)

    validation = _safe_dump(getattr(csa_output, "validation", None))
    status = (validation.get("status") or "COMPLETE").upper()
    operating_context = "partial" if status in ("PARTIAL", "EMPTY") else "full"

    return {
        "case":                  build_case_metadata(task_intake),
        "case_history_summary":  history_summary,
        "recent_communications": recent_comms,
        "risk_flags":            risk_flags,
        "governance_decision":   governance_decision,
        "requires_approval":     requires_approval,
        "operating_context":     operating_context,
    }


def build_da_input(
    task_intake,
    iaa_output,
    risk_output,
    governance_output,
) -> dict:
    """DAInput payload — flattened decision signals from upstream agents."""
    iaa_rec: dict = {}
    if iaa_output and getattr(iaa_output, "recommended_action", None):
        iaa_rec = _safe_dump(iaa_output.recommended_action)
        if iaa_output.task_list:
            first = iaa_output.task_list[0]
            first_dump = _safe_dump(first)
            iaa_rec["assigned_role"] = first_dump.get("assigned_role")
            iaa_rec["priority"]      = first_dump.get("priority")

    risk_level = "low"
    rra_escalate = False
    if risk_output is not None:
        risk_level = getattr(risk_output, "overall_risk_level", "low") or "low"
        rra_escalate = getattr(risk_output, "escalate_to_human", False)

    iaa_escalate = bool(iaa_output and getattr(iaa_output, "escalate_to_human", False))

    decision = "APPROVE"
    requires_approval = False
    gpa_escalate = False
    if governance_output is not None:
        decision = getattr(governance_output, "decision", "APPROVE") or "APPROVE"
        requires_approval = getattr(governance_output, "requires_approval", False)
        gpa_escalate = requires_approval

    return {
        "case": build_case_metadata(task_intake),
        "iaa_recommended_action": iaa_rec,
        "risk_level": risk_level,
        "governance_decision": decision,
        "requires_approval": requires_approval,
        "escalate_flags": {
            "rra": bool(rra_escalate),
            "iaa": bool(iaa_escalate),
            "gpa": bool(gpa_escalate),
        },
    }


def build_swa_input(csa_output, window_days: int = 30) -> dict:
    """SWAInput payload — case_history_events for in-process analysis."""
    context = _safe_dump(getattr(csa_output, "context", None))
    history = context.get("case_history", []) or []
    events = [_safe_dump(h) if not isinstance(h, dict) else h for h in history]
    return {"case_history_events": events, "window_days": window_days}
