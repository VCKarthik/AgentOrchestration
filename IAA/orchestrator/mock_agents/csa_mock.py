"""MOCK Context Stitching Agent — replace with real CSA in Sprint 6."""
from __future__ import annotations
from typing import TYPE_CHECKING
from agent.schemas import EventLogEntry

if TYPE_CHECKING:
    from ..orchestrator import SharedWorkflowState


def csa_node(state: "SharedWorkflowState") -> "SharedWorkflowState":
    """Reads events and produces a one-sentence context summary."""
    events: list[EventLogEntry] = state.get("events", [])

    if not events:
        csa_output = {
            "context_summary": "No events provided — context unavailable.",
            "missing_inputs": ["no_events_provided"],
        }
    else:
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        event_types   = [e.event_type for e in sorted_events]
        summary = (
            f"Case {state.get('entity_id', 'unknown')} has progressed through "
            f"{len(event_types)} event(s): {' → '.join(event_types)}."
        )
        csa_output = {
            "context_summary": summary,
            "missing_inputs":  [],
        }

    return {**state, "csa_output": csa_output}
