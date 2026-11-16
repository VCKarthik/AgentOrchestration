"""
iaa_demo.py
Run this to see the IAA (and full orchestrator pipeline) in action.

Usage:
    python iaa_demo.py                        # default IAA-only demo
    python iaa_demo.py --workflow             # full orchestrator pipeline (all 4 agents)
    python iaa_demo.py --case SYNTH-DOC-0001  # run specific case by entity_id
    python iaa_demo.py --risk high            # pick a high-risk case (shows override)
    python iaa_demo.py --list                 # print all available case IDs
"""

import json, sys, argparse, os
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from agent.schemas import EventLogEntry, ProcessState
from agent.iaa import run_iaa, build_process_state
from agent.chain import apply_overrides


# ── Case helpers ──────────────────────────────────────────────────────────────

def load_case(cases: list, entity_id: str = None, risk: str = None) -> dict:
    if entity_id:
        match = [c for c in cases if c["entity_id"] == entity_id]
        if not match:
            print(f"Case {entity_id} not found.")
            sys.exit(1)
        return match[0]
    if risk:
        match = [c for c in cases if c["risk_severity"] == risk and len(c["prior_actions"]) >= 2]
        if not match:
            print(f"No case with risk_severity={risk}")
            sys.exit(1)
        return match[0]
    # Default: interesting mid-workflow claim case
    for c in cases:
        if (c["risk_severity"] == "medium"
                and len(c["prior_actions"]) >= 2
                and "documentation" in c["event_type"]):
            return c
    return cases[0]


def build_events_from_case(case: dict) -> list[EventLogEntry]:
    ts = datetime.now(timezone.utc)
    actor_seq = {
        step["event_type"]: step["actor"]
        for step in case.get("actor_sequence", [])
    }
    events = [
        EventLogEntry(
            event_id=f"{case['entity_id']}-{j}",
            entity_id=case["entity_id"],
            event_type=evt,
            stage=evt,
            timestamp=ts,
            actor=actor_seq.get(evt),
            metadata={},
        )
        for j, evt in enumerate(case["prior_actions"])
    ]
    events.append(EventLogEntry(
        event_id=f"{case['entity_id']}-current",
        entity_id=case["entity_id"],
        event_type=case["event_type"],
        stage=case["stage"],
        timestamp=ts,
        actor=actor_seq.get(case["event_type"]),
        metadata=case.get("metadata", {}),
    ))
    return events


def build_state_from_case(case: dict) -> ProcessState:
    events = build_events_from_case(case)
    return build_process_state(
        events,
        risk_flags=case.get("risk_flags", []),
        risk_severity=case.get("risk_severity"),
    )


# ── Accuracy helper ───────────────────────────────────────────────────────────

def _keyword_match(predicted: str, ground_truth: str) -> bool:
    """
    Loose match between predicted action_id and ground-truth next_action.
    Normalizes case, separators, and strips common English suffixes from each
    token before comparing. Handles cases like
       "escalate_for_approval" vs "escalated_for_approval"
    by reducing both to "escalat for approv".
    """
    SUFFIXES = ("ing", "ion", "ed", "al", "es", "s", "e")  # longest first

    def stem_token(tok: str) -> str:
        for suf in SUFFIXES:
            if tok.endswith(suf) and len(tok) > len(suf) + 2:
                return tok[: -len(suf)]
        return tok

    def normalize(s: str) -> str:
        s = (s or "").lower().replace("_", " ").replace("-", " ")
        return " ".join(stem_token(t) for t in s.split() if t)

    p = normalize(predicted)
    g = normalize(ground_truth)
    if not p or not g:
        return False
    return p == g or p in g or g in p


# ── Display helpers ───────────────────────────────────────────────────────────

def divider(label=""):
    w = 62
    if label:
        pad = max(0, (w - len(label) - 2) // 2)
        print("─" * pad + f" {label} " + "─" * pad)
    else:
        print("─" * w)


# ── IAA-only demo ─────────────────────────────────────────────────────────────

def run_iaa_demo(case: dict):
    divider("INPUT CASE")
    print(f"  Entity ID    : {case['entity_id']}")
    print(f"  Process      : {case['process_type']}")
    print(f"  Current event: {case['event_type']}")
    print(f"  Prior actions: {' → '.join(case['prior_actions'])}")
    print(f"  Risk severity: {case['risk_severity']}")
    print(f"  Risk flags   : {', '.join(case.get('risk_flags', [])) or 'none'}")
    print(f"  Ground truth : {case['next_action']}  (what actually happened next)")

    divider("RUNNING IAA")
    state = build_state_from_case(case)
    print(f"  Operating context: {state.operating_context}")
    print(f"  Prior steps      : {len(state.prior_steps)}")
    print("  Calling LLM chain...")

    try:
        rec = run_iaa(state)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        print("\n  Check your GOOGLE_API_KEY in .env and that corpus is bootstrapped.")
        print("  Run: python -m agent.ingest --bootstrap")
        sys.exit(1)

    divider("IAA OUTPUT")
    print(f"\n  Recommended action : {rec.recommended_action.action_id}")
    print(f"  Label              : {rec.recommended_action.label}")
    print(f"  Confidence         : {rec.recommended_action.confidence:.0%}")
    print(f"  Escalate to human  : {rec.escalate_to_human}")
    print(f"  Override applied   : {rec.override_applied}")
    if rec.override_reason:
        print(f"  Override reason    : {rec.override_reason}")
    print(f"\n  Reasoning:\n  {rec.recommended_action.reasoning}")

    divider("ALL PREDICTED ACTIONS")
    for i, a in enumerate(rec.predicted_actions, 1):
        bar_len = int(a.confidence * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {i}. [{bar}] {a.confidence:.0%}  {a.action_id}")
        print(f"     {a.reasoning[:90]}")

    if rec.task_list:
        divider("TASK LIST")
        for t in rec.task_list:
            print(f"  [{t.priority.upper():6}] {t.task_id} — {t.action}")
            print(f"           Role: {t.assigned_role or 'unassigned'}")
            if t.depends_on:
                print(f"           Depends on: {', '.join(t.depends_on)}")

    if rec.workflow_timeline:
        divider("WORKFLOW TIMELINE")
        status_icon = {"completed": "✓", "current": "►", "predicted": "○"}
        for w in rec.workflow_timeline:
            icon = status_icon.get(w.status, "?")
            actor_str = f" ({w.actor})" if w.actor else ""
            print(f"  Step {w.step:2d}  {icon}  {w.event_type}{actor_str}  [{w.status}]")

    divider("ACCURACY CHECK")
    top1 = rec.recommended_action.action_id
    gt   = case["next_action"]
    hit  = _keyword_match(top1, gt)
    print(f"  Ground truth : {gt}")
    print(f"  Predicted    : {top1}")
    print(f"  Match        : {'✓  HIT' if hit else '✗  MISS'}")

    divider()
    print(f"  Retrieved {len(rec.retrieved_context_ids)} context chunks from corpus")
    print(f"  Model: {rec.model_used}")
    print()


# ── Full workflow demo ────────────────────────────────────────────────────────

def run_workflow_demo(case: dict):
    from orchestrator.orchestrator import run_workflow

    divider("WORKFLOW DEMO — Project AMP")
    print(f"  Entity ID    : {case['entity_id']}")
    print(f"  Process      : {case['process_type']}")
    print(f"  Current event: {case['event_type']}")
    print(f"  Prior actions: {' → '.join(case['prior_actions'])}")
    print(f"  Risk severity: {case['risk_severity']}")
    print(f"  Ground truth : {case['next_action']}")
    print()
    print("  Running 4-agent pipeline: CSA → RRA → IAA → Delegation ...")

    events = build_events_from_case(case)

    try:
        result = run_workflow(events, case["entity_id"])
    except Exception as e:
        print(f"\n  ERROR: {e}")
        print("\n  Check your GOOGLE_API_KEY in .env and that corpus is bootstrapped.")
        sys.exit(1)

    # ── CSA output ────────────────────────────────────────────────────────────
    divider("AGENT 1 — Context Stitching Agent (CSA) [MOCK]")
    csa = result.get("csa_output") or {}
    print(f"  Context summary : {csa.get('context_summary', 'N/A')}")
    missing = csa.get("missing_inputs", [])
    print(f"  Missing inputs  : {missing or 'none'}")

    # ── RRA output ────────────────────────────────────────────────────────────
    divider("AGENT 2 — Risk Radar Agent (RRA) [MOCK]")
    rra = result.get("rra_output") or {}
    print(f"  Severity : {rra.get('severity', 'N/A')}")
    print(f"  Flags    : {rra.get('flags', []) or 'none'}")

    # ── IAA output ────────────────────────────────────────────────────────────
    divider("AGENT 3 — Intent Anticipation Agent (IAA) [REAL]")
    rec = result.get("iaa_recommendation")
    if rec:
        print(f"  Recommended    : {rec.recommended_action.action_id}")
        print(f"  Label          : {rec.recommended_action.label}")
        print(f"  Confidence     : {rec.recommended_action.confidence:.0%}")
        print(f"  Escalate       : {rec.escalate_to_human}")
        print(f"  Override       : {rec.override_applied}")

        if rec.task_list:
            print(f"\n  Task list ({len(rec.task_list)} tasks):")
            for t in rec.task_list:
                print(f"    [{t.priority.upper():6}] {t.task_id} — {t.action}  (role: {t.assigned_role or 'TBD'})")

        if rec.workflow_timeline:
            print(f"\n  Workflow timeline ({len(rec.workflow_timeline)} steps):")
            icons = {"completed": "✓", "current": "►", "predicted": "○"}
            for w in rec.workflow_timeline:
                icon = icons.get(w.status, "?")
                actor_str = f" [{w.actor}]" if w.actor else ""
                print(f"    {w.step:2d}. {icon} {w.event_type}{actor_str}  [{w.status}]")
    else:
        print("  No IAA recommendation returned.")

    # ── Delegation output ─────────────────────────────────────────────────────
    divider("AGENT 4 — Delegation Agent [MOCK]")
    if result.get("iaa_escalate"):
        print("  [SKIPPED — escalated to human review]")
    else:
        deleg = result.get("delegation_output") or {}
        assigned = deleg.get("assigned_tasks", [])
        if assigned:
            for t in assigned:
                print(f"  {t['task_id']}  →  {t['assigned_to']}  ({t['priority']} priority)")
        else:
            print("  No tasks assigned.")

    # ── Summary ───────────────────────────────────────────────────────────────
    divider("PIPELINE SUMMARY")
    print(f"  Workflow complete  : {result.get('workflow_complete', False)}")
    print(f"  Escalated to human : {result.get('iaa_escalate', False)}")
    if result.get("error"):
        print(f"  Error              : {result['error']}")
    top1 = rec.recommended_action.action_id if rec else "N/A"
    gt   = case["next_action"]
    hit  = _keyword_match(top1, gt)
    print(f"  Ground truth       : {gt}")
    print(f"  IAA predicted      : {top1}")
    print(f"  Match              : {'✓  HIT' if hit else '✗  MISS'}")
    divider()
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IAA / Orchestrator demo")
    parser.add_argument("--workflow", action="store_true",
                        help="Run full 4-agent orchestrator pipeline instead of IAA-only")
    parser.add_argument("--case",  help="entity_id to run")
    parser.add_argument("--risk",  choices=["low", "medium", "high", "critical"],
                        help="Pick a case by risk severity")
    parser.add_argument("--list",  action="store_true", help="List all case IDs and exit")
    args = parser.parse_args()

    cases_path = Path("data/synthetic_cases.json")
    if not cases_path.exists():
        print("No synthetic data. Run: python scripts/generate_synthetic.py")
        sys.exit(1)

    cases = json.load(open(cases_path))

    if args.list:
        for c in cases:
            print(f"{c['entity_id']:35} {c['process_type']:25} risk={c['risk_severity']}")
        sys.exit(0)

    case = load_case(cases, args.case, args.risk)

    if args.workflow:
        run_workflow_demo(case)
    else:
        run_iaa_demo(case)
