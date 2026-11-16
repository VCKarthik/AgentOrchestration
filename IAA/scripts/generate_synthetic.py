"""
generate_synthetic.py
Generates synthetic process trace cases for bootstrapping the IAA corpus.

Uses process templates — each template defines a typical workflow sequence
for a domain. Templates are generic and can be extended by the client.

Each case now includes actor_sequence: a list of {"event_type": str, "actor": str}
for every step, using realistic role labels assigned deterministically by event type.

Run: python scripts/generate_synthetic.py --output data/synthetic_cases.json
"""

from __future__ import annotations
import json, random, argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Actor assignment ──────────────────────────────────────────────────────────
# Deterministic based on event type keywords — no randomness in role assignment

ACTOR_KEYWORD_MAP = [
    (["escalat", "senior", "manager"],            "senior_manager"),
    (["compliance", "policy", "violation"],        "compliance_officer"),
    (["document", "review", "revision", "resubm"],"document_reviewer"),
    (["verify", "verification", "check"],          "claims_analyst"),
    (["approv", "grant", "deny"],                  "senior_manager"),
    (["procure", "purchase", "order"],             "procurement_officer"),
    (["account", "creat", "onboard", "initiat"],   "claims_analyst"),
    (["risk", "assess", "flag"],                   "compliance_officer"),
    (["claim", "submit", "receiv"],                "claims_analyst"),
    (["info", "additional", "request"],            "document_reviewer"),
]

def _assign_actor(event_type: str) -> str:
    """Assign a role label based on event type keywords."""
    et = event_type.lower()
    for keywords, role in ACTOR_KEYWORD_MAP:
        if any(kw in et for kw in keywords):
            return role
    return "claims_analyst"  # default


# ── Process templates ─────────────────────────────────────────────────────────

TEMPLATES = [
    {
        "process_type": "document_review",
        "domain": "operations",
        "sequences": [
            ["document_submitted", "document_received", "review_started", "document_approved"],
            ["document_submitted", "document_received", "review_started", "revision_requested", "document_resubmitted", "document_approved"],
            ["document_submitted", "document_received", "review_started", "document_rejected"],
            ["document_submitted", "document_received", "escalation_triggered", "manager_review", "document_approved"],
        ],
        "risk_scenarios": [
            {"severity": "low",    "flags": []},
            {"severity": "medium", "flags": ["deadline_approaching"]},
            {"severity": "high",   "flags": ["missing_required_attachment", "policy_violation_detected"]},
        ],
    },
    {
        "process_type": "approval_workflow",
        "domain": "operations",
        "sequences": [
            ["request_submitted", "initial_review", "approval_granted"],
            ["request_submitted", "initial_review", "additional_info_requested", "info_provided", "approval_granted"],
            ["request_submitted", "initial_review", "escalated_to_senior", "senior_review", "approval_granted"],
            ["request_submitted", "initial_review", "approval_denied"],
        ],
        "risk_scenarios": [
            {"severity": "low",      "flags": []},
            {"severity": "medium",   "flags": ["value_threshold_approached"]},
            {"severity": "critical", "flags": ["compliance_rule_triggered", "missing_authorization"]},
        ],
    },
    {
        "process_type": "onboarding_workflow",
        "domain": "operations",
        "sequences": [
            ["onboarding_initiated", "documents_collected", "verification_started", "verification_complete", "account_created"],
            ["onboarding_initiated", "documents_collected", "verification_started", "documents_incomplete", "documents_resubmitted", "verification_complete", "account_created"],
            ["onboarding_initiated", "documents_collected", "risk_assessment_triggered", "high_risk_flagged", "manual_review_required"],
        ],
        "risk_scenarios": [
            {"severity": "low",    "flags": []},
            {"severity": "medium", "flags": ["incomplete_documentation"]},
            {"severity": "high",   "flags": ["high_risk_category", "missing_compliance_certificate"]},
        ],
    },
    {
        "process_type": "claim_processing",
        "domain": "operations",
        "sequences": [
            ["claim_submitted", "claim_received", "review_assigned", "documentation_verified", "claim_approved"],
            ["claim_submitted", "claim_received", "review_assigned", "additional_info_requested", "info_received", "claim_approved"],
            ["claim_submitted", "claim_received", "review_assigned", "documentation_verified", "escalated_for_approval", "claim_approved"],
            ["claim_submitted", "claim_received", "review_assigned", "documentation_incomplete", "claim_held"],
        ],
        "risk_scenarios": [
            {"severity": "low",    "flags": []},
            {"severity": "medium", "flags": ["sla_approaching", "documentation_gap"]},
            {"severity": "high",   "flags": ["high_value_threshold_exceeded", "missing_supporting_document"]},
        ],
    },
]


def _generate_case(
    template: dict,
    case_idx: int,
    cutoff_pct: float = None,
) -> dict:
    """Generate one synthetic case from a template, cut at a random point."""
    sequence = random.choice(template["sequences"])
    risk     = random.choice(template["risk_scenarios"])

    if cutoff_pct is None:
        cut = random.randint(1, max(1, len(sequence) - 1))
    else:
        cut = max(1, int(len(sequence) * cutoff_pct))

    prior_events = sequence[:cut]
    next_event   = sequence[cut] if cut < len(sequence) else "process_complete"

    base_time = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 30))

    # Build actor_sequence for every step in the full sequence
    actor_sequence = [
        {"event_type": evt, "actor": _assign_actor(evt)}
        for evt in sequence
    ]

    return {
        "entity_id":      f"SYNTH-{template['process_type'].upper()[:3]}-{case_idx:04d}",
        "process_type":   template["process_type"],
        "domain":         template["domain"],
        "event_type":     prior_events[-1],
        "stage":          prior_events[-1],
        "prior_actions":  prior_events[:-1],
        "next_action":    next_event,
        "timestamp":      base_time.isoformat(),
        "risk_severity":  risk["severity"],
        "risk_flags":     risk["flags"],
        "actor_sequence": actor_sequence,
        "metadata": {
            "source":          "synthetic",
            "full_sequence":   sequence,
            "cut_position":    cut,
            "sequence_length": len(sequence),
        }
    }


def generate(n_per_template: int = 50, output_path: str = "data/synthetic_cases.json") -> list[dict]:
    """
    Generate n_per_template cases per template.
    Returns list of cases and writes to output_path.
    """
    all_cases = []
    idx = 0

    for template in TEMPLATES:
        for _ in range(n_per_template):
            case = _generate_case(template, idx)
            all_cases.append(case)
            idx += 1

    random.shuffle(all_cases)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_cases, f, indent=2)

    print(f"[synthetic] Generated {len(all_cases)} cases across {len(TEMPLATES)} process types")
    print(f"[synthetic] Saved to {output_path}")
    return all_cases


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n",      type=int, default=50, help="Cases per template (default 50)")
    parser.add_argument("--output", default="data/synthetic_cases.json")
    args = parser.parse_args()
    generate(args.n, args.output)
