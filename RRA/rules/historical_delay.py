"""
Historical Delay Risk rule.

Logic:
  - prior_delay_count >= 5  OR
    (prior_delay_count >= 3 AND prior_escalation_count >= 1) -> HIGH
  - prior_delay_count >= 3  OR prior_escalation_count >= 2   -> MEDIUM
  - prior_delay_count >= 1  OR prior_escalation_count >= 1   -> LOW
  - otherwise                                                 -> no flag

This rule never blocks execution on its own — history alone doesn't
stop a task, but it raises human attention.
"""

from __future__ import annotations

from typing import List

from ..schema import CaseInput, RiskItem, RiskType, Severity


class HistoricalDelayRule:
    name = "historical_delay"

    def applies(self, case: CaseInput) -> bool:
        return case.prior_delay_count > 0 or case.prior_escalation_count > 0

    def evaluate(self, case: CaseInput) -> List[RiskItem]:
        d = case.prior_delay_count
        e = case.prior_escalation_count

        if d >= 5 or (d >= 3 and e >= 1):
            sev = Severity.HIGH
            reason = (
                f"Chronic delay pattern: {d} prior delays, {e} prior escalation(s). "
                "Similar cases have repeatedly missed deadlines — high recurrence risk."
            )
        elif d >= 3 or e >= 2:
            sev = Severity.MEDIUM
            reason = (
                f"Repeated delay history: {d} prior delays, {e} prior escalation(s). "
                "Pattern suggests elevated risk of another delay."
            )
        elif d >= 1 or e >= 1:
            sev = Severity.LOW
            reason = (
                f"Minor delay history: {d} prior delay(s), {e} prior escalation(s). "
                "Worth monitoring but not immediately concerning."
            )
        else:
            return []

        return [RiskItem(risk_type=RiskType.HISTORICAL_DELAY, severity=sev,
                         reason=reason, blocking=False)]
