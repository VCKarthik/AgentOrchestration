"""
schemas.py
Universal input and output schemas for the IAA.

Design decisions:
- EventLog is the universal intake format — maps from BPIC, CUAD, or any client event log
- ProcessState is what the IAA actually reasons over — built from EventLog at runtime
- ActionRecommendation is the structured output — always the same shape regardless of domain
- All fields use generic names — no domain-specific labels anywhere in this file
"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ── Universal event log entry (one row from any source) ──────────────────────

class EventLogEntry(BaseModel):
    """
    One event in a process log. Flexible enough to accept BPIC-style XES data,
    CUAD contract events, or any custom client log via column mapping config.
    """
    event_id: str = Field(..., description="Unique identifier for this event")
    entity_id: str = Field(..., description="The case, claim, contract, or task this event belongs to")
    event_type: str = Field(..., description="What happened — e.g. 'document_uploaded', 'approval_requested'")
    stage: str = Field(..., description="Where in the process this happened — e.g. 'verification', 'review'")
    timestamp: datetime = Field(..., description="When this event occurred")
    actor: Optional[str] = Field(None, description="Who or what performed this event — resource ID or role")
    outcome: Optional[str] = Field(None, description="Result of this event if known — 'approved', 'rejected', etc.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Any domain-specific fields — amount, priority, etc.")


# ── Structured prior action step ─────────────────────────────────────────────

class ProcessStep(BaseModel):
    """
    A single structured step from the process history.
    Richer than a plain string — includes actor and timestamp for grounding.
    """
    event_type: str = Field(..., description="What happened at this step")
    actor: Optional[str] = Field(None, description="Who performed this step — role label or resource ID")
    timestamp: Optional[datetime] = Field(None, description="When this step occurred")
    outcome: Optional[str] = Field(None, description="Outcome of this step if known")


# ── Process state (what the IAA reasons over) ────────────────────────────────

class ProcessState(BaseModel):
    """
    The current state of a process instance, assembled from its event history.
    This is the primary input to the IAA chain.
    All domain-specific meaning comes from the event data itself, not from this schema.
    """
    entity_id: str
    current_stage: str
    current_event_type: str
    prior_actions: list[str] = Field(default_factory=list, description="Ordered list of prior event_types")
    prior_steps: list[ProcessStep] = Field(
        default_factory=list,
        description="Structured prior actions with actor and timestamp — populated when available"
    )
    actor: Optional[str] = None
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Optional upstream agent outputs — all nullable, IAA degrades gracefully
    context_summary: Optional[str] = Field(None, description="Summary from Context Stitching Agent if available")
    risk_flags: list[str] = Field(default_factory=list, description="Flags from Risk Radar Agent if available")
    risk_severity: Optional[str] = Field(None, description="low / medium / high / critical — from Risk Radar if available")
    policy_constraints: list[str] = Field(default_factory=list, description="Active constraints from Governance Agent if available")
    assigned_owner: Optional[str] = Field(None, description="Assigned owner from Delegation Agent if available")

    # Derived at build time
    operating_context: str = Field("full", description="'full' or 'partial — <missing agents>'")


# ── Task item for Delegation Agent ───────────────────────────────────────────

class TaskItem(BaseModel):
    """
    A single actionable task destined for the Delegation Agent.
    """
    task_id: str = Field(..., description="Unique identifier for this task — e.g. 'T001'")
    action: str = Field(..., description="Snake_case action identifier for this task")
    assigned_role: Optional[str] = Field(None, description="Role label for Delegation Agent to consume")
    priority: str = Field("medium", description="Task priority — high / medium / low")
    depends_on: list[str] = Field(default_factory=list, description="task_ids this task depends on")
    reasoning: str = Field(..., description="Why this task is included")


# ── Workflow step for timeline ────────────────────────────────────────────────

class WorkflowStep(BaseModel):
    """
    One step in the chronological workflow timeline — Ankit requirement.
    """
    step: int = Field(..., description="Ordinal position in the workflow")
    event_type: str = Field(..., description="Event type label for this step")
    actor: Optional[str] = Field(None, description="Role or resource responsible for this step")
    status: str = Field(..., description="'completed' | 'current' | 'predicted'")
    timestamp: Optional[datetime] = Field(None, description="Timestamp if known — null for predicted steps")


# ── Output schema (what IAA always returns) ───────────────────────────────────

class PredictedAction(BaseModel):
    action_id: str = Field(..., description="Unique identifier for this action — e.g. 'request_document'")
    label: str = Field(..., description="Human-readable label — e.g. 'Request missing document'")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    reasoning: str = Field(..., description="Why this action was predicted")


class ActionRecommendation(BaseModel):
    """
    The structured output of the IAA. Always the same shape regardless of domain.
    Consumed by the LangGraph orchestrator for routing decisions.
    """
    predicted_actions: list[PredictedAction] = Field(
        ..., min_length=1, max_length=3,
        description="Top 1-3 predicted next actions, ranked by confidence"
    )
    recommended_action: PredictedAction = Field(
        ..., description="The single highest-confidence action to surface to the user or orchestrator"
    )
    override_applied: bool = Field(False, description="True if a hard rule fired and overrode LLM output")
    override_reason: Optional[str] = Field(None, description="Explanation of which rule fired, if override_applied")
    retrieved_context_ids: list[str] = Field(
        default_factory=list, description="IDs of vector store chunks used for retrieval — for audit"
    )
    escalate_to_human: bool = Field(False, description="True if human review is required before proceeding")
    operating_context: str = Field("full", description="Passed through from ProcessState for audit logging")
    model_used: str = Field("gemini-2.5-flash", description="LLM provider used for this invocation")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    task_list: list[TaskItem] = Field(
        default_factory=list,
        description="Structured task list for Delegation Agent to consume"
    )
    workflow_timeline: list[WorkflowStep] = Field(
        default_factory=list,
        description="Chronological flowchart of case start-to-end — Ankit requirement"
    )


# ── LangGraph state keys (integration contract for AITS) ─────────────────────

class IAAState(BaseModel):
    """
    The IAA's view of the LangGraph shared state.
    Keys prefixed with iaa_ are owned by the IAA and written only by it.
    All other keys are read-only from the IAA's perspective.

    Hand this class definition to the AITS team as the integration contract.
    They add these keys to their existing AgentState TypedDict.
    """
    # Input keys the IAA reads (populated by upstream agents or orchestrator)
    process_state: Optional[ProcessState] = None

    # Output keys the IAA writes
    iaa_recommendation: Optional[ActionRecommendation] = None
    iaa_routing_action: Optional[str] = None  # top action_id — used by orchestrator for conditional edges
    iaa_escalate: bool = False                 # shortcut flag — orchestrator reads this for approval gate
