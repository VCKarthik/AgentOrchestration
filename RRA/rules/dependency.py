"""
Dependency Risk rule.

Logic:
  - blocker_flag=True OR dependency_status="blocked" -> CRITICAL (blocking)
  - dependency_status="pending"                      -> HIGH (non-blocking)
  - dependency_status="at_risk"                      -> MEDIUM (non-blocking)
  - dependency_status="clear" / absent               -> no flag
"""

from __future__ import annotations

from typing import List

from ..schema import CaseInput, RiskItem, RiskType, Severity


_STATUS_MAP = {
    "blocked":  (Severity.CRITICAL, True,  "Upstream dependency is blocked. Workflow cannot proceed."),
    "pending":  (Severity.HIGH,     False, "Upstream dependency is unconfirmed (pending). Execution is at risk."),
    "at_risk":  (Severity.MEDIUM,   False, "Upstream dependency flagged at-risk. Monitor closely before proceeding."),
}


class DependencyRule:
    name = "dependency_risk"

    def applies(self, case: CaseInput) -> bool:
        return case.blocker_flag or (case.dependency_status is not None and
                                     case.dependency_status != "clear")

    def evaluate(self, case: CaseInput) -> List[RiskItem]:
        if case.blocker_flag:
            return [RiskItem(
                risk_type=RiskType.DEPENDENCY_RISK,
                severity=Severity.CRITICAL,
                reason="Blocker flag is set on this case. Workflow is explicitly blocked by an upstream dependency.",
                blocking=True,
            )]

        status = (case.dependency_status or "").lower()
        if status in _STATUS_MAP:
            sev, blocking, reason = _STATUS_MAP[status]
            return [RiskItem(risk_type=RiskType.DEPENDENCY_RISK, severity=sev,
                             reason=reason, blocking=blocking)]
        return []
