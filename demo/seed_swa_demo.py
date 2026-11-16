"""
demo/seed_swa_demo.py — Pre-seed SWA's activity_log with historical patterns.

Seeds 3 patterns across 5 historical cases designed to fire all 3 heuristic detectors:

  Pattern A — Repetition (detect_repetition):
    auto_invoice_bot repeatedly approves invoices on sys_procurement_queue.
    5 events across 2 cases → fires when occurrences ≥ MIN_REPETITION_THRESHOLD (3).
    Decision: escalate (approval-type action always high-risk).

  Pattern B — Cross-case (detect_cross_case):
    claims_processor_01 sends follow-ups to different claimants across 3 separate cases.
    4 events, 3 cases, 4 unique targets → fires when ≥2 cases + ≥3 occurrences + ≥2 targets.
    Decision: recommend (sent_followup is AUTOMATABLE).

  Pattern C — Temporal regularity (detect_temporal_regularity):
    compliance_scheduler runs status_check on sys_compliance_registry every 24 hours.
    5 events at exactly 24h intervals → regularity_score ≈ 1.0, fires when score ≥ 0.7.
    Decision: recommend (status_check is AUTOMATABLE).

Idempotent — SWA's ingest_batch uses INSERT OR IGNORE, so re-running is safe.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

# ── Add SWA to sys.path (mirrors orchestrator/tools.py) ──────────────────────
_SWA_PATH = os.path.join(os.path.dirname(__file__), "..", "SWA")
if _SWA_PATH not in sys.path:
    sys.path.insert(0, _SWA_PATH)

# SWA's orchestrator opens output/agent.log at import time
os.makedirs(os.path.join(os.path.dirname(__file__), "..", "output"), exist_ok=True)


def _evt(case_id: str, actor_id: str, actor_type: str, action_type: str,
         target_entity: str, target_entity_type: str,
         ts: datetime, outcome: str = "success",
         context_payload: dict | None = None) -> dict:
    return {
        "event_id":           f"evt_seed_{uuid.uuid4().hex[:10]}",
        "case_id":            case_id,
        "timestamp":          ts.isoformat(),
        "actor_id":           actor_id,
        "actor_type":         actor_type,
        "action_type":        action_type,
        "target_entity":      target_entity,
        "target_entity_type": target_entity_type,
        "parent_task_id":     None,
        "context_payload":    context_payload or {},
        "outcome":            outcome,
    }


def _case(case_id: str, case_type: str, domain: str,
          primary_human: str, created_at: datetime,
          closed_at: datetime | None = None) -> dict:
    payload = {
        "case_id":         case_id,
        "case_type":       case_type,
        "status":          "closed" if closed_at else "in_progress",
        "created_at":      created_at.isoformat(),
        "closed_at":       closed_at.isoformat() if closed_at else None,
        "domain_metadata": {"domain": domain, "primary_human": primary_human},
    }
    return payload


def seed_swa_demo() -> dict:
    """
    Seed SWA DB with historical demo patterns. Returns counts of accepted/rejected events.
    Safe to call multiple times — duplicates are silently ignored.
    """
    from agent.logging_tool import ingest_case, ingest_batch  # type: ignore[import]

    now = datetime.now(timezone.utc)

    # ── Pattern A cases ───────────────────────────────────────────────────────
    # auto_invoice_bot auto-approves invoices without human review
    case_a1 = _case("hist_vnd_a01", "vendor_onboarding", "procurement",
                    "user_proc_01",
                    created_at=now - timedelta(days=45),
                    closed_at=now - timedelta(days=35))
    case_a2 = _case("hist_vnd_a02", "vendor_onboarding", "procurement",
                    "user_proc_02",
                    created_at=now - timedelta(days=30),
                    closed_at=now - timedelta(days=22))

    events_a = [
        # Case A1: 3 approvals by the bot
        _evt("hist_vnd_a01", "auto_invoice_bot", "agent", "approved",
             "sys_procurement_queue", "internal_system",
             now - timedelta(days=44), context_payload={"channel": "automated"}),
        _evt("hist_vnd_a01", "auto_invoice_bot", "agent", "approved",
             "sys_procurement_queue", "internal_system",
             now - timedelta(days=43), context_payload={"channel": "automated"}),
        _evt("hist_vnd_a01", "auto_invoice_bot", "agent", "approved",
             "sys_procurement_queue", "internal_system",
             now - timedelta(days=42), context_payload={"channel": "automated"}),
        # Case A2: 2 more approvals by the same bot
        _evt("hist_vnd_a02", "auto_invoice_bot", "agent", "approved",
             "sys_procurement_queue", "internal_system",
             now - timedelta(days=29), context_payload={"channel": "automated"}),
        _evt("hist_vnd_a02", "auto_invoice_bot", "agent", "approved",
             "sys_procurement_queue", "internal_system",
             now - timedelta(days=28), context_payload={"channel": "automated"}),
    ]

    # ── Pattern B cases ───────────────────────────────────────────────────────
    # claims_processor_01 sends follow-ups to different claimants across cases
    case_b1 = _case("hist_clm_b01", "auto_claim", "auto_claims",
                    "user_clm_01", created_at=now - timedelta(days=25))
    case_b2 = _case("hist_clm_b02", "auto_claim", "auto_claims",
                    "user_clm_02", created_at=now - timedelta(days=20))
    case_b3 = _case("hist_clm_b03", "auto_claim", "auto_claims",
                    "user_clm_01", created_at=now - timedelta(days=15))

    events_b = [
        _evt("hist_clm_b01", "claims_processor_01", "human", "sent_followup",
             "claimant_jones", "external_contact",
             now - timedelta(days=24), outcome="pending",
             context_payload={"channel": "email"}),
        _evt("hist_clm_b02", "claims_processor_01", "human", "sent_followup",
             "claimant_smith", "external_contact",
             now - timedelta(days=19), outcome="pending",
             context_payload={"channel": "email"}),
        _evt("hist_clm_b03", "claims_processor_01", "human", "sent_followup",
             "claimant_patel", "external_contact",
             now - timedelta(days=14), outcome="pending",
             context_payload={"channel": "email"}),
        _evt("hist_clm_b03", "claims_processor_01", "human", "sent_followup",
             "claimant_wong", "external_contact",
             now - timedelta(days=13), outcome="pending",
             context_payload={"channel": "email"}),
    ]

    # ── Pattern C case ────────────────────────────────────────────────────────
    # compliance_scheduler runs daily status checks like clockwork
    case_c1 = _case("hist_cmp_c01", "compliance_review", "compliance",
                    "user_legal_01", created_at=now - timedelta(days=10))

    events_c = [
        _evt("hist_cmp_c01", "compliance_scheduler", "agent", "status_check",
             "sys_compliance_registry", "internal_system",
             now - timedelta(hours=96), context_payload={"trigger": "scheduled"}),
        _evt("hist_cmp_c01", "compliance_scheduler", "agent", "status_check",
             "sys_compliance_registry", "internal_system",
             now - timedelta(hours=72), context_payload={"trigger": "scheduled"}),
        _evt("hist_cmp_c01", "compliance_scheduler", "agent", "status_check",
             "sys_compliance_registry", "internal_system",
             now - timedelta(hours=48), context_payload={"trigger": "scheduled"}),
        _evt("hist_cmp_c01", "compliance_scheduler", "agent", "status_check",
             "sys_compliance_registry", "internal_system",
             now - timedelta(hours=24), context_payload={"trigger": "scheduled"}),
        _evt("hist_cmp_c01", "compliance_scheduler", "agent", "status_check",
             "sys_compliance_registry", "internal_system",
             now - timedelta(hours=1), context_payload={"trigger": "scheduled"}),
    ]

    # ── Ingest all cases ──────────────────────────────────────────────────────
    for case in [case_a1, case_a2, case_b1, case_b2, case_b3, case_c1]:
        ingest_case(case)

    # ── Ingest all events ─────────────────────────────────────────────────────
    all_events = events_a + events_b + events_c
    result = ingest_batch(all_events, source_agent="demo_seed")
    return result


if __name__ == "__main__":
    result = seed_swa_demo()
    print(f"SWA demo seed complete: {result}")
