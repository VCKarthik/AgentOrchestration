"""
main.py
-------
Demonstration script for the Delegation Agent.

Purpose:
- Runs a small demo workload
- Shows channel-first delegation decisions
- Reduces noisy third-party logs for cleaner demo output
- Prevents duplicate log handlers
- Saves structured YAML outputs for each decision
- Prints full traceback for debugging when needed
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timedelta, timezone

from .agent import DelegationAgent
from .services.exporter import DecisionExporter


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

root_logger = logging.getLogger()
if root_logger.hasHandlers():
    root_logger.handlers.clear()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("google.genai").setLevel(logging.WARNING)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


# ---------------------------------------------------------------------------
# Demo tasks
# ---------------------------------------------------------------------------

TASK_1 = {
    "task_id": "TSK-2026-001",
    "task_type": "claim_review",
    "title": "Auto Claim Review",
    "description": (
        "Review insurance claim and approve or deny based on evidence "
        "and supporting customer documentation."
    ),
    "priority": "high",
    "business_domain": "claims",
    "required_skills": ["claim_review", "customer_communication"],
    "estimated_effort": 3.5,
    "due_date": _future(24),
    "requester": "customer-portal-bot",
}

TASK_2 = {
    "task_id": "TSK-2026-002",
    "task_type": "financial_approval",
    "title": "High Value Approval",
    "description": (
        "Approve vendor contract worth $350k after compliance and procurement "
        "checks are completed."
    ),
    "priority": "critical",
    "business_domain": "finance",
    "required_skills": ["financial_review", "compliance"],
    "estimated_effort": 6.0,
    "due_date": _future(48),
    "requester": "procurement-lead",
    "monetary_value": 350000,
}

TASK_3 = {
    "task_id": "TSK-2026-003",
    "task_type": "customer_inquiry",
    "title": "Account Reset Issue",
    "description": (
        "User cannot access account after password reset failure and needs "
        "guided recovery steps."
    ),
    "priority": "medium",
    "business_domain": "customer_service",
    "required_skills": ["customer_communication"],
    "estimated_effort": 1.0,
    "due_date": _future(8),
    "requester": "support-queue",
}

TASK_4 = {
    "task_id": "TSK-2026-004",
    "task_type": "compliance_review",
    "title": "Regulatory Filing",
    "description": (
        "Urgent compliance filing due within the regulatory deadline and "
        "requiring compliance expertise."
    ),
    "priority": "critical",
    "business_domain": "compliance",
    "required_skills": ["compliance", "regulatory_review"],
    "estimated_effort": 5.0,
    "due_date": _future(2),
    "requester": "compliance-officer",
}

TASK_5 = {
    "task_id": "TSK-2026-005",
    "task_type": "general",
    "title": "High-Risk Case Review",
    "description": (
        "Investigate a flagged high-risk issue with policy and regulatory "
        "implications for a premium customer."
    ),
    "priority": "critical",
    "business_domain": "risk",
    "required_skills": ["risk_assessment", "compliance"],
    "estimated_effort": 4.0,
    "due_date": _future(6),
    "requester": "risk-monitor",
    "monetary_value": 50000,
}


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_decision_details(decision) -> None:
    print(decision.to_summary())

    if decision.selected_owner:
        print("  Owner Payload    :", decision.selected_owner)

    if decision.selected_assignee:
        print("  Human Assignee   :", decision.selected_assignee)

    print()


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

def run_demo() -> None:
    print("=" * 78)
    print("  DELEGATION AGENT — CHANNEL-FIRST ROUTING DEMO")
    print("=" * 78)
    print()

    agent = DelegationAgent(
        notify_dry_run=True,
        triggered_by="demo-orchestrator",
        enable_trace_logging=False,
        enable_llm_reasoning=True,
    )

    exporter = DecisionExporter(output_dir="outputs")

    print(f"Assignee pool size: {agent.get_assignee_pool_size()} team members")
    print()

    tasks = [TASK_1, TASK_2, TASK_3, TASK_4, TASK_5]
    labels = [
        "Task 1 — Claim Review (Human Owner)",
        "Task 2 — Financial Approval (Supervisor Review)",
        "Task 3 — Customer Support (Automation)",
        "Task 4 — Compliance Filing (Specialized Agent / Review)",
        "Task 5 — High-Risk Case (Specialized Agent / Supervisor Path)",
    ]

    for label, payload in zip(labels, tasks):
        print("─" * 78)
        print(label)
        print("─" * 78)

        try:
            decision = agent.evaluate_task(payload)
            print_decision_details(decision)

            output_path = exporter.export_yaml(
                decision=decision,
                filename=f"{payload['task_id']}.yaml",
            )
            print(f"  YAML Output      : {output_path}")
            print()

        except Exception:
            print("\n❌ FULL ERROR TRACEBACK")
            traceback.print_exc()
            print()

    print("─" * 78)
    print("AUDIT SUMMARY")
    print("─" * 78)

    try:
        print(agent.audit_summary())
    except Exception:
        traceback.print_exc()

    print()


if __name__ == "__main__":
    run_demo()