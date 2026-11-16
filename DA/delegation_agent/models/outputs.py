from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AssignmentStatus(str, Enum):
    ASSIGNED = "assigned"
    ESCALATED = "escalated"
    UNASSIGNED = "unassigned"
    REVIEW_REQUIRED = "review_required"


class EscalationUrgency(str, Enum):
    IMMEDIATE = "immediate"
    URGENT = "urgent"
    MODERATE = "moderate"
    LOW = "low"


class AssignmentReason(str, Enum):
    OWNERSHIP_CONTINUITY = "ownership_continuity"
    SKILL_MATCH = "skill_match"
    WORKLOAD_BALANCE = "workload_balance"
    PRIORITY_OVERRIDE = "priority_override"
    RECOMMENDED_CANDIDATE = "recommended_candidate"
    AUTOMATION = "automation"
    FALLBACK = "fallback"
    CHANNEL_ROUTING = "channel_routing"
    SPECIALIZED_AGENT = "specialized_agent"
    SUPERVISOR_REVIEW = "supervisor_review"
    MANUAL_TRIAGE = "manual_triage"


class ExecutionChannel(str, Enum):
    HUMAN_OWNER = "human_owner"
    SPECIALIZED_AGENT = "specialized_agent"
    AUTOMATION = "automation"
    SUPERVISOR_REVIEW = "supervisor_review"
    MANUAL_TRIAGE = "manual_triage"


class OwnerType(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"
    QUEUE = "queue"
    NONE = "none"


class CandidateRanking(BaseModel):
    assignee_id: str
    name: str
    role: str

    skill_match_score: float
    domain_match_score: float
    capacity_score: float
    priority_handling_score: float
    recommendation_boost: float = 0.0
    composite_score: float

    utilization_percent: float
    availability_status: str
    seniority: str

    hard_rule_passed: bool = True
    disqualification_reason: Optional[str] = None


class DecisionFactors(BaseModel):
    skill_match_score: float = 0.0
    prior_case_ownership: bool = False
    current_utilization: float = 0.0
    availability_status: str = "unknown"
    domain_match: bool = False
    sla_at_risk: bool = False
    priority_override_applied: bool = False
    recommended_candidate_boosted: bool = False


class AssignmentDecision(BaseModel):
    assignment_id: str = Field(
        default_factory=lambda: f"ASN-{uuid.uuid4().hex[:10].upper()}"
    )
    task_id: str

    status: AssignmentStatus
    assignment_reason: Optional[AssignmentReason] = None
    confidence_score: float = 0.0
    reasons: List[str] = Field(default_factory=list)

    # Channel-first routing
    selected_channel: Optional[ExecutionChannel] = None
    selected_owner_type: OwnerType = OwnerType.NONE
    selected_owner: Optional[Dict[str, Any]] = None

    # Backward compatibility for human-owner flow
    selected_assignee: Optional[Dict[str, Any]] = None

    # Human candidate rankings only
    candidate_rankings: List[CandidateRanking] = Field(default_factory=list)
    decision_factors: Optional[DecisionFactors] = None

    escalation_required: bool = False
    escalation_reason: Optional[str] = None
    escalation_urgency: Optional[EscalationUrgency] = None

    audit_log_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expected_completion: Optional[datetime] = None

    orchestrator_action: Optional[str] = None

    def resolved_owner_name(self) -> str:
        if isinstance(self.selected_owner, dict):
            return self.selected_owner.get("name", "N/A")
        if isinstance(self.selected_assignee, dict):
            return self.selected_assignee.get("name", "N/A")
        return "N/A"

    def to_summary(self) -> str:
        owner_name = self.resolved_owner_name()

        channel = (
            self.selected_channel.value
            if hasattr(self.selected_channel, "value")
            else self.selected_channel or "N/A"
        )

        owner_type = (
            self.selected_owner_type.value
            if hasattr(self.selected_owner_type, "value")
            else self.selected_owner_type or "N/A"
        )

        status = (
            self.status.value
            if hasattr(self.status, "value")
            else self.status
        )

        lines = [
            f"  Assignment ID   : {self.assignment_id}",
            f"  Task ID         : {self.task_id}",
            f"  Status          : {status}",
            f"  Channel         : {channel}",
            f"  Owner Type      : {owner_type}",
            f"  Selected Owner  : {owner_name}",
            f"  Confidence      : {self.confidence_score:.1f}%",
            f"  Escalation      : "
            + (
                f"YES — {self.escalation_reason}"
                if self.escalation_required
                else "No"
            ),
            f"  Reasons         :",
        ]

        for reason in self.reasons:
            lines.append(f"    • {reason}")

        if self.candidate_rankings:
            lines.append("  Top Human Candidates  :")
            for r in self.candidate_rankings[:3]:
                lines.append(
                    f"    [{r.composite_score:.1f}] {r.name} ({r.role}) — util={r.utilization_percent:.0f}%"
                )

        if self.orchestrator_action:
            lines.append(f"  Orchestrator Action : {self.orchestrator_action}")

        return "\n".join(lines)

    class Config:
        use_enum_values = True


class AuditLog(BaseModel):
    audit_log_id: str = Field(
        default_factory=lambda: f"AUD-{uuid.uuid4().hex[:12].upper()}"
    )
    task_id: str
    assignment_id: str
    triggered_by: str

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    decision: AssignmentDecision

    candidates_evaluated: int
    candidates_filtered_out: int

    rules_applied: List[str] = Field(default_factory=list)
    escalation_triggers_checked: List[str] = Field(default_factory=list)

    processing_time_ms: Optional[float] = None

    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    class Config:
        use_enum_values = True