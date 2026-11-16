"""MOCK Delegation Agent — replace with real DA in Sprint 6."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from agent.schemas import ActionRecommendation

if TYPE_CHECKING:
    from ..orchestrator import SharedWorkflowState


def delegation_node(state: "SharedWorkflowState") -> "SharedWorkflowState":
    """Assigns each task in the IAA task_list to a mock role based on action keywords."""
    rec: Optional[ActionRecommendation] = state.get("iaa_recommendation")
    task_list = rec.task_list if rec else []

    def _assign_role(action: str) -> str:
        a = action.lower()
        if "escalat" in a:
            return "senior_reviewer"
        if "document" in a or "doc" in a:
            return "document_analyst"
        if "approv" in a:
            return "manager"
        if "notify" in a or "alert" in a:
            return "coordinator"
        return "general_analyst"

    assigned_tasks = [
        {
            "task_id":     t.task_id,
            "action":      t.action,
            "assigned_to": _assign_role(t.action),
            "priority":    t.priority,
        }
        for t in task_list
    ]

    delegation_output = {"assigned_tasks": assigned_tasks}
    return {**state, "delegation_output": delegation_output, "workflow_complete": True}
