"""
flow_helpers.py — Shared Stage 2 routing logic.

Used by both nodes.py (LangGraph stage2_node) and flow.py.
Extracted from the old flow.py _resolve_stage2() so the keyword sets
and routing conditions live in exactly one place.
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

_RISK_KEYWORDS = frozenset({"risk", "compliance", "fraud", "missing", "document", "regulatory"})
_GOV_KEYWORDS  = frozenset({"policy", "approval", "governance", "escalat", "threshold", "legal"})
_IAA_KEYWORDS  = frozenset({"next", "predict", "timeline", "recommend", "workflow", "schedule"})


def resolve_stage2_agents(state: dict) -> list[Callable]:
    """
    Determine which Stage 2 node functions to run based on task_intake + csa_output signals.
    Returns a (possibly empty) list of async node callables: rra_node, gpa_node, iaa_node.

    Imported lazily to avoid circular imports (nodes.py imports this module).
    """
    # Lazy import to avoid circular: nodes imports flow_helpers, flow_helpers imports nodes
    from .nodes import rra_node, gpa_node, iaa_node  # noqa: PLC0415

    task_intake = state.get("task_intake")
    csa_output  = state.get("csa_output")

    combined_text = " ".join(filter(None, [
        getattr(task_intake, "description", None),
        getattr(task_intake, "title", None),
        getattr(task_intake, "task_type", None),
        getattr(task_intake, "case_type", None),
    ])).lower()

    validation = None
    if csa_output and getattr(csa_output, "validation", None):
        validation = csa_output.validation
    missing_fields: list[str] = getattr(validation, "missing_fields", []) or []
    validation_status: str = (getattr(validation, "status", None) or "COMPLETE").upper()

    # RRA and GPA always run — both are rule-based and fast (≤300 ms each),
    # and the demo expects every case to surface a risk verdict and a policy
    # decision. Earlier keyword/whitelist gating silently dropped them on
    # claim_review and interview_scheduling cases (no matching keywords),
    # producing workflows with no GPA / RRA output.
    needs_rra = True
    needs_gpa = True
    needs_iaa = True
    _ = combined_text, missing_fields, validation_status  # kept for logging clarity

    agents: list[Callable] = []
    if needs_rra:
        agents.append(rra_node)
    if needs_gpa:
        agents.append(gpa_node)
    if needs_iaa:
        agents.append(iaa_node)

    logger.info("resolve_stage2_agents: rra=%s gpa=%s iaa=%s", needs_rra, needs_gpa, needs_iaa)
    return agents
