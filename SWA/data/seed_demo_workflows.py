"""
Domain-tailored seed for the three demo workflows from the kickoff doc:
  1. vendor_onboarding   — missing-cert → repeated request_document follow-ups
  2. claim_review        — repeated sent_followup pattern + risk_flagged on prior delays
  3. interview_scheduling — invite → repeated sent_reminder until confirmed

Each workflow gets ~30 cases with realistic, repeatable patterns SWA can
detect. Volume + repetition is what makes the demo's findings tab show
domain-relevant clusters instead of generic noise.

Run:
    python3 -m SWA.data.seed_demo_workflows         # from repo root
    python3 SWA/data/seed_demo_workflows.py         # also works

Idempotent: cases use deterministic IDs `seed_vnd_*`, `seed_clm_*`,
`seed_int_*`. Existing cases are upserted; existing events are deduped by
event_id.
"""
from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running from repo root or from SWA/
SWA_ROOT = Path(__file__).resolve().parent.parent
if str(SWA_ROOT) not in sys.path:
    sys.path.insert(0, str(SWA_ROOT))

from agent.logging_tool import ingest_batch, ingest_case  # noqa: E402

random.seed(42)  # deterministic output across runs

NOW = datetime.now(timezone.utc)
WINDOW_START = NOW - timedelta(days=60)


# ── Workflow templates ──────────────────────────────────────────────────────
# Each step: (action_type, target_entity_type, actor_id_pool, hours_after_prev)
# repeat=N means SWA will see the same action across the last N steps — that's
# the repetition pattern the heuristic detector latches onto.

VENDOR_TEMPLATE = {
    "case_type": "vendor_onboarding",
    "case_prefix": "seed_vnd",
    "actors_human": ["procurement_lead@corp.com", "compliance_officer@corp.com",
                     "vendor_mgr_01@corp.com", "vendor_mgr_02@corp.com"],
    "actors_agent": ["context_stitching_agent", "governance_policy_agent",
                     "risk_radar_agent", "delegation_agent"],
    "steps": [
        # (action,                   target_type,        actor_kind, +hours)
        ("case_opened",              "task",             "human",    0),
        ("context_gathered",         "internal_system",  "agent",    1),
        ("policy_check",             "internal_system",  "agent",    2),
        ("requested_document",       "external_contact", "human",    4),     # 1st request
        ("sent_reminder",            "external_contact", "human",    52),    # follow-up @ 48h
        ("sent_reminder",            "external_contact", "human",    100),   # follow-up @ 96h — pattern!
        ("received_message",         "external_contact", "human",    120),
        ("viewed_document",          "document",         "human",    121),
        ("approved",                 "task",             "human",    125),
        ("case_closed",              "task",             "human",    126),
    ],
}

CLAIM_TEMPLATE = {
    "case_type": "claim_review",
    "case_prefix": "seed_clm",
    "actors_human": ["claims_adjuster_01@corp.com", "claims_adjuster_02@corp.com",
                     "claims_lead@corp.com", "fraud_review@corp.com"],
    "actors_agent": ["context_stitching_agent", "risk_radar_agent",
                     "governance_policy_agent", "delegation_agent"],
    "steps": [
        ("case_opened",              "task",             "human",    0),
        ("context_gathered",         "internal_system",  "agent",    1),
        ("risk_flagged",             "task",             "agent",    2),
        ("policy_check",             "internal_system",  "agent",    3),
        ("requested_document",       "external_contact", "human",    6),
        ("sent_followup",            "external_contact", "human",    50),    # follow-up
        ("sent_followup",            "external_contact", "human",    100),   # follow-up — pattern!
        ("sent_followup",            "external_contact", "human",    150),   # follow-up — pattern!
        ("received_message",         "external_contact", "human",    170),
        ("approved",                 "task",             "human",    175),
        ("case_closed",              "task",             "human",    176),
    ],
}

INTERVIEW_TEMPLATE = {
    "case_type": "interview_scheduling",
    "case_prefix": "seed_int",
    "actors_human": ["recruiter_01@corp.com", "recruiter_02@corp.com",
                     "hiring_mgr_eng@corp.com", "hiring_mgr_pm@corp.com"],
    "actors_agent": ["context_stitching_agent", "intent_anticipation_agent",
                     "delegation_agent"],
    "steps": [
        ("case_opened",              "task",             "human",    0),
        ("context_gathered",         "internal_system",  "agent",    1),
        ("scheduled_meeting",        "external_contact", "human",    3),
        ("sent_reminder",            "external_contact", "human",    24),    # day-before reminder
        ("sent_reminder",            "external_contact", "human",    47),    # hour-before reminder — pattern!
        ("status_check",             "external_contact", "human",    49),
        ("received_message",         "external_contact", "human",    50),
        ("intent_predicted",         "task",             "agent",    51),    # IAA suggests follow-up
        ("scheduled_meeting",        "external_contact", "human",    72),    # follow-up review
        ("case_closed",              "task",             "human",    100),
    ],
}

ALL_TEMPLATES = [VENDOR_TEMPLATE, CLAIM_TEMPLATE, INTERVIEW_TEMPLATE]
CASES_PER_WORKFLOW = 30


def _build_case(template: dict, idx: int) -> tuple[dict, list[dict]]:
    case_id = f"{template['case_prefix']}_{idx:03d}"
    base_offset_hours = random.randint(0, 60 * 24 - 200)
    base_ts = WINDOW_START + timedelta(hours=base_offset_hours)

    case_payload = {
        "case_id":   case_id,
        "case_type": template["case_type"],
        "status":    "closed",
        "created_at": base_ts.isoformat(),
        "closed_at":  (base_ts + timedelta(hours=template["steps"][-1][3])).isoformat(),
        "domain_metadata": {"seed_source": "demo_workflow_seed"},
    }

    events = []
    for step_i, (action, target_type, actor_kind, h_after) in enumerate(template["steps"]):
        ts = base_ts + timedelta(hours=h_after, minutes=random.randint(0, 59))
        if actor_kind == "human":
            actor_id = random.choice(template["actors_human"])
            actor_type = "human"
        else:
            actor_id = random.choice(template["actors_agent"])
            actor_type = "agent"

        # Target entity: pick something that repeats so the cross-case detector
        # bins similar steps together.
        if target_type == "external_contact":
            target_entity = f"vendor_{idx % 5}" if "vendor" in template["case_prefix"] else \
                            f"claimant_{idx % 5}" if "clm"   in template["case_prefix"] else \
                            f"candidate_{idx % 5}"
        elif target_type == "document":
            target_entity = f"doc_{case_id}_{step_i}"
        elif target_type == "task":
            target_entity = case_id
        else:  # internal_system
            target_entity = "primary_workflow_engine"

        events.append({
            "event_id":           f"{case_id}_e{step_i:02d}_{uuid.uuid4().hex[:6]}",
            "case_id":            case_id,
            "timestamp":          ts.isoformat(),
            "actor_id":           actor_id,
            "actor_type":         actor_type,
            "action_type":        action,
            "target_entity":      target_entity,
            "target_entity_type": target_type,
            "parent_task_id":     None,
            "context_payload":    {"step": step_i},
            "outcome":            "success" if action != "risk_flagged" else "pending",
        })

    return case_payload, events


def seed() -> dict[str, dict[str, int]]:
    """Seed all three demo workflows. Returns counts per workflow."""
    summary: dict[str, dict[str, int]] = {}
    for template in ALL_TEMPLATES:
        case_count = 0
        event_count = 0
        all_events: list[dict] = []
        for i in range(1, CASES_PER_WORKFLOW + 1):
            case_payload, events = _build_case(template, i)
            if ingest_case(case_payload):
                case_count += 1
            all_events.extend(events)
        result = ingest_batch(all_events, source_agent="demo_workflow_seed")
        event_count = result.get("accepted", 0)
        summary[template["case_type"]] = {
            "cases":            case_count,
            "events_accepted":  event_count,
            "events_rejected":  result.get("rejected", 0),
        }
    return summary


if __name__ == "__main__":
    print("Seeding domain-tailored demo workflows...")
    summary = seed()
    total_cases = sum(s["cases"] for s in summary.values())
    total_events = sum(s["events_accepted"] for s in summary.values())
    print()
    print(f"{'Workflow':<25}  {'Cases':>6}  {'Events':>7}  {'Rejected':>9}")
    print("-" * 55)
    for ct, stats in summary.items():
        print(f"{ct:<25}  {stats['cases']:>6}  {stats['events_accepted']:>7}  {stats['events_rejected']:>9}")
    print("-" * 55)
    print(f"{'TOTAL':<25}  {total_cases:>6}  {total_events:>7}")
