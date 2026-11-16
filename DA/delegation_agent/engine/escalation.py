from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..models.outputs import CandidateRanking, EscalationUrgency
from ..models.task import CustomerTier, FlagSeverity, Task


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Refined thresholds:
# - Do not escalate too aggressively for moderate uncertainty
# - Only escalate when confidence is truly weak or risk is materially high
LOW_CONFIDENCE_THRESHOLD: float = 50.0
CRITICAL_CONFIDENCE_THRESHOLD: float = 35.0
STRONG_CANDIDATE_THRESHOLD: float = 70.0
MEDIUM_PRIORITY_SAFE_THRESHOLD: float = 55.0

HIGH_VALUE_THRESHOLD: float = 150_000.0
REPEATED_REASSIGNMENT_LIMIT: int = 2
OVERLOADED_UTILIZATION_THRESHOLD: float = 95.0
EXTREME_TIE_GAP_THRESHOLD: float = 2.0
VERY_SHORT_DESCRIPTION_THRESHOLD: int = 15


# ---------------------------------------------------------------------------
# Escalation result
# ---------------------------------------------------------------------------

@dataclass
class EscalationVerdict:
    should_escalate: bool = False
    reasons: List[str] = field(default_factory=list)
    urgency: EscalationUrgency = EscalationUrgency.LOW
    recommended_actions: List[str] = field(default_factory=list)

    def add(
        self,
        reason: str,
        urgency: EscalationUrgency = EscalationUrgency.MODERATE,
        action: Optional[str] = None,
    ) -> None:
        self.should_escalate = True
        self.reasons.append(reason)

        urgency_rank = {
            EscalationUrgency.LOW: 0,
            EscalationUrgency.MODERATE: 1,
            EscalationUrgency.URGENT: 2,
            EscalationUrgency.IMMEDIATE: 3,
        }

        if urgency_rank[urgency] > urgency_rank[self.urgency]:
            self.urgency = urgency

        if action:
            self.recommended_actions.append(action)

    @property
    def primary_reason(self) -> str:
        return self.reasons[0] if self.reasons else "Escalation required"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _priority_value(task: Task) -> str:
    return task.priority if isinstance(task.priority, str) else task.priority.value


def _customer_tier_value(task: Task) -> str:
    return task.customer_tier if isinstance(task.customer_tier, str) else task.customer_tier.value


def _has_strong_candidate(task: Task, qualified_rankings: List[CandidateRanking]) -> bool:
    """
    A strong candidate should suppress many soft escalation triggers.
    """
    if not qualified_rankings:
        return False

    best_score = qualified_rankings[0].composite_score
    priority = _priority_value(task)

    if best_score >= STRONG_CANDIDATE_THRESHOLD:
        return True

    if best_score >= MEDIUM_PRIORITY_SAFE_THRESHOLD and priority in ("low", "medium"):
        return True

    return False


def _check_no_eligible_candidates(
    qualified_rankings: List[CandidateRanking],
    verdict: EscalationVerdict,
) -> None:
    if not qualified_rankings:
        verdict.add(
            "No eligible assignees available",
            EscalationUrgency.URGENT,
            "Expand candidate pool or route to supervisor queue",
        )


def _check_low_confidence(
    qualified_rankings: List[CandidateRanking],
    task: Task,
    verdict: EscalationVerdict,
) -> None:
    if not qualified_rankings:
        return

    best = qualified_rankings[0].composite_score
    priority = _priority_value(task)

    if best < CRITICAL_CONFIDENCE_THRESHOLD:
        verdict.add(
            f"Very low confidence assignment ({best:.1f}%)",
            EscalationUrgency.URGENT,
            "Require manual review before assignment",
        )
    elif best < LOW_CONFIDENCE_THRESHOLD and priority in ("high", "critical"):
        verdict.add(
            f"Low confidence ({best:.1f}%) for {priority}-priority task",
            EscalationUrgency.MODERATE,
            "Supervisor should validate routing decision",
        )

    # Only escalate ties when task importance is high and gap is extremely narrow
    if len(qualified_rankings) >= 2 and priority == "critical":
        gap = abs(
            qualified_rankings[0].composite_score
            - qualified_rankings[1].composite_score
        )

        if gap < EXTREME_TIE_GAP_THRESHOLD:
            verdict.add(
                f"Top candidates are extremely close ({gap:.1f} score gap)",
                EscalationUrgency.MODERATE,
                "Apply secondary review or tie-break rule",
            )


def _check_compliance_and_policy_flags(task: Task, verdict: EscalationVerdict) -> None:
    for flag in task.compliance_flags:
        if flag.severity == FlagSeverity.CRITICAL:
            verdict.add(
                f"Critical compliance flag: '{flag.label}'",
                EscalationUrgency.IMMEDIATE,
                "Immediate compliance review required",
            )

    for flag in task.policy_flags:
        if flag.severity == FlagSeverity.CRITICAL:
            verdict.add(
                f"Critical policy flag: '{flag.label}'",
                EscalationUrgency.IMMEDIATE,
                "Immediate policy review required",
            )


def _check_high_monetary_value(
    task: Task,
    verdict: EscalationVerdict,
    *,
    strong_candidate: bool,
) -> None:
    """
    High value alone should not always escalate if a strong owner exists.
    """
    if task.monetary_value >= HIGH_VALUE_THRESHOLD and not strong_candidate:
        verdict.add(
            f"High monetary value task: ${task.monetary_value:,.0f}",
            EscalationUrgency.URGENT,
            "Supervisor approval recommended for high-value case",
        )


def _check_overloaded_workforce(
    all_rankings: List[CandidateRanking],
    verdict: EscalationVerdict,
) -> None:
    if not all_rankings:
        return

    overloaded = [
        ranking
        for ranking in all_rankings
        if ranking.utilization_percent >= OVERLOADED_UTILIZATION_THRESHOLD
    ]

    if len(overloaded) == len(all_rankings):
        verdict.add(
            "All candidates are overloaded",
            EscalationUrgency.URGENT,
            "Rebalance workload or defer assignment",
        )


def _check_risk_flags(task: Task, verdict: EscalationVerdict) -> None:
    for flag in task.risk_flags:
        if flag.severity == FlagSeverity.CRITICAL:
            verdict.add(
                f"Critical risk flag: '{flag.label}'",
                EscalationUrgency.IMMEDIATE,
                "Immediate escalation required",
            )
        elif flag.severity == FlagSeverity.HIGH:
            verdict.add(
                f"High-severity risk flag: '{flag.label}'",
                EscalationUrgency.URGENT,
                "Risk owner review recommended",
            )


def _check_vip_customer(
    task: Task,
    verdict: EscalationVerdict,
    *,
    strong_candidate: bool,
) -> None:
    """
    VIP should not auto-escalate when routing confidence is already solid.
    """
    if _customer_tier_value(task) == CustomerTier.VIP.value and not strong_candidate:
        verdict.add(
            "VIP customer task requires careful handling",
            EscalationUrgency.MODERATE,
            "Consider senior-owner validation",
        )


def _check_sla_jeopardy(
    task: Task,
    verdict: EscalationVerdict,
    *,
    strong_candidate: bool,
) -> None:
    """
    SLA risk becomes urgent if no strong candidate is available.
    If a strong candidate exists, assignment may still be safe.
    """
    if task.is_sla_at_risk() and not strong_candidate:
        verdict.add(
            f"SLA jeopardy: {task.hours_until_due():.1f}h left vs {task.estimated_effort:.1f}h effort",
            EscalationUrgency.URGENT,
            "Fast-track supervisor attention",
        )


def _check_repeated_reassignment(task: Task, verdict: EscalationVerdict) -> None:
    if task.reassignment_count >= REPEATED_REASSIGNMENT_LIMIT:
        verdict.add(
            "Repeated reassignment detected",
            EscalationUrgency.URGENT,
            "Investigate ownership ambiguity or workflow friction",
        )


def _check_ambiguous_metadata(task: Task, verdict: EscalationVerdict) -> None:
    description = task.description.strip() if task.description else ""
    if len(description) < VERY_SHORT_DESCRIPTION_THRESHOLD:
        verdict.add(
            "Very limited task description",
            EscalationUrgency.LOW,
            "Request more task context if needed",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_escalation(
    task: Task,
    all_rankings: List[CandidateRanking],
    qualified_rankings: List[CandidateRanking],
) -> EscalationVerdict:
    """
    Escalation policy:
    - Always escalate for truly critical risk/compliance issues
    - Escalate for weak/no candidate availability
    - Avoid unnecessary escalation when a strong candidate already exists
    """
    verdict = EscalationVerdict()
    strong_candidate = _has_strong_candidate(task, qualified_rankings)

    # -----------------------------------------------------------------------
    # Always-critical triggers
    # -----------------------------------------------------------------------
    _check_compliance_and_policy_flags(task, verdict)
    _check_risk_flags(task, verdict)

    # -----------------------------------------------------------------------
    # Structural assignment risk
    # -----------------------------------------------------------------------
    if not strong_candidate:
        _check_no_eligible_candidates(qualified_rankings, verdict)
        _check_overloaded_workforce(all_rankings, verdict)
        _check_repeated_reassignment(task, verdict)

    # -----------------------------------------------------------------------
    # Context-sensitive escalation
    # -----------------------------------------------------------------------
    _check_high_monetary_value(task, verdict, strong_candidate=strong_candidate)
    _check_sla_jeopardy(task, verdict, strong_candidate=strong_candidate)
    _check_low_confidence(qualified_rankings, task, verdict)
    _check_vip_customer(task, verdict, strong_candidate=strong_candidate)
    _check_ambiguous_metadata(task, verdict)

    return verdict