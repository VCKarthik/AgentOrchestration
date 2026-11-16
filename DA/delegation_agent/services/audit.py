"""
services/audit.py
-----------------
Builds structured AuditLog entries from pipeline metadata and persists
them via the AuditRepository.  Every delegation evaluation produces exactly
one audit record — regardless of outcome — for compliance and traceability.
"""

from __future__ import annotations

from typing import List

from ..models.outputs import AssignmentDecision, AuditLog
from ..repositories.audit_repository import AuditRepository


class AuditService:
    """
    Service responsible for creating and storing delegation audit records.

    Designed to be injected into the DelegationAgent; can be swapped for a
    database-backed or event-streaming implementation in production.
    """

    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    def record(
        self,
        decision: AssignmentDecision,
        pipeline_meta: dict,
        triggered_by: str = "orchestrator",
    ) -> AuditLog:
        """
        Build and persist an AuditLog entry for a completed delegation run.

        Args:
            decision:      The final AssignmentDecision produced by the pipeline.
            pipeline_meta: Metadata dict returned alongside the decision by the pipeline.
            triggered_by:  Identifier of the caller (system name or user ID).

        Returns:
            The persisted AuditLog instance.
        """
        log = AuditLog(
            task_id=decision.task_id,
            assignment_id=decision.assignment_id,
            triggered_by=triggered_by,
            decision=decision,
            candidates_evaluated=pipeline_meta.get("total_candidates_evaluated", 0),
            candidates_filtered_out=pipeline_meta.get("candidates_filtered_out", 0),
            rules_applied=pipeline_meta.get("rules_applied", []),
            escalation_triggers_checked=pipeline_meta.get("escalation_triggers_checked", []),
            processing_time_ms=pipeline_meta.get("processing_time_ms"),
            warnings=pipeline_meta.get("warnings", []),
            errors=pipeline_meta.get("errors", []),
        )

        self._repo.save(log)
        return log

    def get_history(self, task_id: str) -> List[AuditLog]:
        """Retrieve all audit records for a task (useful for reassignment tracking)."""
        return self._repo.get_by_task_id(task_id)

    def get_all(self) -> List[AuditLog]:
        """Return all audit records stored in the repository."""
        return self._repo.get_all()

    def summary(self) -> str:
        """Return a compact text summary of all stored audit records."""
        logs = self.get_all()
        if not logs:
            return "No audit records found."
        lines = [f"Audit Log Summary ({len(logs)} record(s)):"]
        for log in logs:
            status = log.decision.status
            lines.append(
                f"  [{log.timestamp.strftime('%H:%M:%S')}] "
                f"Task={log.task_id} | "
                f"Status={status} | "
                f"Assignee={log.decision.selected_assignee or 'N/A'} | "
                f"Confidence={log.decision.confidence_score:.1f}% | "
                f"Audit={log.audit_log_id}"
            )
        return "\n".join(lines)
