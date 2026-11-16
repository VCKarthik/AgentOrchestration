"""
Synthetic data generator — 200+ cases across 6 domains.

Supports incremental appending so you can grow the dataset over time
and watch DBSCAN's clusters evolve.

Usage:
  python -m data.synthetic_events                       # generate fresh 200 cases
  python -m data.synthetic_events --count 200           # explicit count
  python -m data.synthetic_events --append --count 20   # add 20 more on top
"""
import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.logging_tool import ingest_batch, ingest_case
from db import db


# ──────────────────────────────────────────────────────────────────
# DOMAIN TEMPLATES
# ──────────────────────────────────────────────────────────────────
# Each domain defines:
#   - case_type: human-readable type
#   - actors: who works these cases (humans + which agents touch them)
#   - workflow: the typical sequence of events
#   - external_contacts: pool of contacts to chase
#   - documents: pool of documents to request
#
# These templates produce REALISTIC events that 5 other AITS agents
# would write into the activity_log if they were processing real cases.

DOMAINS = {
    "vendor_onboarding": {
        "case_type": "vendor_onboarding",
        "humans": ["user_proc_01", "user_proc_02", "user_proc_03"],
        "external_pool": ["vendor_acme", "vendor_globex", "vendor_initech",
                          "vendor_umbrella", "vendor_stark", "vendor_wayne"],
        "documents": ["tax_id", "compliance_cert", "insurance_proof", "w9_form"],
        "internal_systems": ["sys_procurement_queue", "sys_compliance_db"],
    },
    "auto_claims": {
        "case_type": "auto_claim",
        "humans": ["user_clm_01", "user_clm_02", "user_clm_03", "user_clm_04"],
        "external_pool": ["claimant_001", "claimant_002", "claimant_003",
                          "claimant_004", "claimant_005", "claimant_006"],
        "documents": ["police_report", "repair_estimate", "photos", "medical_report"],
        "internal_systems": ["sys_claims_queue", "sys_fraud_check"],
    },
    "recruiting": {
        "case_type": "recruiting",
        "humans": ["user_rec_01", "user_rec_02"],
        "external_pool": ["candidate_alpha", "candidate_bravo", "candidate_charlie",
                          "candidate_delta", "candidate_echo", "candidate_foxtrot"],
        "documents": ["references", "background_check", "transcripts", "portfolio"],
        "internal_systems": ["sys_ats", "sys_hr_dashboard"],
    },
    "construction": {
        "case_type": "residential_construction",
        "humans": ["user_pm_01", "user_pm_02", "user_pm_03"],
        "external_pool": ["client_alpha", "client_bravo", "client_charlie",
                          "client_delta", "client_echo"],
        "documents": ["plot_layout", "permit_approval", "soil_report", "blueprints"],
        "internal_systems": ["sys_permit_tracker", "sys_project_dashboard"],
    },
    "healthcare_referrals": {
        "case_type": "healthcare_referral",
        "humans": ["user_clin_01", "user_clin_02"],
        "external_pool": ["patient_001", "patient_002", "patient_003",
                          "patient_004", "patient_005"],
        "documents": ["medical_history", "insurance_auth", "lab_results", "imaging"],
        "internal_systems": ["sys_referrals_queue", "sys_ehr"],
    },
    "legal_intake": {
        "case_type": "legal_intake",
        "humans": ["user_legal_01", "user_legal_02"],
        "external_pool": ["intake_001", "intake_002", "intake_003",
                          "intake_004", "intake_005"],
        "documents": ["retainer_agreement", "evidence_docs", "id_verification"],
        "internal_systems": ["sys_case_db", "sys_conflict_check"],
    },
}

DOMAIN_KEYS = list(DOMAINS.keys())


# ──────────────────────────────────────────────────────────────────
# WORKFLOW TEMPLATES
# ──────────────────────────────────────────────────────────────────
# These define what the OTHER 5 AGENTS would do when processing a case.
# Each template is a sequence of (actor, action, target_kind, hour_offset_h)
# triples that get filled in with concrete values per case.

def case_workflow_template(rng: random.Random) -> list[dict]:
    """
    Return a workflow — list of event 'recipes'. Some randomness in the
    workflow gives DBSCAN realistic variety to discover.

    Each recipe has:
      actor_kind: "human" | one of the 5 agents
      action_type: action vocabulary
      target_kind: "external" | "internal_sys" | "task" | "document"
      offset_hours: hours since case_start
    """
    base_workflow = [
        # Case opening (orchestrator-driven)
        {"actor_kind": "human", "action_type": "case_opened", "target_kind": "task", "offset_hours": 0.0},

        # Context Stitching — gathers background
        {"actor_kind": "context_stitching_agent", "action_type": "context_gathered", "target_kind": "internal_sys", "offset_hours": 0.5},
        {"actor_kind": "context_stitching_agent", "action_type": "viewed_document", "target_kind": "document", "offset_hours": 0.6},

        # Risk Radar — flags missing inputs (THIS IS A KEY PATTERN: Risk Radar
        # always sends a follow-up early in the case lifecycle)
        {"actor_kind": "risk_radar_agent", "action_type": "risk_flagged", "target_kind": "internal_sys", "offset_hours": 1.0},
        {"actor_kind": "risk_radar_agent", "action_type": "sent_followup", "target_kind": "external", "offset_hours": 2.0},

        # Governance — checks compliance (ANOTHER KEY PATTERN: Governance
        # does redundant policy checks)
        {"actor_kind": "governance_policy_agent", "action_type": "policy_check", "target_kind": "internal_sys", "offset_hours": 3.0},

        # Delegation — assigns to humans
        {"actor_kind": "delegation_agent", "action_type": "task_assigned", "target_kind": "internal_user", "offset_hours": 3.5},

        # Human follow-ups (chasing behavior — should cluster across cases)
        {"actor_kind": "human", "action_type": "sent_followup", "target_kind": "external", "offset_hours": 48.0},
        {"actor_kind": "human", "action_type": "sent_followup", "target_kind": "external", "offset_hours": 96.0},

        # Intent Anticipation — predicts next steps
        {"actor_kind": "intent_anticipation_agent", "action_type": "intent_predicted", "target_kind": "task", "offset_hours": 100.0},
    ]

    # Add variability — some cases have extra events, some have fewer
    extra = rng.choice([0, 0, 1, 1, 2])  # bias toward 0-1 extras
    extras_pool = [
        {"actor_kind": "human", "action_type": "sent_followup", "target_kind": "external", "offset_hours": 144.0},
        {"actor_kind": "human", "action_type": "status_check", "target_kind": "internal_sys", "offset_hours": 24.0},
        {"actor_kind": "governance_policy_agent", "action_type": "policy_check", "target_kind": "internal_sys", "offset_hours": 48.0},
        {"actor_kind": "human", "action_type": "requested_document", "target_kind": "external", "offset_hours": 24.0},
    ]
    for _ in range(extra):
        base_workflow.append(rng.choice(extras_pool))

    # Some cases get an approval action (will trigger escalation)
    if rng.random() < 0.15:
        base_workflow.append({"actor_kind": "human", "action_type": "approved", "target_kind": "task", "offset_hours": 168.0})

    # Some cases close cleanly
    if rng.random() < 0.6:
        base_workflow.append({"actor_kind": "human", "action_type": "case_closed", "target_kind": "task", "offset_hours": 200.0})

    return base_workflow


def realize_workflow(case_id: str, domain: dict, case_start: datetime,
                     workflow: list[dict], rng: random.Random) -> list[dict]:
    """Turn a workflow template into concrete events with real values."""
    events = []
    primary_human = rng.choice(domain["humans"])
    primary_external = rng.choice(domain["external_pool"])
    primary_doc = rng.choice(domain["documents"])
    primary_sys = rng.choice(domain["internal_systems"])

    for step in workflow:
        ts = case_start + timedelta(hours=step["offset_hours"] + rng.uniform(-0.5, 0.5))

        # Pick actor
        if step["actor_kind"] == "human":
            actor_id = primary_human
            actor_type = "human"
        else:
            actor_id = step["actor_kind"]
            actor_type = "agent"

        # Pick target
        if step["target_kind"] == "external":
            target_entity = primary_external
            target_entity_type = "external_contact"
            ctx = {"channel": "email", "doc_type": primary_doc}
        elif step["target_kind"] == "internal_sys":
            target_entity = primary_sys
            target_entity_type = "internal_system"
            ctx = {"system": primary_sys}
        elif step["target_kind"] == "internal_user":
            target_entity = rng.choice(domain["humans"])
            target_entity_type = "internal_user"
            ctx = {"assignment_kind": "review"}
        elif step["target_kind"] == "document":
            target_entity = f"{primary_doc}_{case_id[-4:]}"
            target_entity_type = "document"
            ctx = {"doc_type": primary_doc}
        else:  # task
            target_entity = f"task_{case_id[-6:]}"
            target_entity_type = "task"
            ctx = {}

        # Outcomes — most success, some pending
        outcome = rng.choices(["success", "pending", "failed"], weights=[80, 17, 3])[0]

        events.append({
            "event_id": f"evt_{uuid.uuid4().hex[:10]}",
            "case_id": case_id,
            "timestamp": ts.isoformat(),
            "actor_id": actor_id,
            "actor_type": actor_type,
            "action_type": step["action_type"],
            "target_entity": target_entity,
            "target_entity_type": target_entity_type,
            "parent_task_id": f"task_{case_id[-6:]}",
            "context_payload": ctx,
            "outcome": outcome,
        })

    return events


# ──────────────────────────────────────────────────────────────────
# CASE GENERATOR
# ──────────────────────────────────────────────────────────────────

def generate_cases(count: int, start_index: int = 0,
                   base_date: datetime = None, seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Generate `count` synthetic cases starting from start_index."""
    rng = random.Random(seed + start_index)
    if base_date is None:
        base_date = datetime.now(timezone.utc) - timedelta(days=60)

    cases = []
    all_events = []

    for i in range(count):
        domain_key = DOMAIN_KEYS[i % len(DOMAIN_KEYS)]
        domain = DOMAINS[domain_key]

        case_start = base_date + timedelta(
            days=rng.randint(0, 50),
            hours=rng.randint(8, 17),
            minutes=rng.randint(0, 59),
        )

        case_id = f"case_{domain_key[:6]}_{start_index + i + 1:04d}"

        # 70% in_progress, 30% closed
        case_status = rng.choices(["in_progress", "closed"], weights=[70, 30])[0]

        case = {
            "case_id": case_id,
            "case_type": domain["case_type"],
            "status": case_status,
            "created_at": case_start.isoformat(),
            "domain_metadata": {
                "domain": domain_key,
                "primary_human": rng.choice(domain["humans"]),
            },
        }
        if case_status == "closed":
            case["closed_at"] = (case_start + timedelta(days=rng.randint(7, 14))).isoformat()
        cases.append(case)

        # Generate events for this case
        workflow = case_workflow_template(rng)
        events = realize_workflow(case_id, domain, case_start, workflow, rng)
        all_events.extend(events)

    return cases, all_events


# ──────────────────────────────────────────────────────────────────
# MAIN ENTRY POINTS
# ──────────────────────────────────────────────────────────────────

def dump_to_file(cases: list[dict], events: list[dict],
                 path: str = "data/synthetic_events.json") -> None:
    """Save snapshot to disk for inspection."""
    data = {"cases": cases, "events": events}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, default=str))
    print(f"[snapshot] wrote {len(cases)} cases, {len(events)} events to {path}")


def load_into_db(cases: list[dict], events: list[dict]) -> dict:
    """Push everything through the logging_tool (validates + stores)."""
    print(f"\n[ingest] registering {len(cases)} cases...")
    for case in cases:
        ingest_case(case)

    print(f"[ingest] ingesting {len(events)} events via logging_tool...")
    return ingest_batch(events, source_agent="synthetic_data_loader")


def main():
    parser = argparse.ArgumentParser(description="Synthetic case generator")
    parser.add_argument("--count", type=int, default=200, help="Number of cases to generate")
    parser.add_argument("--append", action="store_true", help="Append to existing DB instead of fresh")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--no-db", action="store_true", help="Just write JSON, skip DB load")
    args = parser.parse_args()

    if args.append:
        try:
            existing_count = db.count_cases()
        except Exception as e:
            print(f"[append] could not count existing cases ({e}); starting from 0")
            existing_count = 0
        print(f"\n[append] existing cases in DB: {existing_count}")
        print(f"[append] generating {args.count} new cases (indices {existing_count}–{existing_count + args.count - 1})")
        cases, events = generate_cases(
            args.count,
            start_index=existing_count,
            seed=args.seed,
        )
    else:
        print(f"\n[fresh] generating {args.count} cases across {len(DOMAINS)} domains...")
        cases, events = generate_cases(args.count, seed=args.seed)

    # Domain breakdown
    from collections import Counter
    domain_counts = Counter(c["domain_metadata"]["domain"] for c in cases)
    print("[breakdown]")
    for domain, n in sorted(domain_counts.items()):
        print(f"  {domain}: {n} cases")

    # Save snapshot
    dump_to_file(cases, events)

    # Load into DB
    if not args.no_db:
        try:
            result = load_into_db(cases, events)
            print(f"\n[done] {result['accepted']} events accepted, {result['rejected']} rejected")
        except Exception as e:
            print(f"\n[done] DB load skipped ({e})")
            print("       JSON snapshot is still saved.")


if __name__ == "__main__":
    main()
