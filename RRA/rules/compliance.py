"""
Compliance Risk rule.

Logic:
  - policy_flag=True AND stakeholder_priority in (executive, regulatory) -> CRITICAL (blocking)
  - policy_flag=True AND prior_escalation_count >= 1                     -> HIGH
  - policy_flag=True                                                      -> MEDIUM (non-blocking)
  - policy_flag=False                                                     -> no flag

Distinct from MissingInputRule: this rule flags that the *context itself*
is compliance-sensitive regardless of what documents are present.
"""

from __future__ import annotations

from typing import List

from ..schema import CaseInput, RiskItem, RiskType, Severity

_HIGH_STAKE_PRIORITIES = {"executive", "regulatory", "legal"}


class ComplianceRule:
    name = "compliance_risk"

    def applies(self, case: CaseInput) -> bool:
        return case.policy_flag

    def evaluate(self, case: CaseInput) -> List[RiskItem]:
        priority = (case.stakeholder_priority or "").lower()
        is_high_stake = priority in _HIGH_STAKE_PRIORITIES

        if is_high_stake:
            return [RiskItem(
                risk_type=RiskType.COMPLIANCE_RISK,
                severity=Severity.CRITICAL,
                reason=(
                    f"Policy-flagged workflow with {priority}-level stakeholder priority. "
                    "Compliance review is mandatory before any action."
                ),
                blocking=True,
            )]

        if case.prior_escalation_count >= 1:
            return [RiskItem(
                risk_type=RiskType.COMPLIANCE_RISK,
                severity=Severity.HIGH,
                reason=(
                    f"Policy-flagged case with {case.prior_escalation_count} prior escalation(s). "
                    "Recurrence pattern in a compliance-sensitive workflow requires review."
                ),
                blocking=False,
            )]

        return [RiskItem(
            risk_type=RiskType.COMPLIANCE_RISK,
            severity=Severity.MEDIUM,
            reason="Policy flag is set on this case. Compliance conditions apply — review before proceeding.",
            blocking=False,
        )]
