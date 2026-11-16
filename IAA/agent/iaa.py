"""
iaa.py
Main IAA entrypoint and LangGraph-compatible node wrapper.

Two interfaces:
  1. run_iaa(state) — direct callable, returns ActionRecommendation
  2. iaa_node(graph_state) — LangGraph node, reads/writes shared state dict

The LangGraph node is non-fixed — it can be inserted at any position in any graph.
It reads from graph_state["process_state"] and writes to graph_state["iaa_*"] keys.
It also supplements ProcessState from csa_output / rra_output keys if present.
"""

from __future__ import annotations
import logging
import os, json, time
from datetime import datetime, timezone
from typing import Optional, Any
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

from .schemas import ProcessState, ActionRecommendation, EventLogEntry, ProcessStep
from .retriever import IAARetriever
from .chain import run_chain, apply_overrides, get_llm


# ── ProcessState builder from raw event log ───────────────────────────────────

def build_process_state(
    events: list[EventLogEntry],
    context_summary: Optional[str] = None,
    risk_flags: Optional[list[str]] = None,
    risk_severity: Optional[str] = None,
    policy_constraints: Optional[list[str]] = None,
    assigned_owner: Optional[str] = None,
) -> ProcessState:
    """
    Build a ProcessState from a list of EventLogEntry objects.
    The last event is the current state; all prior events form the history.
    Upstream agent outputs are optional — graceful degradation if absent.
    Populates both prior_actions (strings) and prior_steps (structured) from events.
    """
    if not events:
        raise ValueError("Cannot build ProcessState from empty event list")

    events_sorted = sorted(events, key=lambda e: e.timestamp)
    current       = events_sorted[-1]
    prior_events  = events_sorted[:-1]

    prior_actions = [e.event_type for e in prior_events]
    prior_steps   = [
        ProcessStep(
            event_type=e.event_type,
            actor=e.actor,
            timestamp=e.timestamp,
            outcome=e.outcome,
        )
        for e in prior_events
    ]

    absent = []
    if risk_severity is None and not risk_flags:
        absent.append("risk_radar")
    if not policy_constraints:
        absent.append("governance_policy")
    if not assigned_owner:
        absent.append("delegation")

    operating_ctx = "full" if not absent else f"partial — {', '.join(absent)} null"

    return ProcessState(
        entity_id=current.entity_id,
        current_stage=current.stage,
        current_event_type=current.event_type,
        prior_actions=prior_actions,
        prior_steps=prior_steps,
        actor=current.actor,
        timestamp=current.timestamp,
        metadata=current.metadata,
        context_summary=context_summary,
        risk_flags=risk_flags or [],
        risk_severity=risk_severity,
        policy_constraints=policy_constraints or [],
        assigned_owner=assigned_owner,
        operating_context=operating_ctx,
    )


# ── Core IAA function ─────────────────────────────────────────────────────────

_retriever: Optional[IAARetriever] = None
_llm = None

def run_iaa(
    state: ProcessState,
    domain_filter: Optional[str] = None,
    process_type_filter: Optional[str] = None,
    retriever: Optional[IAARetriever] = None,
    llm=None,
) -> ActionRecommendation:
    """
    Run the full IAA pipeline for a given ProcessState.

    1. Retrieve relevant historical context from the vector store
    2. Run three-step LLM chain (Contextualize → Anticipate → Recommend)
    3. Apply rule overrides
    4. Return ActionRecommendation
    """
    global _retriever, _llm

    if retriever is None:
        if _retriever is None:
            _retriever = IAARetriever()
        retriever = _retriever

    if llm is None:
        if _llm is None:
            _llm = get_llm()
        llm = _llm

    retrieved    = retriever.retrieve(state, domain_filter, process_type_filter)
    context_str  = retriever.format_for_prompt(retrieved)
    context_ids  = [r["id"] for r in retrieved]

    recommendation = run_chain(state, context_str, context_ids, llm)
    final          = apply_overrides(recommendation, state)

    _log(state, final)
    return final


# ── LangGraph node wrapper ────────────────────────────────────────────────────

def iaa_node(graph_state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph-compatible node function.

    Reads from graph_state:
      - process_state: ProcessState (required)
      - csa_output: dict with context_summary (optional — supplements ProcessState)
      - rra_output: dict with severity/flags (optional — supplements ProcessState)

    Writes to graph_state:
      - iaa_recommendation: ActionRecommendation
      - iaa_routing_action: str (top action_id for conditional edges)
      - iaa_escalate: bool (shortcut for approval gate)
    """
    from .schemas import PredictedAction

    # Read optional upstream outputs from shared state
    csa_output = graph_state.get("csa_output") or {}
    rra_output = graph_state.get("rra_output") or {}

    ps = graph_state.get("process_state")

    if ps is None:
        fallback = PredictedAction(
            action_id="escalate_for_review",
            label="Escalate — no process state",
            confidence=0.99,
            reasoning="IAA received no process_state — cannot predict without input",
        )
        rec = ActionRecommendation(
            predicted_actions=[fallback],
            recommended_action=fallback,
            override_applied=True,
            override_reason="No process_state in graph state",
            escalate_to_human=True,
            timestamp=datetime.now(timezone.utc),
        )
        return {
            **graph_state,
            "iaa_recommendation": rec,
            "iaa_routing_action": "escalate_for_review",
            "iaa_escalate": True,
        }

    # Supplement ProcessState with upstream outputs if available and not already set
    if isinstance(ps, ProcessState):
        update: dict[str, Any] = {}
        if csa_output.get("context_summary") and not ps.context_summary:
            update["context_summary"] = csa_output["context_summary"]
        if rra_output.get("severity") and not ps.risk_severity:
            update["risk_severity"] = rra_output["severity"]
        if rra_output.get("flags") and not ps.risk_flags:
            update["risk_flags"] = rra_output["flags"]
        if update:
            ps = ps.model_copy(update=update)

    recommendation = run_iaa(ps)

    return {
        **graph_state,
        "iaa_recommendation": recommendation,
        "iaa_routing_action": recommendation.recommended_action.action_id,
        "iaa_escalate": recommendation.escalate_to_human,
    }


# ── Logging ───────────────────────────────────────────────────────────────────

LOG_FILE = os.getenv("LOG_FILE", "./data/predictions.jsonl")

def _log(state: ProcessState, rec: ActionRecommendation) -> None:
    """Append one IAA invocation to the JSONL log for evaluation and audit."""
    try:
        import pathlib
        pathlib.Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp":        rec.timestamp.isoformat(),
            "entity_id":        state.entity_id,
            "current_stage":    state.current_stage,
            "current_event":    state.current_event_type,
            "operating_context":state.operating_context,
            "recommended":      rec.recommended_action.action_id,
            "confidence":       rec.recommended_action.confidence,
            "override_applied": rec.override_applied,
            "override_reason":  rec.override_reason,
            "escalate":         rec.escalate_to_human,
            "model_used":       rec.model_used,
            "task_count":       len(rec.task_list),
            "timeline_steps":   len(rec.workflow_timeline),
        }
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning("IAA logging failed: %s", e)
