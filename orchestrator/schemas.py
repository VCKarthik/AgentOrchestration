"""
Orchestrator-level Pydantic v2 schemas for AmpState.

AmpState is the canonical shared state that flows through the entire AMP workflow.
It is assembled by the orchestrator — never modified by individual agents.
All fields are Optional with None default so partially-completed runs are valid.

Typed sub-models replace all dict[str, Any] fields so Gemini can generate valid
JSON schemas for ADK FunctionTools without emitting additionalProperties errors.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Stage 0 — Task Intake (populated by orchestrator before any agent runs)
# ─────────────────────────────────────────────────────────────────────────────

class TaskIntake(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    task_id: Optional[str] = None
    case_id: Optional[str] = None
    case_type: Optional[str] = None
    task_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    requester: Optional[str] = None
    requester_role: Optional[str] = None
    priority: Optional[str] = None
    urgency: Optional[str] = None
    estimated_effort: Optional[float] = None
    due_date: Optional[str] = None
    business_domain: Optional[str] = None
    timestamp: Optional[str] = None
    required_skills: Optional[list[str]] = None
    monetary_value: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — CSA Output
# ─────────────────────────────────────────────────────────────────────────────

class CsaEmail(BaseModel):
    """One email record from the CSA context packet."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    case_id: Optional[str] = None
    case_type: Optional[str] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    recipients: Optional[str] = None
    date: Optional[str] = None
    body: Optional[str] = None
    attachments: list[str] = Field(default_factory=list)
    thread_id: Optional[str] = None
    file_path: Optional[str] = None
    file_link: Optional[str] = None


class CsaDocument(BaseModel):
    """One document record from the CSA context packet."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    case_id: Optional[str] = None
    case_type: Optional[str] = None
    filename: Optional[str] = None
    file_type: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    file_path: Optional[str] = None
    file_link: Optional[str] = None


class CsaCalendarEvent(BaseModel):
    """One calendar event from the CSA context packet."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    case_id: Optional[str] = None
    case_type: Optional[str] = None
    title: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    attendees: list[str] = Field(default_factory=list)
    location: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class CsaHistoryEntry(BaseModel):
    """One case_history record from the CSA context packet."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    case_id: Optional[str] = None
    case_type: Optional[str] = None
    event_type: Optional[str] = None
    actor: Optional[str] = None
    timestamp: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class CsaMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_sources: Optional[int] = None
    sql_hits: Optional[int] = None
    qdrant_hits: Optional[int] = None
    keywords_used: list[str] = Field(default_factory=list)
    retrieval_method: Optional[str] = None
    csa_version: Optional[str] = None


class CsaValidation(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence_score: Optional[float] = None
    total_sources: Optional[int] = None


class CsaContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    emails: list[CsaEmail] = Field(default_factory=list)
    documents: list[CsaDocument] = Field(default_factory=list)
    calendar_events: list[CsaCalendarEvent] = Field(default_factory=list)
    case_history: list[CsaHistoryEntry] = Field(default_factory=list)


class CsaOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: Optional[str] = None
    task_text: Optional[str] = None
    case_id: Optional[str] = None
    case_type: Optional[str] = None
    timestamp: Optional[str] = None
    context: Optional[CsaContext] = None
    validation: Optional[CsaValidation] = None
    meta: Optional[CsaMeta] = None


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2a — RRA Output
# ─────────────────────────────────────────────────────────────────────────────

class RiskOutput(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    task_id: Optional[str] = None
    workflow_state: Optional[str] = None
    priority: Optional[str] = None
    risk_flags: list[str] = Field(default_factory=list)
    # Each risk_item: { risk_type, severity, reason, blocking }
    # Carried alongside risk_flags so the UI can render per-item severity
    # and the human-readable reason instead of just the flag name.
    risk_items: list[dict] = Field(default_factory=list)
    overall_risk_level: Optional[str] = None
    can_proceed: Optional[str] = None
    escalate_to_human: bool = False
    escalation_target: Optional[str] = None
    reasoning_summary: Optional[str] = None
    operating_context: Optional[str] = None
    model_used: Optional[str] = None
    timestamp: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2b — GPA Output
# ─────────────────────────────────────────────────────────────────────────────

class GovernanceOutput(BaseModel):
    model_config = ConfigDict()

    task_id: Optional[str] = None
    decision: Optional[str] = None
    reason: Optional[str] = None
    confidence: Optional[float] = None
    requires_approval: bool = False
    next_agent: Optional[str] = None
    matched_rule_ids: list[int] = Field(default_factory=list)
    matched_chunk_ids: list[int] = Field(default_factory=list)
    approvers: list[str] = Field(default_factory=list)
    reason_list: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2c — IAA Output
# ─────────────────────────────────────────────────────────────────────────────

class PredictedActionOut(BaseModel):
    """One predicted action from the IAA."""
    model_config = ConfigDict(extra="allow")

    action_id: Optional[str] = None
    label: Optional[str] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None


class TaskItemOut(BaseModel):
    """One task item from IAA task_list."""
    model_config = ConfigDict(extra="allow")

    task_id: Optional[str] = None
    action: Optional[str] = None
    assigned_role: Optional[str] = None
    priority: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)
    reasoning: Optional[str] = None


class WorkflowStepOut(BaseModel):
    """One step in the IAA workflow_timeline."""
    model_config = ConfigDict(extra="allow")

    step: Optional[int] = None
    event_type: Optional[str] = None
    actor: Optional[str] = None
    status: Optional[str] = None
    timestamp: Optional[str] = None


class IaaOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    predicted_actions: list[PredictedActionOut] = Field(default_factory=list)
    recommended_action: Optional[PredictedActionOut] = None
    override_applied: bool = False
    override_reason: Optional[str] = None
    retrieved_context_ids: list[str] = Field(default_factory=list)
    escalate_to_human: bool = False
    operating_context: Optional[str] = None
    model_used: Optional[str] = None
    timestamp: Optional[str] = None
    task_list: list[TaskItemOut] = Field(default_factory=list)
    workflow_timeline: list[WorkflowStepOut] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — DA Output
# ─────────────────────────────────────────────────────────────────────────────

class OwnerInfo(BaseModel):
    """Owner or assignee info dict from DA output."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None


class CandidateRankingOut(BaseModel):
    """One entry in DA candidate_rankings."""
    model_config = ConfigDict(extra="allow")

    assignee_id: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    composite_score: Optional[float] = None
    utilization_percent: Optional[float] = None
    availability_status: Optional[str] = None
    seniority: Optional[str] = None
    skill_match_score: Optional[float] = None
    domain_match_score: Optional[float] = None
    capacity_score: Optional[float] = None
    priority_handling_score: Optional[float] = None
    recommendation_boost: Optional[float] = None
    hard_rule_passed: Optional[bool] = None
    disqualification_reason: Optional[str] = None


class DecisionFactorsOut(BaseModel):
    """DA decision_factors sub-model."""
    model_config = ConfigDict(extra="allow")

    skill_match_score: Optional[float] = None
    prior_case_ownership: Optional[bool] = None
    current_utilization: Optional[float] = None
    availability_status: Optional[str] = None
    domain_match: Optional[bool] = None
    sla_at_risk: Optional[bool] = None
    priority_override_applied: Optional[bool] = None
    recommended_candidate_boosted: Optional[bool] = None


class DaOutput(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="allow")

    assignment_id: Optional[str] = None
    task_id: Optional[str] = None
    status: Optional[str] = None
    assignment_reason: Optional[str] = None
    confidence_score: Optional[float] = None
    reasons: list[str] = Field(default_factory=list)
    selected_channel: Optional[str] = None
    selected_owner_type: Optional[str] = None
    selected_owner: Optional[OwnerInfo] = None
    selected_assignee: Optional[OwnerInfo] = None
    candidate_rankings: list[CandidateRankingOut] = Field(default_factory=list)
    decision_factors: Optional[DecisionFactorsOut] = None
    escalation_required: bool = False
    escalation_reason: Optional[str] = None
    escalation_urgency: Optional[str] = None
    audit_log_id: Optional[str] = None
    timestamp: Optional[str] = None
    expected_completion: Optional[str] = None
    orchestrator_action: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 async — SWA Output
# ─────────────────────────────────────────────────────────────────────────────

class AnalysisWindowOut(BaseModel):
    """Serialized AgentOutput.window_analyzed."""
    model_config = ConfigDict(extra="allow")

    start: Optional[str] = None
    end: Optional[str] = None
    events_processed: Optional[int] = None


class RunMetricsOut(BaseModel):
    """Serialized AgentOutput.metrics."""
    model_config = ConfigDict(extra="allow")

    patterns_detected: Optional[int] = None
    recommendations_made: Optional[int] = None
    escalations_raised: Optional[int] = None
    events_processed: Optional[int] = None
    processing_time_ms: Optional[float] = None
    detectors_used: list[str] = Field(default_factory=list)


class TemporalSignatureOut(BaseModel):
    """Serialized SWA TemporalSignature."""
    model_config = ConfigDict(extra="allow")

    mean_interval_hours: Optional[float] = None
    stddev_interval_hours: Optional[float] = None
    regularity_score: Optional[float] = None


class AutomationRecommendationOut(BaseModel):
    """Serialized SWA AutomationRecommendation."""
    model_config = ConfigDict(extra="allow")

    type: Optional[str] = None
    trigger: Optional[str] = None
    action: Optional[str] = None
    estimated_time_saved_per_week_hours: Optional[float] = None


class CaseTimelineEntryOut(BaseModel):
    """One entry in a CasePortfolio timeline."""
    model_config = ConfigDict(extra="allow")

    timestamp: Optional[str] = None
    actor_id: Optional[str] = None
    actor_type: Optional[str] = None
    action_type: Optional[str] = None
    target_entity: Optional[str] = None
    outcome: Optional[str] = None


class CasePortfolioOut(BaseModel):
    """Serialized SWA CasePortfolio object."""
    model_config = ConfigDict(extra="allow")

    case_id: Optional[str] = None
    case_type: Optional[str] = None
    status: Optional[str] = None
    total_events: Optional[int] = None
    distinct_actors: Optional[int] = None
    distinct_actions: Optional[int] = None
    case_duration_hours: Optional[float] = None
    timeline: list[CaseTimelineEntryOut] = Field(default_factory=list)
    action_counts: dict[str, int] = Field(default_factory=dict)
    actor_counts: dict[str, int] = Field(default_factory=dict)
    target_counts: dict[str, int] = Field(default_factory=dict)


class FindingOut(BaseModel):
    """Serialized SWA Finding object."""
    model_config = ConfigDict(extra="allow")

    finding_id: Optional[str] = None
    detector_source: Optional[str] = None
    pattern_type: Optional[str] = None
    pattern_signature: Optional[str] = None
    occurrences: Optional[int] = None
    actors_involved: list[str] = Field(default_factory=list)
    cases_involved: list[str] = Field(default_factory=list)
    temporal_signature: Optional[TemporalSignatureOut] = None
    description: Optional[str] = None
    domain_contextualized_description: Optional[str] = None
    automation_recommendation: Optional[AutomationRecommendationOut] = None
    confidence: Optional[float] = None
    risk_level: Optional[str] = None
    decision: Optional[str] = None
    requires_human_approval: Optional[bool] = None
    evidence_event_ids: list[str] = Field(default_factory=list)


class EscalationOut(BaseModel):
    """Serialized SWA Escalation object."""
    model_config = ConfigDict(extra="allow")

    escalation_id: Optional[str] = None
    reason: Optional[str] = None
    pattern_signature: Optional[str] = None
    occurrences: Optional[int] = None
    recommended_human_role: Optional[str] = None
    summary_for_human: Optional[str] = None
    evidence_event_ids: list[str] = Field(default_factory=list)


class SwaOutput(BaseModel):
    """
    AmpState representation of SWA's AgentOutput (D6).

    Mapping:
      agent               ← AgentOutput.agent ("shadow_work")
      run_id              ← AgentOutput.run_id
      scope               ← AgentOutput.scope ("global" or "case:<id>")
      trigger_type        ← AgentOutput.trigger_type
      findings            ← AgentOutput.findings (serialized)
      escalations         ← AgentOutput.escalations (serialized)
      escalation_surfaced ← True if len(AgentOutput.escalations) > 0
      summary_sent        ← True if len(AgentOutput.findings) > 0
      window_analyzed     ← AgentOutput.window_analyzed (serialized)
      case_portfolios     ← AgentOutput.case_portfolios (serialized)
      metrics             ← AgentOutput.metrics (serialized)
      timestamp           ← AgentOutput.timestamp
    """
    agent: str = Field(default="shadow_work")
    run_id: str = Field(..., description="SWA run identifier")
    scope: str = Field(default="global")
    trigger_type: str = Field(default="scheduled_sweep")
    findings: list[FindingOut] = Field(default_factory=list)
    escalations: list[EscalationOut] = Field(default_factory=list)
    escalation_surfaced: bool = Field(...)
    summary_sent: bool = Field(...)
    window_analyzed: AnalysisWindowOut = Field(...)
    case_portfolios: list[CasePortfolioOut] = Field(default_factory=list)
    metrics: RunMetricsOut = Field(...)
    timestamp: datetime = Field(...)


def swa_output_from_agent_output(agent_output) -> SwaOutput:
    """Build SwaOutput from a SWA AgentOutput instance."""
    dumped = agent_output.model_dump(mode="json")
    wa = dumped.get("window_analyzed", {})
    m = dumped.get("metrics", {})
    return SwaOutput(
        agent=dumped.get("agent", "shadow_work"),
        run_id=dumped["run_id"],
        scope=dumped.get("scope", "global"),
        trigger_type=dumped.get("trigger_type", "scheduled_sweep"),
        findings=[FindingOut(**f) for f in dumped.get("findings", [])],
        escalations=[EscalationOut(**e) for e in dumped.get("escalations", [])],
        escalation_surfaced=len(dumped.get("escalations", [])) > 0,
        summary_sent=len(dumped.get("findings", [])) > 0,
        window_analyzed=AnalysisWindowOut(**wa),
        case_portfolios=[CasePortfolioOut(**p) for p in dumped.get("case_portfolios", [])],
        metrics=RunMetricsOut(**m),
        timestamp=agent_output.timestamp,
    )


# ─────────────────────────────────────────────────────────────────────────────
# AmpState — canonical shared state
# ─────────────────────────────────────────────────────────────────────────────

class AmpState(BaseModel):
    """
    Canonical shared state for the AMP 6-agent workflow.

    Populated incrementally as each stage runs. All stage fields are Optional —
    a partially-completed run is valid and inspectable.
    latency_log and stage_errors are written by the orchestrator, not agents.
    requires_escalation is set by compute_requires_escalation() after DA runs.
    operating_context is set by compute_operating_context() after Stage 2 (D5).
    """
    model_config = ConfigDict(use_enum_values=True)

    task_intake: Optional[TaskIntake] = None

    # Stage 1
    csa_output: Optional[CsaOutput] = None

    # Stage 2 (any subset may run)
    risk_output: Optional[RiskOutput] = None
    governance_output: Optional[GovernanceOutput] = None
    iaa_output: Optional[IaaOutput] = None

    # Stage 3
    da_output: Optional[DaOutput] = None

    # Stage 1 async (may be None at DA time — SWA runs in background)
    swa_result: Optional[SwaOutput] = None

    # Orchestrator-computed
    latency_log: dict[str, float] = Field(default_factory=dict)
    stage_errors: dict[str, Any] = Field(default_factory=dict)
    requires_escalation: bool = False
    operating_context: str = "full"  # D5: set by compute_operating_context() after Stage 2
