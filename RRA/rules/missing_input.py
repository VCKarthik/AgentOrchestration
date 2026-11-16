"""
Missing Input Risk (Sprint 5 capability).

Logic:
  - required set - received set = missing set
  - If any missing item is in mandatory_inputs AND policy_flag is on -> CRITICAL (blocking)
  - If any missing item is in mandatory_inputs -> HIGH (blocking)
  - If non-mandatory items are missing -> MEDIUM (non-blocking)
  - If nothing is missing -> no risk item emitted
"""

from __future__ import annotations

from typing import List

from ..schema import CaseInput, RiskItem, RiskType, Severity


class MissingInputRule:
    name = "missing_input"

    def applies(self, case: CaseInput) -> bool:
        # If there are no required inputs declared, this rule can't say anything.
        return len(case.required_inputs) > 0

    def evaluate(self, case: CaseInput) -> List[RiskItem]:
        received = set(case.received_inputs)
        required = set(case.required_inputs)
        mandatory = set(case.mandatory_inputs)

        missing = required - received
        if not missing:
            return []

        missing_mandatory = missing & mandatory
        missing_optional = missing - mandatory

        items: List[RiskItem] = []

        if missing_mandatory:
            # Mandatory + compliance-sensitive workflow => critical
            if case.policy_flag:
                severity = Severity.CRITICAL
            else:
                severity = Severity.HIGH

            items.append(RiskItem(
                risk_type=RiskType.MISSING_INPUT,
                severity=severity,
                reason=(
                    f"Mandatory input(s) missing: {sorted(missing_mandatory)}. "
                    f"Workflow cannot safely proceed without these."
                ),
                blocking=True,
            ))

        if missing_optional:
            items.append(RiskItem(
                risk_type=RiskType.MISSING_INPUT,
                severity=Severity.MEDIUM,
                reason=(
                    f"Non-mandatory input(s) missing: {sorted(missing_optional)}. "
                    f"Workflow may proceed but output quality may be reduced."
                ),
                blocking=False,
            ))

        return items
