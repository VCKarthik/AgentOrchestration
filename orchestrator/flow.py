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
    final_state = await get_graph().ainvoke(
        initial_state,
        config=config,
    )

    result = AmpState(**{k: v for k, v in final_state.items() if v is not None})

    # Post-run stage summaries from final state
    if result.csa_output:
        conf = getattr(result.csa_output.validation, "confidence_score", None) if result.csa_output.validation else None
        conf_str = f" (confidence: {conf:.0%})" if conf is not None else ""
        _progress(f"Stage 1 complete — CSA stitched context{conf_str}")

    _progress("Stage 2 — RRA / GPA / IAA ran in parallel")

    if result.risk_output:
        _progress(f"  RRA: risk={result.risk_output.overall_risk_level}, proceed={result.risk_output.can_proceed}")
    if result.governance_output:
        _progress(f"  GPA: decision={result.governance_output.decision}, requires_approval={result.governance_output.requires_approval}")
    if result.iaa_output and result.iaa_output.recommended_action:
        rec = result.iaa_output.recommended_action
        _progress(f"  IAA: recommended={rec.label} ({rec.confidence:.0%})")

    if result.da_output:
        _progress(f"Stage 3 complete — DA assigned: status={result.da_output.status}, escalation={result.da_output.escalation_required}")

    _progress(
        f"Workflow complete — requires_escalation={result.requires_escalation}, "
        f"operating_context={result.operating_context}, stage_errors={result.stage_errors}"
    )
    return result
