# REFERENCE IMPLEMENTATION — LangGraph orchestrator
# Status: preserved for handoff. Not called at runtime.
# Active orchestrator: agent/main.py (ADK) — see Step 5
# Sprint 6: replace mock_agents/ with real teammate agent endpoints
"""
orchestrator.py
MVP Orchestrator — wires IAA together with mock versions of the other 5 agents
using LangGraph. Real agent implementations will replace the mocks in Sprint 6.

Agent pipeline (linear with conditional escalation gate):
  CSA → RRA → IAA → (if escalate) END
                   → Delegation → END

SharedWorkflowState is the single TypedDict passed through the entire graph.
"""

from __future__ import annotations
from typing import Optional, TypedDict
from datetime import datetime, timezone

from agent.schemas import EventLogEntry, ProcessState, ActionRecommendation
from agent.iaa import run_iaa, build_process_state

from .mock_agents import csa_node, rra_node, delegation_node


# ── Shared workflow state ─────────────────────────────────────────────────────

class SharedWorkflowState(TypedDict, total=False):
    entity_id: str
    process_state: Optional[ProcessState]
    events: list[EventLogEntry]
    csa_output: Optional[dict]        # context_summary, missing_inputs
    rra_output: Optional[dict]        # severity, flags
    iaa_recommendation: Optional[ActionRecommendation]
    iaa_routing_action: Optional[str]
    iaa_escalate: bool
    delegation_output: Optional[dict] # assigned_role, task_list consumed
    workflow_complete: bool
    error: Optional[str]


# ── IAA node (real, not mocked) ───────────────────────────────────────────────

def iaa_node_wrapped(state: SharedWorkflowState) -> SharedWorkflowState:
    """
    Real IAA node — builds ProcessState from events, calls run_iaa().
    Reads csa_output and rra_output from shared state to enrich ProcessState.
    """
    events: list[EventLogEntry] = state.get("events", [])
    csa_output = state.get("csa_output") or {}
    rra_output = state.get("rra_output") or {}

    if not events:
        from agent.schemas import PredictedAction
        fallback = PredictedAction(
            action_id="escalate_for_review",
            label="Escalate — no events",
            confidence=0.99,
            reasoning="Orchestrator received no events — cannot run IAA without input",
        )
        rec = ActionRecommendation(
            predicted_actions=[fallback],
            recommended_action=fallback,
            override_applied=True,
            override_reason="No events in workflow state",
            escalate_to_human=True,
            timestamp=datetime.now(timezone.utc),
        )
        return {
            **state,
            "iaa_recommendation": rec,
            "iaa_routing_action": "escalate_for_review",
            "iaa_escalate": True,
        }

    try:
        ps = build_process_state(
            events,
            context_summary=csa_output.get("context_summary"),
            risk_severity=rra_output.get("severity"),
            risk_flags=rra_output.get("flags", []),
        )
        rec = run_iaa(ps)
        return {
            **state,
            "process_state":      ps,
            "iaa_recommendation": rec,
            "iaa_routing_action": rec.recommended_action.action_id,
            "iaa_escalate":       rec.escalate_to_human,
        }
    except Exception as e:
        from agent.schemas import PredictedAction
        err_action = PredictedAction(
            action_id="escalate_for_review",
            label="Escalate — IAA error",
            confidence=0.99,
            reasoning=f"IAA encountered an error: {e}",
        )
        rec = ActionRecommendation(
            predicted_actions=[err_action],
            recommended_action=err_action,
            override_applied=True,
            override_reason=f"IAA error: {e}",
            escalate_to_human=True,
            timestamp=datetime.now(timezone.utc),
        )
        return {
            **state,
            "iaa_recommendation": rec,
            "iaa_routing_action": "escalate_for_review",
            "iaa_escalate":       True,
            "error":              str(e),
        }


# ── Graph construction ────────────────────────────────────────────────────────

_checkpointer = None

def _get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver
        _checkpointer = MemorySaver()
    return _checkpointer


def _build_graph():
    """Build and compile the workflow LangGraph with a memory checkpointer."""
    from langgraph.graph import StateGraph, END

    workflow = StateGraph(SharedWorkflowState)

    workflow.add_node("csa_node",            csa_node)
    workflow.add_node("rra_node",            rra_node)
    workflow.add_node("iaa_node_wrapped",    iaa_node_wrapped)
    workflow.add_node("delegation_node",     delegation_node)

    workflow.set_entry_point("csa_node")
    workflow.add_edge("csa_node", "rra_node")
    workflow.add_edge("rra_node", "iaa_node_wrapped")

    def _route_after_iaa(state: SharedWorkflowState) -> str:
        return END if state.get("iaa_escalate") else "delegation_node"

    workflow.add_conditional_edges(
        "iaa_node_wrapped",
        _route_after_iaa,
        {END: END, "delegation_node": "delegation_node"},
    )
    workflow.add_edge("delegation_node", END)

    return workflow.compile(checkpointer=_get_checkpointer())


_graph = None

def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ── Public API ────────────────────────────────────────────────────────────────

def run_workflow(
    events: list[EventLogEntry],
    entity_id: str,
) -> SharedWorkflowState:
    """
    Run the full orchestrator pipeline for a list of events.

    Pipeline: CSA → RRA → IAA → Delegation (unless escalated)

    Returns the final SharedWorkflowState with all agent outputs populated.
    """
    initial_state: SharedWorkflowState = {
        "entity_id":          entity_id,
        "events":             events,
        "process_state":      None,
        "csa_output":         None,
        "rra_output":         None,
        "iaa_recommendation": None,
        "iaa_routing_action": None,
        "iaa_escalate":       False,
        "delegation_output":  None,
        "workflow_complete":  False,
        "error":              None,
    }

    graph  = _get_graph()
    config = {"configurable": {"thread_id": entity_id}}
    result = graph.invoke(initial_state, config=config)
    return result


def get_workflow_history(entity_id: str) -> list:
    """
    Return all state snapshots for a given entity_id thread, newest first.
    Each snapshot is a langgraph StateSnapshot with .values, .next, .config,
    .metadata, .created_at. Empty list if no history exists.
    """
    try:
        graph  = _get_graph()
        config = {"configurable": {"thread_id": entity_id}}
        return list(graph.get_state_history(config))
    except Exception as e:
        print(f"[orchestrator] get_workflow_history({entity_id}) failed: {e}")
        return []


# ── Demo entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json, sys
    from pathlib import Path

    cases_path = Path(__file__).parent.parent / "data" / "synthetic_cases.json"
    if not cases_path.exists():
        print(f"Synthetic cases not found at {cases_path}")
        print("Run: python scripts/generate_synthetic.py first")
        sys.exit(1)

    cases = json.load(open(cases_path))

    case = next(
        (c for c in cases
         if c["risk_severity"] == "medium" and len(c.get("prior_actions", [])) >= 2),
        cases[0]
    )

    print("\n" + "=" * 60)
    print("  ORCHESTRATOR DEMO — Project AMP MVP")
    print("=" * 60)
    print(f"\n  Case       : {case['entity_id']}")
    print(f"  Process    : {case['process_type']}")
    print(f"  Event      : {case['event_type']}")
    print(f"  Prior      : {' → '.join(case.get('prior_actions', []))}")
    print(f"  Risk       : {case['risk_severity']}")
    print(f"  GT next    : {case['next_action']}")

    ts = datetime.now(timezone.utc)
    events = []
    for j, evt in enumerate(case.get("prior_actions", [])):
        events.append(EventLogEntry(
            event_id=f"{case['entity_id']}-{j}",
            entity_id=case["entity_id"],
            event_type=evt,
            stage=evt,
            timestamp=ts,
            metadata={},
        ))
    events.append(EventLogEntry(
        event_id=f"{case['entity_id']}-current",
        entity_id=case["entity_id"],
        event_type=case["event_type"],
        stage=case.get("stage", case["event_type"]),
        timestamp=ts,
        metadata=case.get("metadata", {}),
    ))

    print("\n  Running pipeline...")
    result = run_workflow(events, case["entity_id"])

    print("\n" + "─" * 60)
    print("  CSA OUTPUT")
    print("─" * 60)
    csa = result.get("csa_output") or {}
    print(f"  Summary : {csa.get('context_summary', 'N/A')}")
    print(f"  Missing : {csa.get('missing_inputs', [])}")

    print("\n" + "─" * 60)
    print("  RRA OUTPUT")
    print("─" * 60)
    rra = result.get("rra_output") or {}
    print(f"  Severity: {rra.get('severity', 'N/A')}")
    print(f"  Flags   : {rra.get('flags', [])}")

    print("\n" + "─" * 60)
    print("  IAA OUTPUT")
    print("─" * 60)
    rec = result.get("iaa_recommendation")
    if rec:
        print(f"  Action  : {rec.recommended_action.action_id}")
        print(f"  Label   : {rec.recommended_action.label}")
        print(f"  Conf    : {rec.recommended_action.confidence:.0%}")
        print(f"  Escalate: {rec.escalate_to_human}")
        if rec.task_list:
            print(f"\n  Task list ({len(rec.task_list)} tasks):")
            for t in rec.task_list:
                print(f"    [{t.priority.upper()}] {t.task_id} — {t.action} (role: {t.assigned_role or 'unassigned'})")
        if rec.workflow_timeline:
            print(f"\n  Timeline ({len(rec.workflow_timeline)} steps):")
            for w in rec.workflow_timeline:
                print(f"    Step {w.step}: {w.event_type} [{w.status}]")

    print("\n" + "─" * 60)
    print("  DELEGATION OUTPUT")
    print("─" * 60)
    deleg = result.get("delegation_output")
    if deleg:
        for t in deleg.get("assigned_tasks", []):
            print(f"  {t['task_id']} → {t['assigned_to']}  ({t['priority']} priority)")
    elif result.get("iaa_escalate"):
        print("  [skipped — escalated to human]")
    else:
        print("  N/A")

    print(f"\n  Workflow complete: {result.get('workflow_complete', False)}")
    if result.get("error"):
        print(f"  Error: {result['error']}")
    print()
