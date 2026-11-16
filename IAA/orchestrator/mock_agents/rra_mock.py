"""MOCK Risk Radar Agent — replace with real RRA in Sprint 6."""
from __future__ import annotations
from typing import TYPE_CHECKING
from agent.schemas import EventLogEntry

if TYPE_CHECKING:
    from ..orchestrator import SharedWorkflowState


def rra_node(state: "SharedWorkflowState") -> "SharedWorkflowState":
    """Counts events and flags documentation gaps."""
    events: list[EventLogEntry] = state.get("events", [])

    severity = "low"
    flags: list[str] = []

    if len(events) > 3:
        last_event = events[-1].event_type.lower() if events else ""
        if "incomplete" in last_event or "missing" in last_event:
            severity = "medium"
            flags = ["documentation_gap"]

    rra_output = {"severity": severity, "flags": flags}
    return {**state, "rra_output": rra_output}
