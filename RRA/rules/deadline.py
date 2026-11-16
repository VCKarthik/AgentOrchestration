"""
Deadline / SLA Risk (Sprint 6 capability).

Logic:
  - sla_deadline breached (now > sla_deadline) -> CRITICAL (blocking)
  - <= critical_hours remaining -> HIGH (non-blocking but urgent)
  - <= high_hours remaining    -> MEDIUM
  - <= medium_hours remaining  -> LOW
  - further out -> no flag

History modifier:
  - If prior_delay_count >= elevate threshold, bump severity up one notch
    (capped at CRITICAL). This is deliberately conservative — we don't
    want historical patterns alone to block execution, but they should
    raise attention.

Also evaluates due_date using the same logic if sla_deadline is absent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from ..config import DEFAULT_HISTORY, DEFAULT_SLA
from ..schema import CaseInput, RiskItem, RiskType, Severity


def _bump(severity: Severity) -> Severity:
    ladder = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
    idx = ladder.index(severity)
    return ladder[min(idx + 1, len(ladder) - 1)]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hours_until(deadline: datetime) -> float:
    # Normalize naive datetimes to UTC so comparisons don't blow up.
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    delta = deadline - _now()
    return delta.total_seconds() / 3600.0


def _classify(hours_remaining: float, sla=DEFAULT_SLA) -> Optional[Severity]:
    if hours_remaining < 0:
        return Severity.CRITICAL  # breached
    if hours_remaining <= sla.critical_hours:
        return Severity.HIGH
    if hours_remaining <= sla.high_hours:
        return Severity.MEDIUM
    if hours_remaining <= sla.medium_hours:
        return Severity.LOW
    return None


class DeadlineRule:
    name = "deadline_risk"

    def __init__(self, sla=DEFAULT_SLA, history=DEFAULT_HISTORY):
        self.sla = sla
        self.history = history

    def applies(self, case: CaseInput) -> bool:
        return case.sla_deadline is not None or case.due_date is not None

    def evaluate(self, case: CaseInput) -> List[RiskItem]:
        items: List[RiskItem] = []

        # Evaluate SLA deadline first — treated as more critical than due_date.
        if case.sla_deadline is not None:
            hours = _hours_until(case.sla_deadline)
            sev = _classify(hours, self.sla)
            if sev is not None:
                if case.prior_delay_count >= self.history.delay_count_elevate:
                    sev = _bump(sev)
                items.append(self._make_item(
                    kind="SLA",
                    hours=hours,
                    severity=sev,
                    history_bumped=(case.prior_delay_count >= self.history.delay_count_elevate),
                    prior_delays=case.prior_delay_count,
                ))

        # Only evaluate due_date independently if there's no SLA or the SLA didn't fire.
        if case.due_date is not None and case.sla_deadline is None:
            hours = _hours_until(case.due_date)
            sev = _classify(hours, self.sla)
            if sev is not None:
                items.append(self._make_item(
                    kind="Due date",
                    hours=hours,
                    severity=sev,
                    history_bumped=False,
                    prior_delays=case.prior_delay_count,
                ))

        return items

    @staticmethod
    def _make_item(kind: str, hours: float, severity: Severity,
                   history_bumped: bool, prior_delays: int) -> RiskItem:
        if hours < 0:
            reason = f"{kind} breached by {abs(hours):.1f}h."
            blocking = True
        else:
            reason = f"{kind} within {hours:.1f}h."
            blocking = severity == Severity.CRITICAL

        if history_bumped:
            reason += f" Severity elevated due to {prior_delays} prior delays on similar cases."

        return RiskItem(
            risk_type=RiskType.DEADLINE_RISK,
            severity=severity,
            reason=reason,
            blocking=blocking,
        )
