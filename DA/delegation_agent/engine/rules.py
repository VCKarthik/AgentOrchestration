"""
engine/rules.py
---------------
Hard business rules applied AFTER scoring to accept, penalise, or
disqualify candidates.

This module is intentionally stricter than scoring, but lighter than
full escalation logic:
- scoring decides who is best
- rules decide who is eligible
- escalation decides when human oversight is required
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..models.assignee import Assignee
from ..models.outputs import CandidateRanking
from ..models.task import FlagSeverity, Task

# ---------------------------------------------------------------------------
# Configurable rule thresholds
# ---------------------------------------------------------------------------

HARD_UTILIZATION_CEILING: float = 95.0
HIGH_VALUE_THRESHOLD: float = 150_000.0
REPEATED_REASSIGNMENT_LIMIT: int = 2


# ---------------------------------------------------------------------------
# Individual rule checkers
# ---------------------------------------------------------------------------

def rule_utilization_ceiling(
    assignee: Assignee,
) -> Tuple[bool, Optional[str]]:
    """
    HARD: Reject candidates at or above the utilization hard ceiling.
    """
    if assignee.utilization_percent >= HARD_UTILIZATION_CEILING:
        return False, (
            f"Utilization {assignee.utilization_percent:.0f}% exceeds hard ceiling "
            f"of {HARD_UTILIZATION_CEILING:.0f}%"
        )
    return True, None


def rule_availability_status(
    assignee: Assignee,
) -> Tuple[bool, Optional[str]]:
    """
    HARD: Reject candidates who are out of office or on leave.
    """
    blocked_statuses = {"out_of_office", "on_leave"}
    status = (
        assignee.availability_status
        if isinstance(assignee.availability_status, str)
        else assignee.availability_status.value
    )
    if status in blocked_statuses:
        return False, f"Assignee is currently '{status}' and unavailable"
    return True, None


def rule_required_skills_present(
    assignee: Assignee,
    task: Task,
) -> Tuple[bool, Optional[str]]:
    """
    CONDITIONAL HARD RULE:
    If the task is high/critical priority and the assignee covers none of the
    required skills, disqualify.

    For medium/low priority tasks, allow zero-match candidates to remain as
    fallback options and let scoring push them down the ranking.
    """
    required = [s.lower() for s in task.required_skills]
    if not required:
        return True, None

    assignee_skills = set(assignee.skill_names())
    matched = [r for r in required if r in assignee_skills]

    priority_str = task.priority if isinstance(task.priority, str) else task.priority.value
    if not matched and priority_str in {"high", "critical"}:
        missing = ", ".join(task.required_skills)
        return False, f"Assignee has none of the required skills: [{missing}]"

    return True, None


def rule_high_value_seniority(
    assignee: Assignee,
    task: Task,
) -> Tuple[bool, Optional[str]]:
    """
    SOFTENED RULE:
    High-value tasks are handled primarily through scoring and escalation.
    We do not disqualify here.
    """
    return True, None


def rule_vip_customer_handling(
    assignee: Assignee,
    task: Task,
) -> Tuple[bool, Optional[str]]:
    """
    SOFTENED RULE:
    VIP handling is primarily enforced through scoring/escalation rather than
    outright disqualification here.
    """
    return True, None


def rule_critical_compliance_flags(task: Task) -> Tuple[bool, str]:
    """
    TASK-LEVEL RULE:
    Critical compliance or policy flags mandate escalation.
    Returns (requires_escalation, reason).
    """
    for flag in task.compliance_flags:
        if flag.severity == FlagSeverity.CRITICAL:
            return True, f"Critical compliance: {flag.label}"

    for flag in task.policy_flags:
        if flag.severity == FlagSeverity.CRITICAL:
            return True, f"Critical policy: {flag.label}"

    return False, ""


def rule_critical_risk_flags(task: Task) -> Tuple[bool, str]:
    """
    TASK-LEVEL RULE:
    Critical risk flags mandate escalation.
    Returns (requires_escalation, reason).
    """
    for flag in task.risk_flags:
        if flag.severity == FlagSeverity.CRITICAL:
            return True, f"Critical risk: {flag.label}"

    return False, ""


# ---------------------------------------------------------------------------
# Public API: apply all candidate-level hard rules
# ---------------------------------------------------------------------------

def apply_hard_rules(
    ranking: CandidateRanking,
    assignee: Assignee,
    task: Task,
) -> CandidateRanking:
    """
    Apply candidate-level hard rules to a CandidateRanking entry.

    Mutates the ranking object in-place:
    - sets hard_rule_passed = False
    - sets disqualification_reason on the first failure
    """
    checkers = [
        lambda: rule_utilization_ceiling(assignee),
        lambda: rule_availability_status(assignee),
        lambda: rule_required_skills_present(assignee, task),
        lambda: rule_high_value_seniority(assignee, task),
        lambda: rule_vip_customer_handling(assignee, task),
    ]

    for check in checkers:
        passed, reason = check()
        if not passed:
            ranking.hard_rule_passed = False
            ranking.disqualification_reason = reason
            return ranking

    ranking.hard_rule_passed = True
    ranking.disqualification_reason = None
    return ranking


def filter_qualified_candidates(
    rankings: List[CandidateRanking],
) -> List[CandidateRanking]:
    """
    Return only candidates that passed all hard rules.
    """
    return [r for r in rankings if r.hard_rule_passed]


def check_task_level_escalation_rules(task: Task) -> Tuple[bool, str]:
    """
    Evaluate task-level rules that mandate escalation regardless of candidates.
    Returns (escalate, reason).
    """
    for rule_fn in (rule_critical_compliance_flags, rule_critical_risk_flags):
        escalate, reason = rule_fn(task)
        if escalate:
            return True, reason

    if task.monetary_value >= HIGH_VALUE_THRESHOLD:
        return True, f"High-value task (${task.monetary_value:,.0f})"

    if task.reassignment_count >= REPEATED_REASSIGNMENT_LIMIT:
        return True, (
            f"Task has been reassigned {task.reassignment_count} time(s) — "
            "team lead review required"
        )

    return False, ""
