"""
MODULE 1: LOGGING TOOL
─────────────────────────────────────────────────────────────────
This is the "ingestion + storage" half of Shadow Work Agent.

Per Ankit's framing:
  "You will be CC'd in every agent interaction happening. You need to
   log what's happening at what time. The log becomes the source of truth."

Responsibilities:
  1. Receive events from all agents
  2. Validate against the data dictionary (closed vocabulary)
  3. Sort and store by case_id
  4. Log every ingestion attempt (including rejections)

This module does NOT do analysis. That's Module 2.
"""
import logging
from typing import Any

from pydantic import ValidationError

from agent.models import IncomingCase, IncomingEvent
from config.settings import settings
from db import db

# ── Structured logging setup ──────────────────────────────────────
logger = logging.getLogger("shadow_work.logging_tool")


class ValidationResult:
    def __init__(self, ok: bool, event_id: str = "", case_id: str = "", reason: str = ""):
        self.ok = ok
        self.event_id = event_id
        self.case_id = case_id
        self.reason = reason


# ─────────────────────────────────────────────────────────────────
# VALIDATION — enforces the data dictionary
# ─────────────────────────────────────────────────────────────────

def validate_event(payload: dict[str, Any]) -> ValidationResult:
    """
    Validate an incoming event against the data dictionary.
    Returns ValidationResult with ok=True/False and rejection reason if any.
    """
    # 1. Schema validation via Pydantic
    try:
        event = IncomingEvent(**payload)
    except ValidationError as e:
        return ValidationResult(
            ok=False,
            event_id=payload.get("event_id", "<unknown>"),
            case_id=payload.get("case_id", "<unknown>"),
            reason=f"schema_violation: {e.errors()[0]['msg']}",
        )

    # 2. Action type must be in closed vocabulary
    if event.action_type not in settings.ALL_ACTION_TYPES:
        return ValidationResult(
            ok=False,
            event_id=event.event_id,
            case_id=event.case_id,
            reason=f"unknown_action_type: '{event.action_type}' not in closed vocabulary",
        )

    # 3. Target entity type must be in closed vocabulary
    if event.target_entity_type not in settings.VALID_TARGET_TYPES:
        return ValidationResult(
            ok=False,
            event_id=event.event_id,
            case_id=event.case_id,
            reason=f"unknown_target_type: '{event.target_entity_type}' not in closed vocabulary",
        )

    return ValidationResult(ok=True, event_id=event.event_id, case_id=event.case_id)


# ─────────────────────────────────────────────────────────────────
# INGESTION — the "CC'd on every interaction" API
# ─────────────────────────────────────────────────────────────────

def ingest_case(case_payload: dict[str, Any]) -> bool:
    """
    Register a new case (or update an existing one).
    Called by the orchestrator when a case is opened/updated.
    """
    try:
        case = IncomingCase(**case_payload)
    except ValidationError as e:
        logger.error(f"case validation failed: {e}")
        db.log_ingestion({
            "status": "rejected",
            "rejection_reason": f"case_schema_violation: {e.errors()[0]['msg']}",
            "raw_payload": case_payload,
        })
        return False

    db.upsert_case(case.model_dump())
    logger.info(f"[case] upserted: {case.case_id} ({case.case_type}, status={case.status})")
    return True


def ingest_event(event_payload: dict[str, Any], source_agent: str = "unknown") -> bool:
    """
    Main entry point for other agents. Every action any agent takes in the
    AITS system should flow through here — "CC'd to Shadow Work."

    Returns True if accepted, False if rejected. Either way, the ingestion
    attempt is logged.
    """
    result = validate_event(event_payload)

    # Log the ingestion attempt regardless of outcome
    db.log_ingestion({
        "source_agent": source_agent,
        "event_id": result.event_id,
        "case_id": result.case_id,
        "status": "accepted" if result.ok else "rejected",
        "rejection_reason": result.reason if not result.ok else None,
        "raw_payload": event_payload,
    })

    if not result.ok:
        logger.warning(
            f"[event] REJECTED from {source_agent}: {result.event_id} — {result.reason}"
        )
        return False

    # Store the validated event
    db.insert_event(event_payload)
    logger.info(
        f"[event] accepted from {source_agent}: {result.event_id} "
        f"(case={result.case_id}, action={event_payload['action_type']})"
    )
    return True


def ingest_batch(events: list[dict[str, Any]], source_agent: str = "batch_loader") -> dict[str, int]:
    """
    Batch ingestion helper. Returns counts of accepted and rejected events.
    """
    accepted, rejected = 0, 0
    for event in events:
        if ingest_event(event, source_agent=source_agent):
            accepted += 1
        else:
            rejected += 1
    logger.info(f"[batch] {source_agent}: {accepted} accepted, {rejected} rejected")
    return {"accepted": accepted, "rejected": rejected}
