"""
Risk Radar Agent — Severity & decision consolidation.

Takes a list of RiskItems and produces:
  - overall_risk_level (max severity, with modifiers)
  - can_proceed (proceed / caution / hold)
  - escalate_to_human (hard + soft escalation logic from Sprint 4)
  - escalation_target

This is the decision table. Pure function. Deterministic. Easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .config import ESCALATION_TARGETS
from .schema import (
    CaseInput,
    OperatingContext,
    ProceedDecision,
    RiskItem,
    RiskType,
    Severity,
)


@dataclass
class Decision:
    overall_risk_level: Severity
    can_proceed: ProceedDecision
    escalate_to_human: bool
    escalation_target: Optional[str]


def consolidate(
    risk_items: List[RiskItem],
    case: CaseInput,
    operating_context: OperatingContext,
) -> Decision:
    if not risk_items:
        return Decision(
            overall_risk_level=Severity.LOW,
            can_proceed=ProceedDecision.PROCEED,
            escalate_to_human=False,
            escalation_target=None,
        )

    overall = _overall_severity(risk_items)
    any_blocking = any(item.blocking for item in risk_items)
    high_count = sum(1 for item in risk_items if item.severity.rank >= Severity.HIGH.rank)

    # Combined-risk rule: multiple High items elevate to Critical.
    if high_count >= 2 and overall != Severity.CRITICAL:
        overall = Severity.CRITICAL

    can_proceed = _proceed_decision(overall, any_blocking)
    escalate, target = _escalation(overall, risk_items, case, operating_context, high_count)

    return Decision(
        overall_risk_level=overall,
        can_proceed=can_proceed,
        escalate_to_human=escalate,
        escalation_target=target,
    )


def _overall_severity(items: List[RiskItem]) -> Severity:
    return max(items, key=lambda i: i.severity.rank).severity


def _proceed_decision(overall: Severity, any_blocking: bool) -> ProceedDecision:
    """Blocking beats severity — a blocking Medium still holds the workflow."""
    if any_blocking or overall == Severity.CRITICAL:
        return ProceedDecision.HOLD
    if overall == Severity.HIGH:
        return ProceedDecision.HOLD
    if overall == Severity.MEDIUM:
        return ProceedDecision.CAUTION
    return ProceedDecision.PROCEED


def _escalation(
    overall: Severity,
    items: List[RiskItem],
    case: CaseInput,
    operating_context: OperatingContext,
    high_count: int,
) -> Tuple[bool, Optional[str]]:
    """
    Sprint 4 escalation logic — hard triggers (deterministic overrides) +
    soft triggers (human review safer than autonomous continuation).
    """
    # --- Hard escalations ---
    if overall == Severity.CRITICAL:
        # Figure out the most specific target we can.
        if any(i.risk_type == RiskType.COMPLIANCE_RISK for i in items):
            return True, ESCALATION_TARGETS["compliance_flag"]
        if any(i.risk_type == RiskType.MISSING_INPUT and i.blocking for i in items):
            return True, ESCALATION_TARGETS["missing_input_mandatory"]
        if any(i.risk_type == RiskType.DEADLINE_RISK and i.blocking for i in items):
            return True, ESCALATION_TARGETS["sla_breached"]
        return True, ESCALATION_TARGETS["manager"] if "manager" in ESCALATION_TARGETS else "manager"

    # Multiple High risks combine into severe case -> hard escalate.
    if high_count >= 2:
        return True, ESCALATION_TARGETS["multi_high_risk"]

    # Compliance flag on case + any High risk -> hard escalate to compliance.
    if case.policy_flag and overall == Severity.HIGH:
        return True, ESCALATION_TARGETS["compliance_flag"]

    # --- Soft escalations ---
    if operating_context == OperatingContext.PARTIAL and overall.rank >= Severity.MEDIUM.rank:
        return True, ESCALATION_TARGETS["ambiguous"]

    if overall == Severity.HIGH:
        return True, "task_owner"

    return False, None
