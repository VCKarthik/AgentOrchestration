"""
contracts.py — Slim per-agent input contracts.

Phase 1 of the surgical refactor: each agent receives only what it needs,
not the full ~500-line AmpState. Keeps Gemini prompts small (the IAA latency fix)
and makes inter-agent dependencies explicit.

Builders live in shims.py (build_csa_input, build_rra_input, ...). HTTP wiring
lives in tools.py.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CaseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    case_type: str
    priority: str
    due_date: Optional[str] = None
    title: str
    description: str
    requester: str
    business_domain: str


class CSAInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case: CaseMetadata


class RRAInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case: CaseMetadata
    context_validation: dict
    document_count: int
    case_history_count: int


class IAAInput(BaseModel):
    """Slim input for IAA — last-5 events, last-3 emails, no bodies."""
    model_config = ConfigDict(extra="forbid")
    case: CaseMetadata
    case_history_summary: list[dict] = Field(default_factory=list)
    recent_communications: list[dict] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    governance_decision: Optional[str] = None
    requires_approval: bool = False
    operating_context: str = "full"


class GPAInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case: CaseMetadata
    risk_flags: list[str] = Field(default_factory=list)
    estimated_value: Optional[float] = None


class DAInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case: CaseMetadata
    iaa_recommended_action: dict
    risk_level: str
    governance_decision: str
    requires_approval: bool = False
    escalate_flags: dict = Field(default_factory=dict)


class SWAInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_history_events: list[dict]
    window_days: int = 30
