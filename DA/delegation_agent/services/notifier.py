"""
services/notifier.py
--------------------
Channel-aware notification service.

Behavior:
- human_owner       -> assignee email + optional supervisor email
- automation        -> system/workflow notification log
- supervisor_review -> supervisor/queue notification
- specialized_agent -> orchestrator/agent handoff notification
- escalated/review  -> escalation alert
"""

from __future__ import annotations

import logging

from ..models.outputs import AssignmentDecision, AssignmentStatus
from ..models.task import Task

logger = logging.getLogger(__name__)


class NotifierService:
    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run

    def dispatch(self, decision: AssignmentDecision, task: Task) -> None:
        status = decision.status if isinstance(decision.status, str) else decision.status.value

        if status in (AssignmentStatus.ESCALATED.value, AssignmentStatus.REVIEW_REQUIRED.value):
            self._send_escalation_alert(decision, task)
            return

        if status == AssignmentStatus.UNASSIGNED.value:
            self._send_escalation_alert(decision, task)
            logger.warning("[NOTIFIER] Task %s left unassigned", task.task_id)
            return

        if status != AssignmentStatus.ASSIGNED.value:
            return

        channel = (
            decision.selected_channel
            if isinstance(decision.selected_channel, str)
            else decision.selected_channel.value
        )

        if channel == "human_owner":
            self._notify_human_owner(decision, task)
            self._notify_supervisor_if_needed(decision, task)
            if task.current_assignee:
                self._notify_previous_owner(decision, task)

        elif channel == "automation":
            self._notify_automation(decision, task)

        elif channel == "supervisor_review":
            self._notify_supervisor_queue(decision, task)

        elif channel == "specialized_agent":
            self._notify_specialized_agent(decision, task)

        else:
            logger.info(
                "[NOTIFIER] No channel-specific notification handler for channel=%s task=%s",
                channel,
                task.task_id,
            )

    def _notify_human_owner(self, decision: AssignmentDecision, task: Task) -> None:
        if not decision.selected_assignee:
            return

        assignee_name = decision.selected_assignee.get("name", "Unknown")
        assignee_id = decision.selected_assignee.get("assignee_id", "")

        subject = f"[{task.priority.upper()}] New Task Assigned: {task.title}"
        body = (
            f"Dear {assignee_name},\n\n"
            f"You have been assigned a new task.\n\n"
            f"Task ID       : {task.task_id}\n"
            f"Title         : {task.title}\n"
            f"Priority      : {task.priority.upper()}\n"
            f"Due Date      : {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Est. Effort   : {task.estimated_effort:.1f} hours\n"
            f"Domain        : {task.business_domain}\n"
            f"Description   : {task.description}\n\n"
            f"Confidence     : {decision.confidence_score:.1f}%\n"
            f"Reason         : {decision.assignment_reason or 'N/A'}\n"
            f"Assignment ID  : {decision.assignment_id}\n"
        )

        self._send_email(
            to=f"{assignee_id}@company.com",
            subject=subject,
            body=body,
        )

    def _notify_supervisor_if_needed(self, decision: AssignmentDecision, task: Task) -> None:
        from ..models.task import CustomerTier, Priority

        priority_str = task.priority if isinstance(task.priority, str) else task.priority.value
        tier_str = task.customer_tier if isinstance(task.customer_tier, str) else task.customer_tier.value

        should_notify = (
            priority_str in (Priority.CRITICAL.value, Priority.HIGH.value)
            or tier_str == CustomerTier.VIP.value
            or (
                decision.decision_factors is not None
                and decision.decision_factors.current_utilization >= 80.0
            )
        )

        if not should_notify:
            return

        assignee_name = (
            decision.selected_assignee.get("name")
            if decision.selected_assignee
            else "N/A"
        )

        subject = f"[SUPERVISOR ALERT] {priority_str.upper()} Task Assigned: {task.title}"
        body = (
            f"A {priority_str.upper()} task was assigned to {assignee_name}.\n\n"
            f"Task ID    : {task.task_id}\n"
            f"Confidence : {decision.confidence_score:.1f}%\n"
            f"Due Date   : {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\n"
        )

        self._send_email("supervisor@company.com", subject, body)

    def _notify_previous_owner(self, decision: AssignmentDecision, task: Task) -> None:
        if not task.current_assignee:
            return

        new_owner = (
            decision.selected_assignee.get("name", "Unknown")
            if decision.selected_assignee
            else "N/A"
        )

        subject = f"Task Reassigned: {task.title}"
        body = (
            f"Task '{task.title}' (ID: {task.task_id}) has been reassigned to {new_owner}.\n\n"
            f"Reason: {', '.join(decision.reasons[:2])}"
        )

        self._send_email(
            to=f"{task.current_assignee}@company.com",
            subject=subject,
            body=body,
        )

    def _notify_automation(self, decision: AssignmentDecision, task: Task) -> None:
        owner = decision.selected_owner or {}
        system_name = owner.get("name", "Automation Engine")

        logger.info(
            "[NOTIFIER DRY-RUN] Automation Trigger → system=%s | task=%s | confidence=%.1f%%",
            system_name,
            task.task_id,
            decision.confidence_score,
        )

    def _notify_supervisor_queue(self, decision: AssignmentDecision, task: Task) -> None:
        owner = decision.selected_owner or {}
        queue_name = owner.get("name", "Supervisor Review Queue")

        subject = f"[SUPERVISOR REVIEW] {task.title}"
        body = (
            f"Task requires supervisor queue handling.\n\n"
            f"Task ID      : {task.task_id}\n"
            f"Queue        : {queue_name}\n"
            f"Priority     : {task.priority.upper()}\n"
            f"Confidence   : {decision.confidence_score:.1f}%\n"
            f"Reason       : {decision.assignment_reason or 'Supervisor review required'}\n"
        )

        self._send_email("supervisor@company.com", subject, body)

    def _notify_specialized_agent(self, decision: AssignmentDecision, task: Task) -> None:
        owner = decision.selected_owner or {}
        agent_name = owner.get("name", "Specialized Agent")

        logger.info(
            "[NOTIFIER DRY-RUN] Agent Handoff → agent=%s | task=%s | confidence=%.1f%%",
            agent_name,
            task.task_id,
            decision.confidence_score,
        )

    def _send_escalation_alert(self, decision: AssignmentDecision, task: Task) -> None:
        urgency = (
            decision.escalation_urgency
            if isinstance(decision.escalation_urgency, str)
            else (decision.escalation_urgency.value if decision.escalation_urgency else "moderate")
        )

        subject = f"[ESCALATION - {urgency.upper()}] Task Requires Review: {task.title}"
        body = (
            f"The Delegation Agent could not safely complete routing without review.\n\n"
            f"Task ID      : {task.task_id}\n"
            f"Title        : {task.title}\n"
            f"Priority     : {task.priority.upper()}\n"
            f"Due Date     : {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Decision     : {decision.status}\n"
            f"Reason       : {decision.escalation_reason or 'N/A'}\n"
            f"Urgency      : {urgency.upper()}\n"
            f"Assignment ID: {decision.assignment_id}\n"
        )

        self._send_email(
            to="escalations@company.com",
            subject=subject,
            body=body,
            urgent=True,
        )

    def _send_email(self, to: str, subject: str, body: str, urgent: bool = False) -> None:
        label = "[URGENT] " if urgent else ""
        if self.dry_run:
            logger.info(
                "[NOTIFIER DRY-RUN] %sEmail → %s | Subject: %s",
                label,
                to,
                subject,
            )
        else:
            logger.info(
                "[NOTIFIER] %sSending email → %s | Subject: %s",
                label,
                to,
                subject,
            )