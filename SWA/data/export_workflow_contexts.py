"""
Export the seeded demo workflows as JSON context files. The Streamlit demo's
"Load workflow context" uploader consumes these directly.

Output shape (one file per workflow):
    {
      "metadata": { "domain": "vendor_onboarding", "description": "..." },
      "cases":    [ IncomingCase, ... ],
      "events":   [ IncomingEvent, ... ]
    }

Run:
    python3 SWA/data/export_workflow_contexts.py     # from repo root
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SWA_ROOT  = REPO_ROOT / "SWA"
if str(SWA_ROOT) not in sys.path:
    sys.path.insert(0, str(SWA_ROOT))

from db import db  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "data" / "workflow_contexts"

WORKFLOWS = [
    {
        "case_type":   "vendor_onboarding",
        "case_prefix": "seed_vnd_",
        "filename":    "vendor_onboarding_context.json",
        "description": "30 prior vendor onboardings with realistic missing-cert + repeated follow-up patterns. Use as SWA backdrop for vendor demos.",
    },
    {
        "case_type":   "claim_review",
        "case_prefix": "seed_clm_",
        "filename":    "claim_review_context.json",
        "description": "30 prior claim reviews showing the manual sent_followup pattern across cases. Use as SWA backdrop for claim review demos.",
    },
    {
        "case_type":   "interview_scheduling",
        "case_prefix": "seed_int_",
        "filename":    "interview_scheduling_context.json",
        "description": "30 prior interview schedulings with repeated reminder patterns. Use as SWA backdrop for interview scheduling demos.",
    },
]


def _fetch_cases(case_prefix: str) -> list[dict]:
    """Fetch all cases whose case_id begins with the given prefix."""
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT case_id, case_type, status, created_at, closed_at, domain_metadata "
            "FROM cases WHERE case_id LIKE ? ORDER BY case_id",
            (f"{case_prefix}%",),
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        d["domain_metadata"] = json.loads(d.get("domain_metadata") or "{}")
        out.append(d)
    return out


def _fetch_events(case_prefix: str) -> list[dict]:
    """Fetch every activity_log event whose case_id matches the prefix."""
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT event_id, case_id, timestamp, actor_id, actor_type, "
            "       action_type, target_entity, target_entity_type, parent_task_id, "
            "       context_payload, outcome "
            "FROM activity_log WHERE case_id LIKE ? ORDER BY timestamp",
            (f"{case_prefix}%",),
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        d["context_payload"] = json.loads(d.get("context_payload") or "{}")
        out.append(d)
    return out


def export() -> dict[str, dict[str, int]]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict[str, int]] = {}
    for wf in WORKFLOWS:
        cases = _fetch_cases(wf["case_prefix"])
        events = _fetch_events(wf["case_prefix"])
        payload = {
            "metadata": {
                "domain":      wf["case_type"],
                "description": wf["description"],
                "version":     "1.0",
            },
            "cases":  cases,
            "events": events,
        }
        out_path = OUTPUT_DIR / wf["filename"]
        out_path.write_text(json.dumps(payload, indent=2, default=str))
        summary[wf["case_type"]] = {
            "cases":  len(cases),
            "events": len(events),
            "path":   str(out_path.relative_to(REPO_ROOT)),
        }
    return summary


if __name__ == "__main__":
    print(f"Exporting workflow contexts to {OUTPUT_DIR.relative_to(REPO_ROOT)}/")
    summary = export()
    print()
    print(f"{'Workflow':<25}  {'Cases':>6}  {'Events':>7}  {'Path'}")
    print("-" * 95)
    for ct, stats in summary.items():
        print(f"{ct:<25}  {stats['cases']:>6}  {stats['events']:>7}  {stats['path']}")
    print()
    if all(s["cases"] == 0 for s in summary.values()):
        print("WARNING: no cases found. Run `python3 SWA/data/seed_demo_workflows.py` first.")
