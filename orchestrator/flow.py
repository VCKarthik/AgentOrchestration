"""
flow.py — Programmatic AMP workflow execution.

Public API: run_amp_workflow(task_input: dict, on_progress=None) -> AmpState

Backed by LangGraph graph.ainvoke(). The StateGraph (graph.py) owns execution order;
this module owns the public interface and the AmpState reconstruction from final graph state.

LangSmith tracing: graph.ainvoke() is automatically traced when LANGCHAIN_TRACING_V2=true.
Individual node HTTP calls are traced via @traceable in tools.py.
"""
from __future__ import annotations

import logging
from typing import Callable

from langsmith import traceable

from .graph import get_graph
from .schemas import AmpState, TaskIntake

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@traceable(name="amp_workflow", run_type="chain")
async def run_amp_workflow(
    task_input: dict,
    on_progress: Callable[[str], None] | None = None,
) -> AmpState:
    """
    Execute the full AMP workflow programmatically.

    task_input: dict matching TaskIntake fields.
    on_progress: optional callback called with a status string at each stage boundary.
    Returns: fully-populated AmpState (or partial on failure).

    The graph runs: CSA → Stage2 (RRA/GPA/IAA as needed) → DA
    SWA fires as a background task inside csa_node — non-blocking.
    """
    def _progress(msg: str) -> None:
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    task_intake = TaskIntake(**{k: v for k, v in task_input.items() if v is not None})
    _progress(f"Starting workflow — task_id={task_intake.task_id}")

    initial_state = {
        "task_intake":  task_intake,
        "latency_log":  {},
        "stage_errors": {},
    }
    config = {"configurable": {"thread_id": task_intake.task_id or "default"}}

    _progress("Stage 1 — CSA: fetching context...")

    # Stream the graph node-by-node so progress callbacks fire AS each stage
    # completes, not in a recap after the whole run. Without this, the demo UI
    # shows "CSA fetching context" for the entire workflow and then every
    # stage message lands at once at the end.
    final_state: dict = dict(initial_state)
    async for update in get_graph().astream(
        initial_state,
        config=config,
        stream_mode="updates",
    ):
        for node, delta in update.items():
            if isinstance(delta, dict):
                final_state.update({k: v for k, v in delta.items() if v is not None})

            if node == "csa":
                csa = final_state.get("csa_output")
                validation = getattr(csa, "validation", None) if csa else None
                conf = getattr(validation, "confidence_score", None) if validation else None
                conf_str = f" (confidence: {conf:.0%})" if conf is not None else ""
                _progress(f"Stage 1 complete — CSA stitched context{conf_str}")
                _progress("Stage 2 — RRA / GPA / IAA running in parallel...")
            elif node == "stage2":
                ro = final_state.get("risk_output")
                if ro:
                    _progress(f"  RRA: risk={ro.overall_risk_level}, proceed={ro.can_proceed}")
                go = final_state.get("governance_output")
                if go:
                    _progress(f"  GPA: decision={go.decision}, requires_approval={go.requires_approval}")
                iaa = final_state.get("iaa_output")
                if iaa and iaa.recommended_action:
                    rec = iaa.recommended_action
                    _progress(f"  IAA: recommended={rec.label} ({rec.confidence:.0%})")
                _progress("Stage 2 complete")
                _progress("Stage 3 — DA: sending request...")
            elif node == "da":
                do = final_state.get("da_output")
                if do:
                    _progress(f"Stage 3 complete — DA assigned: status={do.status}, escalation={do.escalation_required}")

    result = AmpState(**{k: v for k, v in final_state.items() if v is not None})

    _progress(
        f"Workflow complete — requires_escalation={result.requires_escalation}, "
        f"operating_context={result.operating_context}, stage_errors={result.stage_errors}"
    )
    return result
