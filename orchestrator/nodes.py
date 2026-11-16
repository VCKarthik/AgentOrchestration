"""
nodes.py — LangGraph node functions for the AMP orchestrator.

Each node:
  1. Reconstructs AmpState from the LangGraph TypedDict state
  2. Calls the corresponding _impl function (HTTP call or background task)
  3. Returns a partial dict containing only the fields it updated

stage2_node is a fan-out node that runs RRA/GPA/IAA concurrently via asyncio.gather,
replicating the parallel execution from the old flow.py.

SWA is NOT a node — it fires as asyncio.create_task() inside csa_node and runs
entirely in the background. Its result is stored in state.swa_result when it completes.
"""
from __future__ import annotations

import asyncio
import logging

from .schemas import AmpState
from .shims import compute_operating_context
from .state import AmpGraphState
from .tools import (
    _call_csa_impl,
    _call_da_impl,
    _call_gpa_impl,
    _call_iaa_impl,
    _call_rra_impl,
    _run_swa_background,
)

logger = logging.getLogger(__name__)


def _build_amp_state(state: AmpGraphState) -> AmpState:
    """Reconstruct a full AmpState from the LangGraph TypedDict snapshot."""
    return AmpState(
        task_intake=state.get("task_intake"),
        csa_output=state.get("csa_output"),
        risk_output=state.get("risk_output"),
        governance_output=state.get("governance_output"),
        iaa_output=state.get("iaa_output"),
        da_output=state.get("da_output"),
        swa_result=state.get("swa_result"),
        latency_log=dict(state.get("latency_log") or {}),
        stage_errors=dict(state.get("stage_errors") or {}),
        requires_escalation=state.get("requires_escalation", False),
        operating_context=state.get("operating_context", "full"),
    )


# ── Stage 1 ───────────────────────────────────────────────────────────────────

async def csa_node(state: AmpGraphState) -> dict:
    """Stage 1 — Context Stitching Agent. Always runs first."""
    s = _build_amp_state(state)
    await _call_csa_impl(s)
    # Fire SWA immediately after CSA — non-blocking, result stored in s.swa_result eventually
    asyncio.create_task(_run_swa_background(s))
    return {
        "csa_output":   s.csa_output,
        "latency_log":  s.latency_log,
        "stage_errors": s.stage_errors,
    }


# ── Stage 2 individual nodes (called from stage2_node via asyncio.gather) ─────

async def rra_node(state: AmpGraphState) -> dict:
    """Stage 2a — Risk Radar Agent."""
    s = _build_amp_state(state)
    try:
        await _call_rra_impl(s)
    except Exception as exc:
        logger.exception("rra_node failed")
        s.stage_errors["rra"] = type(exc).__name__
    return {
        "risk_output":  s.risk_output,
        "latency_log":  s.latency_log,
        "stage_errors": s.stage_errors,
    }


async def gpa_node(state: AmpGraphState) -> dict:
    """Stage 2b — Governance & Policy Agent."""
    s = _build_amp_state(state)
    try:
        await _call_gpa_impl(s)
    except Exception as exc:
        logger.exception("gpa_node failed")
        s.stage_errors["gpa"] = type(exc).__name__
    return {
        "governance_output": s.governance_output,
        "latency_log":       s.latency_log,
        "stage_errors":      s.stage_errors,
    }


async def iaa_node(state: AmpGraphState) -> dict:
    """Stage 2c — Intent Anticipation Agent."""
    s = _build_amp_state(state)
    try:
        await _call_iaa_impl(s)
    except Exception as exc:
        logger.exception("iaa_node failed")
        s.stage_errors["iaa"] = type(exc).__name__
    return {
        "iaa_output":   s.iaa_output,
        "latency_log":  s.latency_log,
        "stage_errors": s.stage_errors,
    }


# ── Stage 2 fan-out ───────────────────────────────────────────────────────────

async def stage2_node(state: AmpGraphState) -> dict:
    """
    Fan-out node: resolves which Stage 2 agents are needed, runs them concurrently
    via asyncio.gather, and merges results. Mirrors the old flow.py parallel gather.

    Operating context (D5) is computed here after all Stage 2 results are available.
    Single agent failure is tolerated; 2+ failures are logged but do not raise.
    """
    from .flow_helpers import resolve_stage2_agents

    agents = resolve_stage2_agents(state)
    if not agents:
        logger.info("stage2_node: no Stage 2 agents needed — skipping to DA")
        return {}

    results = await asyncio.gather(*[fn(state) for fn in agents], return_exceptions=True)

    merged: dict = {
        "latency_log":  dict(state.get("latency_log") or {}),
        "stage_errors": dict(state.get("stage_errors") or {}),
    }
    failed: list[str] = []
    for fn, result in zip(agents, results):
        agent_name = fn.__name__.replace("_node", "")
        if isinstance(result, Exception):
            failed.append(agent_name)
            merged["stage_errors"][agent_name] = type(result).__name__
            logger.error("stage2_node: '%s' raised %s", agent_name, result)
        else:
            for k, v in result.items():
                if k == "latency_log":
                    merged["latency_log"].update(v or {})
                elif k == "stage_errors":
                    merged["stage_errors"].update(v or {})
                else:
                    merged[k] = v

    if len(failed) >= 2:
        logger.error("stage2_node: %d agents failed: %s", len(failed), failed)

    # D5: compute operating_context with whatever we have
    combined = {**state, **merged}
    risk_out = combined.get("risk_output")
    iaa_out  = combined.get("iaa_output")
    if risk_out and iaa_out:
        merged["operating_context"] = compute_operating_context(risk_out, iaa_out)
    elif risk_out:
        rc = getattr(risk_out, "operating_context", "full") or "full"
        merged["operating_context"] = "partial" if "partial" in str(rc) else "full"
    elif iaa_out:
        iaa_oc = getattr(iaa_out, "operating_context", "full") or "full"
        merged["operating_context"] = "partial" if "partial" in str(iaa_oc) else "full"

    return merged


# ── Stage 3 ───────────────────────────────────────────────────────────────────

async def da_node(state: AmpGraphState) -> dict:
    """Stage 3 — Delegation Agent. Always runs last."""
    s = _build_amp_state(state)
    await _call_da_impl(s)
    return {
        "da_output":           s.da_output,
        "requires_escalation": s.requires_escalation,
        "latency_log":         s.latency_log,
        "stage_errors":        s.stage_errors,
    }
