"""
tools.py — HTTP calls to AMP agent FastAPI servers.

One private _impl function per agent. Each function:
  - Accepts AmpState (mutates it in-place)
  - Makes the HTTP call
  - Validates the response schema
  - Applies the relevant shim

Called exclusively by nodes.py. Port constants are the single source of truth.

SWA has no HTTP server — _run_swa_background imports analyze() directly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import httpx
from langsmith import traceable
from pydantic import ValidationError

from .exceptions import AgentUnreachableError, AgentResponseError, AgentSchemaError
from .schemas import (
    AmpState, CsaOutput, RiskOutput, GovernanceOutput, IaaOutput, DaOutput,
)
from .shims import (
    csa_to_rra, csa_to_gpa, csa_to_iaa,
    rra_to_amp, gpa_to_amp, iaa_to_amp, da_to_amp,
    build_da_task, compute_requires_escalation,
    case_history_to_incoming_events,
)

logger = logging.getLogger(__name__)

# ── Port constants ─────────────────────────────────────────────────────────────
CSA_PORT = 8001
RRA_PORT = 8002
IAA_PORT = 8003
GPA_PORT = 8004
DA_PORT  = 8005

AGENT_TIMEOUT = 30.0
CSA_TIMEOUT   = 120.0  # CSA loads sentence-transformers model + indexes all records on first request
IAA_TIMEOUT   = 120.0  # IAA makes an LLM call (Gemini) — needs a longer timeout

# Per-agent base URLs — override via env for Docker networking.
# Defaults to localhost for local dev; set CSA_URL=http://csa:8001 etc. in compose.
_AGENT_URLS: dict[int, str] = {
    CSA_PORT: os.getenv("CSA_URL",  f"http://localhost:{CSA_PORT}"),
    RRA_PORT: os.getenv("RRA_URL",  f"http://localhost:{RRA_PORT}"),
    IAA_PORT: os.getenv("IAA_URL",  f"http://localhost:{IAA_PORT}"),
    GPA_PORT: os.getenv("GPA_URL",  f"http://localhost:{GPA_PORT}"),
    DA_PORT:  os.getenv("DA_URL",   f"http://localhost:{DA_PORT}"),
}


def _url(port: int, path: str) -> str:
    return f"{_AGENT_URLS[port]}{path}"


def _record_latency(state: AmpState, agent: str, start: float) -> None:
    state.latency_log[agent] = round((time.perf_counter() - start) * 1000, 2)


# ── CSA ────────────────────────────────────────────────────────────────────────

@traceable(name="call_csa")
async def _call_csa_impl(state: AmpState) -> CsaOutput:
    intake = state.task_intake
    payload: dict = {
        "task_text": getattr(intake, "description", None) or getattr(intake, "title", None) or "",
        "case_id":   getattr(intake, "case_id", None),
        "case_type": getattr(intake, "case_type", None),
    }
    start = time.perf_counter()
    logger.info("call_csa: sending request", extra={"case_id": payload.get("case_id")})
    try:
        async with httpx.AsyncClient(timeout=CSA_TIMEOUT) as client:
            resp = await client.post(_url(CSA_PORT, "/query"), json=payload)
    except httpx.TimeoutException as exc:
        raise AgentResponseError("csa", 504, f"Timeout after {CSA_TIMEOUT}s") from exc
    except httpx.ConnectError as exc:
        raise AgentUnreachableError("csa", CSA_PORT) from exc

    _record_latency(state, "csa", start)

    if resp.status_code != 200:
        raise AgentResponseError("csa", resp.status_code, resp.text)

    raw = resp.json()
    try:
        csa_out = CsaOutput(**raw)
    except ValidationError as exc:
        raise AgentSchemaError("csa", exc) from exc

    state.csa_output = csa_out
    logger.info("call_csa: success", extra={"task_id": csa_out.task_id})
    return csa_out


# ── RRA ────────────────────────────────────────────────────────────────────────

@traceable(name="call_rra")
async def _call_rra_impl(state: AmpState) -> RiskOutput:
    payload = csa_to_rra(state.csa_output)
    start = time.perf_counter()
    logger.info("call_rra: sending request", extra={"task_id": payload.get("task_id")})
    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.post(_url(RRA_PORT, "/predict"), json=payload)
    except httpx.TimeoutException as exc:
        raise AgentResponseError("rra", 504, f"Timeout after {AGENT_TIMEOUT}s") from exc
    except httpx.ConnectError as exc:
        raise AgentUnreachableError("rra", RRA_PORT) from exc

    _record_latency(state, "rra", start)

    if resp.status_code != 200:
        raise AgentResponseError("rra", resp.status_code, resp.text)

    raw = resp.json()
    mapped = rra_to_amp(raw)
    try:
        risk_out = RiskOutput(**mapped)
    except ValidationError as exc:
        raise AgentSchemaError("rra", exc) from exc

    state.risk_output = risk_out
    logger.info("call_rra: success", extra={"risk_level": risk_out.overall_risk_level})
    return risk_out


# ── GPA ────────────────────────────────────────────────────────────────────────

@traceable(name="call_gpa")
async def _call_gpa_impl(state: AmpState) -> GovernanceOutput:
    payload = csa_to_gpa(state.task_intake, state.csa_output)
    start = time.perf_counter()
    logger.info("call_gpa: sending request", extra={"task_id": payload.get("task_id")})
    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.post(_url(GPA_PORT, "/evaluate-task"), json=payload)
    except httpx.TimeoutException as exc:
        raise AgentResponseError("gpa", 504, f"Timeout after {AGENT_TIMEOUT}s") from exc
    except httpx.ConnectError as exc:
        raise AgentUnreachableError("gpa", GPA_PORT) from exc

    _record_latency(state, "gpa", start)

    if resp.status_code != 200:
        raise AgentResponseError("gpa", resp.status_code, resp.text)

    raw = resp.json()
    mapped = gpa_to_amp(raw)
    try:
        gov_out = GovernanceOutput(**mapped)
    except ValidationError as exc:
        raise AgentSchemaError("gpa", exc) from exc

    state.governance_output = gov_out
    logger.info("call_gpa: success", extra={"decision": gov_out.decision})
    return gov_out


# ── IAA ────────────────────────────────────────────────────────────────────────

@traceable(name="call_iaa")
async def _call_iaa_impl(state: AmpState) -> IaaOutput:
    payload = csa_to_iaa(state.csa_output, state.risk_output)
    start = time.perf_counter()
    logger.info("call_iaa: sending request")
    try:
        async with httpx.AsyncClient(timeout=IAA_TIMEOUT) as client:
            resp = await client.post(_url(IAA_PORT, "/predict"), json=payload)
    except httpx.TimeoutException as exc:
        raise AgentResponseError("iaa", 504, f"Timeout after {IAA_TIMEOUT}s") from exc
    except httpx.ConnectError as exc:
        raise AgentUnreachableError("iaa", IAA_PORT) from exc
    except httpx.ReadError as exc:
        raise AgentResponseError("iaa", 503, "Connection dropped mid-response (ReadError)") from exc

    _record_latency(state, "iaa", start)

    if resp.status_code != 200:
        raise AgentResponseError("iaa", resp.status_code, resp.text)

    raw = resp.json()
    mapped = iaa_to_amp(raw)
    try:
        iaa_out = IaaOutput(**mapped)
    except ValidationError as exc:
        raise AgentSchemaError("iaa", exc) from exc

    state.iaa_output = iaa_out
    logger.info("call_iaa: success", extra={"operating_context": iaa_out.operating_context})
    return iaa_out


# ── DA ─────────────────────────────────────────────────────────────────────────

@traceable(name="call_da")
async def _call_da_impl(state: AmpState) -> DaOutput:
    meta_dict: dict = {"stage_errors": state.stage_errors}

    iaa_task_item = None
    if state.iaa_output and state.iaa_output.task_list:
        first = state.iaa_output.task_list[0] if state.iaa_output.task_list else None
        if first is not None:
            from types import SimpleNamespace
            if hasattr(first, "model_dump"):
                iaa_task_item = SimpleNamespace(**first.model_dump())
            elif isinstance(first, dict):
                iaa_task_item = SimpleNamespace(**first)
            else:
                iaa_task_item = first

    gpa_raw: dict = {}
    if state.governance_output:
        gpa_raw = state.governance_output.model_dump()

    intake_dict: dict = {}
    if state.task_intake:
        intake_dict = state.task_intake.model_dump()

    _DA_TASK_TYPES = {
        "claim_review", "customer_inquiry", "technical_support",
        "vendor_onboarding", "compliance_review", "financial_approval",
        "fraud_investigation", "general",
    }

    def _coerce_task_type(v: str | None) -> str:
        return v if v in _DA_TASK_TYPES else "general"

    if iaa_task_item is None:
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        payload = {
            "task_id":          intake_dict.get("task_id", "unknown"),
            "task_type":        _coerce_task_type(intake_dict.get("task_type")),
            "title":            intake_dict.get("title", "Untitled Task"),
            "description":      intake_dict.get("description", ""),
            "priority":         intake_dict.get("priority", "medium"),
            "urgency":          intake_dict.get("urgency", "moderate"),
            "estimated_effort": intake_dict.get("estimated_effort") or 1.0,
            "due_date":         intake_dict.get("due_date") or (now + timedelta(hours=24)).isoformat(),
            "business_domain":  intake_dict.get("business_domain", "general"),
            "requester":        intake_dict.get("requester", "orchestrator"),
        }
    else:
        payload = build_da_task(intake_dict, iaa_task_item, gpa_raw, meta_dict)
        if "task_type" in payload:
            payload["task_type"] = _coerce_task_type(payload.get("task_type"))

    if state.risk_output:
        payload["risk_flags"] = [
            {
                "flag_id":     f,
                "label":       f,
                "severity":    state.risk_output.overall_risk_level or "low",
                "description": f,
            }
            for f in (state.risk_output.risk_flags or [])
        ]

    start = time.perf_counter()
    logger.info("call_da: sending request", extra={"task_id": payload.get("task_id")})
    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.post(_url(DA_PORT, "/predict"), json=payload)
    except httpx.TimeoutException as exc:
        raise AgentResponseError("da", 504, f"Timeout after {AGENT_TIMEOUT}s") from exc
    except httpx.ConnectError as exc:
        raise AgentUnreachableError("da", DA_PORT) from exc

    _record_latency(state, "da", start)

    if resp.status_code != 200:
        raise AgentResponseError("da", resp.status_code, resp.text)

    raw = resp.json()
    mapped = da_to_amp(raw)
    try:
        da_out = DaOutput(**mapped)
    except ValidationError as exc:
        raise AgentSchemaError("da", exc) from exc

    state.da_output = da_out
    state.requires_escalation = compute_requires_escalation(
        state.risk_output,
        state.governance_output,
        state.iaa_output,
        da_out,
    )
    logger.info(
        "call_da: success",
        extra={"escalation_required": da_out.escalation_required, "status": da_out.status},
    )
    return da_out


# ── SWA — direct import (no HTTP server) ──────────────────────────────────────

async def _run_swa_background(state: AmpState) -> None:
    """
    Per-case SWA hook fired via asyncio.create_task() inside csa_node.

    Currently INGEST-ONLY: it writes the new case + its events into SWA's
    SQLite DB so the corpus grows with every workflow run, but does NOT
    invoke analyze(). Pattern mining is on-demand from the Observatory's
    "Run analysis now" button.

    All exceptions are swallowed — SWA failure never surfaces to the
    primary workflow.
    """
    start = time.perf_counter()
    try:
        import os
        import sys
        swa_path = os.path.join(os.path.dirname(__file__), "..", "SWA")
        if swa_path not in sys.path:
            sys.path.insert(0, swa_path)

        # SWA's orchestrator.py opens "output/agent.log" at import time
        os.makedirs("output", exist_ok=True)

        from agent.logging_tool import ingest_case, ingest_batch  # type: ignore[import]

        csa_out = state.csa_output
        if csa_out is None:
            state.stage_errors["swa"] = "CsaOutputMissing"
            return

        context = csa_out.context
        history_raw: list[dict] = []
        if context and context.case_history:
            history_raw = [
                h if isinstance(h, dict) else h.model_dump()
                for h in context.case_history
            ]

        events_raw = case_history_to_incoming_events(history_raw)

        case_id = csa_out.case_id or "unknown"
        case_payload = {
            "case_id":         case_id,
            "case_type":       csa_out.case_type or "general",
            "status":          "in_progress",
            "created_at":      datetime.now(timezone.utc).isoformat(),
            "closed_at":       None,
            "domain_metadata": {},
        }

        loop = asyncio.get_event_loop()

        def _ingest_only():
            # Write the case + its events to SWA's DB so the corpus grows
            # over time — but DO NOT run analyze() here.
            #
            # Pattern mining is now manual: the presenter clicks
            # "Run analysis now" in the Observatory when they want findings
            # generated. Auto-running analyze() per workflow submission
            # produced confusing demo state (every Case Workspace click
            # silently spawned a new analysis_run + cluster_snapshot).
            ingest_case(case_payload)
            if events_raw:
                ingest_batch(events_raw, source_agent="orchestrator")

        await loop.run_in_executor(None, _ingest_only)
        logger.info("_run_swa_background: case + events ingested (analyze deferred)")

    except Exception:
        logger.exception("_run_swa_background: SWA failed — suppressed")
        state.stage_errors["swa"] = "SwaRuntimeError"
    finally:
        _record_latency(state, "swa", start)
