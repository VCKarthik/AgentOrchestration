from __future__ import annotations

import time
from typing import List, Tuple

from .escalation import evaluate_escalation
from .rules import (
    apply_hard_rules,
    check_task_level_escalation_rules,
    filter_qualified_candidates,
)
from .scoring import rank_candidates

from ..models.assignee import Assignee, AvailabilityStatus
from ..models.outputs import (
    AssignmentDecision,
    AssignmentStatus,
    ExecutionChannel,
    OwnerType,
    EscalationUrgency,
)
from ..models.task import Task
from ..repositories.assignee_repository import AssigneeRepository
from ..repositories.bandwidth_repository import BandwidthRepository


MINIMUM_CONFIDENCE_SCORE: float = 60.0


def _estimate_task_hours(description: str) -> int:
    """Estimate task hours based on description length."""
    words = len(description.split())
    return max(1, words // 50)


# -------------------------
# Stage 1: Validation
# -------------------------
def stage_validate_input(task: Task) -> List[str]:
    warnings: List[str] = []

    if not task.required_skills:
        warnings.append("No required skills specified")

    if len(task.description.strip()) < 30:
        warnings.append("Task description is too short")

    if task.estimated_effort <= 0:
        warnings.append("Estimated effort invalid")

    return warnings


# -------------------------
# Stage 2: Channel Decision
# -------------------------
def stage_decide_channel(task: Task) -> dict:
    """
    Decide execution channel before human ranking.

    Delegation Agent decides the best ownership / execution channel.
    Orchestrator remains responsible for multi-agent workflow sequencing.
    """

    # 1. Critical flags -> supervisor review
    if task.has_critical_flags():
        return {
            "channel": ExecutionChannel.SUPERVISOR_REVIEW,
            "owner_type": OwnerType.QUEUE,
            "owner": {
                "queue_id": "lead-review-queue",
                "name": "Lead Review Queue",
            },
            "confidence": 95.0,
            "reasons": ["Critical flags require supervisor review"],
        }

    # 2. High-value tasks -> supervisor review
    if task.monetary_value >= 100_000:
        return {
            "channel": ExecutionChannel.SUPERVISOR_REVIEW,
            "owner_type": OwnerType.QUEUE,
            "owner": {
                "queue_id": "finance-review-queue",
                "name": "Finance Review Queue",
            },
            "confidence": 90.0,
            "reasons": ["High-value task requires supervisor approval"],
        }

    # 3. Simple, repetitive, low-risk tasks -> automation
    if (
        str(task.task_type) == "customer_inquiry"
        and not task.has_critical_flags()
        and task.monetary_value == 0
    ):
        return {
            "channel": ExecutionChannel.AUTOMATION,
            "owner_type": OwnerType.SYSTEM,
            "owner": {
                "system_id": "workflow_automation",
                "name": "Automation Engine",
            },
            "confidence": 80.0,
            "reasons": ["Low-risk repetitive task suitable for automation"],
        }

    # 4. Specialized domains -> specialized agent
    if str(task.business_domain).lower() in {"risk", "compliance"}:
        return {
            "channel": ExecutionChannel.SPECIALIZED_AGENT,
            "owner_type": OwnerType.AGENT,
            "owner": {
                "agent_id": "risk_radar_agent",
                "name": "Risk Radar Agent",
            },
            "confidence": 82.0,
            "reasons": ["Specialized domain requires expert agent"],
        }

    # 5. Default -> human owner
    return {
        "channel": ExecutionChannel.HUMAN_OWNER,
        "owner_type": OwnerType.HUMAN,
        "owner": None,
        "confidence": 75.0,
        "reasons": ["Requires human decision-making"],
    }


# -------------------------
# Stage 3: Retrieve Human Candidates
# -------------------------
def stage_retrieve_candidates(task: Task, repo: AssigneeRepository) -> List[Assignee]:
    return repo.get_all()


# -------------------------
# Stage 4: Filter basic constraints
# -------------------------
def stage_filter_candidates(
    assignees: List[Assignee],
    task: Task,
) -> Tuple[List[Assignee], List[str]]:
    notes: List[str] = []
    blocked = {
        AvailabilityStatus.OUT_OF_OFFICE.value,
        AvailabilityStatus.ON_LEAVE.value,
    }

    filtered: List[Assignee] = []

    for a in assignees:
        status = (
            a.availability_status.value
            if hasattr(a.availability_status, "value")
            else a.availability_status
        )

        if status in blocked:
            notes.append(f"{a.name} blocked due to {status}")
        else:
            filtered.append(a)

    return filtered, notes


# -------------------------
# Stage 5: Bandwidth filter
# -------------------------
def stage_bandwidth_filter(
    assignees: List[Assignee],
    task_hours: int,
    bandwidth_repo: BandwidthRepository,
) -> List[Assignee]:
    feasible: List[Assignee] = []

    for a in assignees:
        available = bandwidth_repo.get_available_hours(a.assignee_id)
        if available >= task_hours:
            feasible.append(a)

    return feasible


# -------------------------
# Stage 6: Scoring
# -------------------------
def stage_score_candidates(assignees: List[Assignee], task: Task):
    return rank_candidates(assignees, task)


# -------------------------
# Stage 7: Hard rules
# -------------------------
def stage_apply_hard_rules(rankings, assignees, task):
    assignee_map = {a.assignee_id: a for a in assignees}

    annotated = []

    for r in rankings:
        assignee = assignee_map.get(r.assignee_id)
        if assignee:
            apply_hard_rules(r, assignee, task)
        annotated.append(r)

    qualified = filter_qualified_candidates(annotated)
    return annotated, qualified


# -------------------------
# Stage 8: Escalation
# -------------------------
def stage_detect_escalation(task, all_rankings, qualified_rankings):
    escalate, reason = check_task_level_escalation_rules(task)
    verdict = evaluate_escalation(task, all_rankings, qualified_rankings)

    if escalate and reason:
        verdict.add(reason, urgency=EscalationUrgency.URGENT)

    return verdict


# -------------------------
# Stage 9: Build Decision
# -------------------------
def stage_build_decision(
    task,
    all_rankings,
    qualified_rankings,
    escalation_verdict,
    warnings,
    channel_decision,
):
    selected_channel = channel_decision["channel"]
    selected_owner_type = channel_decision["owner_type"]

    reasons = list(warnings) + list(channel_decision["reasons"])
    selected_assignee = None
    selected_owner = None
    status = AssignmentStatus.UNASSIGNED
    confidence_score = 0.0

    if escalation_verdict.should_escalate:
        status = AssignmentStatus.ESCALATED
        reasons.extend(escalation_verdict.reasons)

    elif qualified_rankings:
        best = qualified_rankings[0]
        confidence_score = best.composite_score

        if confidence_score >= MINIMUM_CONFIDENCE_SCORE:
            status = AssignmentStatus.ASSIGNED

            selected_assignee = {
                "assignee_id": best.assignee_id,
                "name": best.name,
                "role": best.role,
            }
            selected_owner = selected_assignee

            reasons.append(f"Assigned to {best.name}")
        else:
            status = AssignmentStatus.REVIEW_REQUIRED
            reasons.append("Low confidence score")

    else:
        reasons.append("No valid candidates")

    return AssignmentDecision(
        task_id=task.task_id,
        status=status,
        confidence_score=round(confidence_score, 2),
        reasons=reasons,
        selected_channel=selected_channel,
        selected_owner_type=selected_owner_type,
        selected_owner=selected_owner,
        selected_assignee=selected_assignee,
        candidate_rankings=all_rankings,
        escalation_required=escalation_verdict.should_escalate,
        escalation_reason=escalation_verdict.primary_reason,
        escalation_urgency=escalation_verdict.urgency,
        orchestrator_action="invoke_selected_owner",
    )


# -------------------------
# Pipeline
# -------------------------
class DelegationPipeline:
    def __init__(self, repo: AssigneeRepository):
        self.repo = repo
        self.bandwidth_repo = BandwidthRepository()

    def run(self, task: Task) -> Tuple[AssignmentDecision, dict]:
        start = time.perf_counter()

        meta = {
            "stages": [],
            "task_hours": 0,
        }

        # Step 1: Validate
        warnings = stage_validate_input(task)
        meta["stages"].append("validate")

        # Step 2: Decide channel
        channel_decision = stage_decide_channel(task)
        meta["stages"].append("channel")

        # Fast exit for non-human channels
        if channel_decision["channel"] != ExecutionChannel.HUMAN_OWNER:
            decision = AssignmentDecision(
                task_id=task.task_id,
                status=AssignmentStatus.ASSIGNED,
                confidence_score=channel_decision["confidence"],
                reasons=warnings + channel_decision["reasons"],
                selected_channel=channel_decision["channel"],
                selected_owner_type=channel_decision["owner_type"],
                selected_owner=channel_decision["owner"],
                selected_assignee=None,
                candidate_rankings=[],
                escalation_required=False,
                escalation_reason=None,
                escalation_urgency=None,
                orchestrator_action="invoke_selected_owner",
            )

            meta["time_ms"] = round((time.perf_counter() - start) * 1000, 2)
            return decision, meta

        # Human branch only below this point
        assignees = stage_retrieve_candidates(task, self.repo)
        meta["stages"].append("retrieve")

        filtered, notes = stage_filter_candidates(assignees, task)
        warnings.extend(notes)
        meta["stages"].append("filter")

        task_hours = _estimate_task_hours(task.description)
        meta["task_hours"] = task_hours

        filtered = stage_bandwidth_filter(
            filtered,
            task_hours,
            self.bandwidth_repo,
        )
        meta["stages"].append("bandwidth")

        rankings = stage_score_candidates(filtered, task)
        meta["stages"].append("score")

        annotated, qualified = stage_apply_hard_rules(rankings, filtered, task)
        meta["stages"].append("rules")

        escalation = stage_detect_escalation(task, annotated, qualified)
        meta["stages"].append("escalation")

        decision = stage_build_decision(
            task,
            annotated,
            qualified,
            escalation,
            warnings,
            channel_decision,
        )
        meta["stages"].append("decision")

        meta["time_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return decision, meta