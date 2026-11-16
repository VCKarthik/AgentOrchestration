"""
Risk Radar Agent — Configuration

Thresholds are workflow-agnostic defaults here. In production these would
come from a rules registry per workflow_type. Centralizing them means
Sprint 5 code doesn't hardcode magic numbers.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SLAThresholds:
    """Windows for deadline/SLA risk severity.

    Interpretation: how many hours *before* the deadline we flag each level.
    Breached = past deadline.
    """
    breached_severity: str = "critical"  # SLA already missed
    critical_hours: float = 2.0          # <= 2h to deadline -> critical
    high_hours: float = 8.0              # <= 8h -> high
    medium_hours: float = 24.0           # <= 24h -> medium
    # anything further out with no other risks -> no flag


@dataclass(frozen=True)
class HistoricalThresholds:
    """When historical delays start bumping severity."""
    delay_count_warning: int = 2
    delay_count_elevate: int = 3
    prior_escalation_weight: int = 1


DEFAULT_SLA = SLAThresholds()
DEFAULT_HISTORY = HistoricalThresholds()


# Escalation targets by risk type. Kept centralized so the Risk Radar /
# Governance boundary is easy to adjust once that question is resolved
# with the lead.
ESCALATION_TARGETS = {
    "missing_input_mandatory": "task_owner",
    "sla_breached": "workflow_owner",
    "dependency_blocked": "workflow_owner",
    "compliance_flag": "compliance_reviewer",  # TODO: confirm with lead — may be Governance Agent's call
    "multi_high_risk": "manager",
    "ambiguous": "human_reviewer",
}
