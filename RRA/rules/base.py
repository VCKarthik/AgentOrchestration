"""
Risk Radar Agent — Rule base interface.

Every risk category is a self-contained Rule. The agent loads enabled rules,
runs each one against the case, and collects RiskItems. Adding a new risk
category in a future sprint = drop a new file implementing this Protocol.
"""

from __future__ import annotations

from typing import List, Protocol

from ..schema import CaseInput, RiskItem


class Rule(Protocol):
    """Protocol every risk rule implements."""

    name: str

    def applies(self, case: CaseInput) -> bool:
        """Return True if this rule has enough context to evaluate."""
        ...

    def evaluate(self, case: CaseInput) -> List[RiskItem]:
        """Return zero or more RiskItems detected for this case."""
        ...
