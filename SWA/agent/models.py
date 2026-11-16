"""
Pydantic schemas for structured I/O. This is the CONTRACT that other agents
and the orchestrator work against.
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── INCOMING EVENT (from other agents) ────────────────────────────

class IncomingEvent(BaseModel):
    """What other agents send to Shadow Work's logging tool."""
    event_id: str
    case_id: str
    timestamp: datetime
    actor_id: str
    actor_type: Literal["agent", "human"]
    action_type: str
    target_entity: str
    target_entity_type: str
    parent_task_id: Optional[str] = None
    context_payload: dict[str, Any] = Field(default_factory=dict)
    outcome: Literal["success", "pending", "failed"]


class IncomingCase(BaseModel):
    """Case metadata, written when a case opens."""
    case_id: str
    case_type: str
    status: Literal["open", "in_progress", "closed"]
    created_at: datetime
    closed_at: Optional[datetime] = None
    domain_metadata: dict[str, Any] = Field(default_factory=dict)


# ── CASE PORTFOLIO (Module 1 output) ──────────────────────────────

class CaseTimelineEntry(BaseModel):
    timestamp: datetime
    actor_id: str
    actor_type: str
    action_type: str
    target_entity: str
    outcome: str


class CasePortfolio(BaseModel):
    """
    Full history view of a single case — the 'case sheet' Ankit asked for.
    """
    case_id: str
    case_type: str
    status: str
    total_events: int
    distinct_actors: int
    distinct_actions: int
    case_duration_hours: Optional[float]
    timeline: list[CaseTimelineEntry]
    action_counts: dict[str, int]       # action_type -> count
    actor_counts: dict[str, int]        # actor_id -> count
    target_counts: dict[str, int]       # target_entity -> count


# ── ANALYSIS OUTPUT (Module 2 output) ─────────────────────────────

class PatternSignature(BaseModel):
    pattern_type: str
    action_type: str
    target_entity_type: str


class TemporalSignature(BaseModel):
    mean_interval_hours: float
    stddev_interval_hours: float
    regularity_score: float


class AutomationRecommendation(BaseModel):
    type: str
    trigger: str
    action: str
    estimated_time_saved_per_week_hours: Optional[float] = None


class Finding(BaseModel):
    finding_id: str
    detector_source: str              # which detector produced this
    pattern_type: str
    pattern_signature: str
    occurrences: int
    actors_involved: list[str]
    cases_involved: list[str]         # which cases this pattern spans
    temporal_signature: TemporalSignature
    description: str
    domain_contextualized_description: Optional[str] = None
    automation_recommendation: AutomationRecommendation
    confidence: float
    risk_level: Literal["low", "medium", "high"]
    decision: Literal["recommend", "watch", "escalate"]
    requires_human_approval: bool
    evidence_event_ids: list[str]


class Escalation(BaseModel):
    escalation_id: str
    reason: str
    pattern_signature: str
    occurrences: int
    recommended_human_role: str
    summary_for_human: str
    evidence_event_ids: list[str]


class AnalysisWindow(BaseModel):
    start: datetime
    end: datetime
    events_processed: int


class RunMetrics(BaseModel):
    patterns_detected: int
    recommendations_made: int
    escalations_raised: int
    events_processed: int
    processing_time_ms: float
    detectors_used: list[str]


class AgentOutput(BaseModel):
    agent: Literal["shadow_work"] = "shadow_work"
    run_id: str
    timestamp: datetime
    scope: str                        # "global" or "case:<case_id>"
    trigger_type: str
    window_analyzed: AnalysisWindow
    case_portfolios: list[CasePortfolio] = Field(default_factory=list)
    findings: list[Finding]
    escalations: list[Escalation]
    metrics: RunMetrics
