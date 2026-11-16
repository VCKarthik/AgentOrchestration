from __future__ import annotations

import logging
from typing import Optional

from .engine.stages import DelegationPipeline
from .models.outputs import AssignmentDecision
from .models.task import Task
from .repositories.assignee_repository import AssigneeRepository
from .repositories.audit_repository import AuditRepository
from .services.audit import AuditService
from .services.notifier import NotifierService
from .services.llm_service import LLMService
from .services.llm_router import LLMRouter

logger = logging.getLogger(__name__)


class DelegationAgent:
    """
    Delegation Agent — decides:
    - best execution channel (human / agent / automation / review)
    - best owner inside that channel

    DOES NOT:
    - orchestrate multi-agent workflows
    - sequence agent execution
    """

    def __init__(
        self,
        assignee_repo: Optional[AssigneeRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        notify_dry_run: bool = True,
        triggered_by: str = "orchestrator",
        enable_trace_logging: bool = False,
        enable_llm_reasoning: bool = True,
    ) -> None:
        self.assignee_repo = assignee_repo or AssigneeRepository()
        self.audit_repo = audit_repo or AuditRepository()

        self.triggered_by = triggered_by
        self.enable_trace_logging = enable_trace_logging
        self.enable_llm_reasoning = enable_llm_reasoning

        self._audit_service = AuditService(repo=self.audit_repo)
        self._notifier = NotifierService(dry_run=notify_dry_run)

        self._llm = LLMService() if enable_llm_reasoning else None
        self._llm_router = LLMRouter() if enable_llm_reasoning else None

        self._pipeline = DelegationPipeline(repo=self.assignee_repo)

        logger.info(
            "[DelegationAgent] Initialized | Assignees: %d | Triggered by: %s",
            self.assignee_repo.count(),
            self.triggered_by,
        )

    def evaluate_task(self, task_payload: dict | Task) -> AssignmentDecision:
        task = self._parse_task(task_payload)

        logger.info(
            "[DelegationAgent] Evaluating task %s | Priority: %s | Domain: %s",
            task.task_id,
            task.priority,
            task.business_domain,
        )

        decision, pipeline_meta = self._pipeline.run(task)

        # Keep escalation fields internally consistent
        if not decision.escalation_required:
            decision.escalation_reason = None

        if self.enable_trace_logging:
            logger.debug(
                "[DelegationAgent] Pipeline meta for %s: %s",
                task.task_id,
                pipeline_meta,
            )

        # LLM advisory (non-blocking, human-owner only)
        if (
            self._llm_router is not None
            and decision.selected_channel == "human_owner"
            and decision.selected_assignee is not None
            and decision.candidate_rankings
            and not decision.escalation_required
        ):
            try:
                route_advice = self._llm_router.recommend_assignee(
                    task=task,
                    candidate_rankings=decision.candidate_rankings,
                )

                # Only add LLM router reason if API is actually available
                if self._llm_router.client and route_advice.get("reason"):
                    decision.reasons.append(
                        f"LLM Router: {route_advice['reason']}"
                    )

                # Advisory only: do not override deterministic routing
                recommended_id = route_advice.get("recommended_assignee_id")
                selected_id = decision.selected_assignee.get("assignee_id")

                if (
                    self._llm_router.client
                    and recommended_id
                    and recommended_id != selected_id
                ):
                    decision.reasons.append(
                        f"LLM suggested {recommended_id}, but deterministic policy retained {selected_id}"
                    )

            except Exception as exc:
                logger.warning(
                    "[DelegationAgent] LLM router failed (non-fatal): %s",
                    exc,
                )

        # Optional explanation
        if self._llm is not None:
            try:
                llm_reason = self._llm.generate_reasoning(task, decision)
                if llm_reason:
                    decision.reasons.append(f"LLM Insight: {llm_reason}")
            except Exception as exc:
                logger.warning(
                    "[DelegationAgent] LLM reasoning failed (non-fatal): %s",
                    exc,
                )

        # Audit
        audit_log = self._audit_service.record(
            decision=decision,
            pipeline_meta=pipeline_meta,
            triggered_by=self.triggered_by,
        )
        decision.audit_log_id = audit_log.audit_log_id

        # Notification
        try:
            self._notifier.dispatch(decision=decision, task=task)
        except Exception as exc:
            logger.warning(
                "[DelegationAgent] Notification error (non-fatal): %s",
                exc,
            )

        # Final log
        logger.info(
            "[DelegationAgent] Decision | Task: %s | Channel: %s | Confidence: %.1f%% | Escalation: %s",
            task.task_id,
            decision.selected_channel,
            decision.confidence_score,
            decision.escalation_required,
        )

        return decision

    def _parse_task(self, task_payload: dict | Task) -> Task:
        if isinstance(task_payload, Task):
            return task_payload

        try:
            return Task(**task_payload)
        except Exception as exc:
            logger.error(
                "[DelegationAgent] Task payload validation failed: %s",
                exc,
            )
            raise ValueError(f"Invalid task payload: {exc}") from exc

    def audit_summary(self) -> str:
        return self._audit_service.summary()

    def get_assignee_pool_size(self) -> int:
        return self.assignee_repo.count()