"""
state.py — LangGraph TypedDict state for the AMP orchestrator.

AmpGraphState is the canonical state passed between LangGraph nodes.
All fields are optional (total=False) so nodes return only the fields they updated.

latency_log and stage_errors use merge reducers so writes from parallel nodes
accumulate rather than overwrite each other.

AmpState (schemas.py) is still used internally by _impl functions and as the
return type of run_amp_workflow(). AmpGraphState is the LangGraph wire format.
"""
from __future__ import annotations

from typing import Annotated, Any, Optional, TypedDict

from .schemas import (
    CsaOutput,
    DaOutput,
    GovernanceOutput,
    IaaOutput,
    RiskOutput,
    SwaOutput,
    TaskIntake,
)


def _merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}


class AmpGraphState(TypedDict, total=False):
    # Stage 0 — populated before graph runs
    task_intake: Optional[TaskIntake]

    # Stage 1
    csa_output: Optional[CsaOutput]

    # Stage 2 (any subset may be populated)
    risk_output: Optional[RiskOutput]
    governance_output: Optional[GovernanceOutput]
    iaa_output: Optional[IaaOutput]

    # Stage 3
    da_output: Optional[DaOutput]

    # Stage 1 async (populated by background SWA task)
    swa_result: Optional[SwaOutput]

    # Orchestrator-computed — merge reducers so parallel nodes accumulate entries
    latency_log: Annotated[dict[str, float], _merge_dicts]
    stage_errors: Annotated[dict[str, Any], _merge_dicts]

    # Orchestrator-computed scalars
    requires_escalation: bool
    operating_context: str
