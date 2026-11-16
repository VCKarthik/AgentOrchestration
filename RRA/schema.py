"""
Risk Radar Agent — Output Schema

Dataclass-based models that lock in the Sprint 4 output contract as code.
Zero external dependencies — just stdlib. Every field from the Sprint 4
spec is present; schema is stable even when upstream context is partial.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------- Enums ----------

class RiskType(str, Enum):
    MISSING_INPUT = "missing_input"
    DEADLINE_RISK = "deadline_risk"
    DEPENDENCY_RISK = "dependency_risk"
    COMPLIANCE_RISK = "compliance_risk"
    HISTORICAL_DELAY = "historical_delay"
    COORDINATION_RISK = "coordination_risk"
    AMBIGUITY_RISK = "ambiguity_risk"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"low": 1, "medium": 2, "high": 3, "critical": 4}[self.value]


class ProceedDecision(str, Enum):
    PROCEED = "proceed"
    CAUTION = "caution"
    HOLD = "hold"


class OperatingContext(str, Enum):
    FULL = "full"
    PARTIAL = "partial"


# ---------- Helpers ----------

def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse ISO 8601 datetimes, tolerating 'Z' suffix."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise TypeError(f"Cannot parse datetime from {value!r}")


def _serialize(obj: Any) -> Any:
    """Recursive JSON-safe serializer for our dataclass outputs."""
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    return obj


# ---------- Input: Case payload from orchestrator ----------

@dataclass
class CaseInput:
    """
    Structured case data handed to Risk Radar by the orchestrator
    after Context Stitching has assembled the packet.

    Any field may be None (partial context); rules handle absence gracefully.
    """
    task_id: str
    workflow_type: str
    workflow_state: str
    priority: Optional[str] = None

    # Timing
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    due_date: Optional[datetime] = None
    sla_deadline: Optional[datetime] = None

    # Completeness
    required_inputs: List[str] = field(default_factory=list)
    received_inputs: List[str] = field(default_factory=list)
    mandatory_inputs: List[str] = field(default_factory=list)

    # Dependencies
    dependency_status: Optional[str] = None
    blocker_flag: bool = False

    # Stakeholder / policy
    stakeholder_priority: Optional[str] = None
    policy_flag: bool = False

    # History
    prior_delay_count: int = 0
    prior_escalation_count: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CaseInput":
        """Construct from raw JSON dict, parsing timestamps."""
        allowed = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in allowed}
        for dt_field in ("created_at", "last_updated", "due_date", "sla_deadline"):
            if dt_field in clean:
                clean[dt_field] = _parse_dt(clean[dt_field])
        return cls(**clean)


# ---------- Output: Risk Radar result ----------

@dataclass
class RiskItem:
    risk_type: RiskType
    severity: Severity
    reason: str
    blocking: bool = False


@dataclass
class RiskRadarOutput:
    """Sprint 4 output schema — fields always present, stable shape."""

    task_id: str
    workflow_state: str
    priority: Optional[str] = None

    risk_items: List[RiskItem] = field(default_factory=list)
    overall_risk_level: Severity = Severity.LOW
    can_proceed: ProceedDecision = ProceedDecision.PROCEED

    escalate_to_human: bool = False
    escalation_target: Optional[str] = None

    reasoning_summary: str = ""

    operating_context: OperatingContext = OperatingContext.FULL
    model_used: str = "rules-plus-llm-summary"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def risk_detected(self) -> bool:
        return len(self.risk_items) > 0

    def to_dict(self) -> Dict[str, Any]:
        return _serialize(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
