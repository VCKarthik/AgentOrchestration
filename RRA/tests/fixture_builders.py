"""
Test fixture builders.

Fixtures use datetimes relative to "now" so tests are stable whether
they run today or three months from now. Static JSON fixtures exist
in fixtures/ for documentation and manual CLI runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from risk_radar.schema import CaseInput


def _now() -> datetime:
    return datetime.now(timezone.utc)


def clean_case() -> CaseInput:
    """Everything present, SLA comfortably in the future, no history."""
    now = _now()
    return CaseInput(
        task_id="T1001",
        workflow_type="vendor_onboarding",
        workflow_state="compliance_review",
        priority="P2",
        created_at=now - timedelta(days=2),
        last_updated=now - timedelta(hours=4),
        due_date=now + timedelta(days=8),
        sla_deadline=now + timedelta(days=7),
        required_inputs=["tax_form", "compliance_certificate", "bank_details"],
        received_inputs=["tax_form", "compliance_certificate", "bank_details"],
        mandatory_inputs=["tax_form", "compliance_certificate"],
        dependency_status="clear",
        blocker_flag=False,
        stakeholder_priority="standard",
        policy_flag=False,
        prior_delay_count=0,
        prior_escalation_count=0,
    )


def hold_case() -> CaseInput:
    """Non-mandatory missing + SLA inside medium window (~20h out)."""
    now = _now()
    return CaseInput(
        task_id="T1002",
        workflow_type="vendor_onboarding",
        workflow_state="compliance_review",
        priority="P1",
        created_at=now - timedelta(days=2),
        last_updated=now - timedelta(hours=4),
        due_date=now + timedelta(hours=24),
        sla_deadline=now + timedelta(hours=20),  # within medium_hours (24h)
        required_inputs=["tax_form", "compliance_certificate", "bank_details", "insurance_cert"],
        received_inputs=["tax_form", "compliance_certificate", "bank_details"],
        mandatory_inputs=["tax_form", "compliance_certificate"],
        dependency_status="clear",
        blocker_flag=False,
        stakeholder_priority="director",
        policy_flag=False,
        prior_delay_count=1,
        prior_escalation_count=0,
    )


def escalate_case() -> CaseInput:
    """Mandatory compliance doc missing + policy_flag + SLA breached."""
    now = _now()
    return CaseInput(
        task_id="T1003",
        workflow_type="vendor_onboarding",
        workflow_state="compliance_review",
        priority="P1",
        created_at=now - timedelta(days=7),
        last_updated=now - timedelta(hours=4),
        due_date=now - timedelta(hours=1),
        sla_deadline=now - timedelta(hours=2),  # breached
        required_inputs=["tax_form", "compliance_certificate", "bank_details"],
        received_inputs=["tax_form", "bank_details"],
        mandatory_inputs=["tax_form", "compliance_certificate"],
        dependency_status="pending",
        blocker_flag=False,
        stakeholder_priority="executive",
        policy_flag=True,
        prior_delay_count=3,
        prior_escalation_count=1,
    )


def partial_context_case() -> CaseInput:
    """Minimal fields — tests operating_context=partial path."""
    return CaseInput(
        task_id="T9999",
        workflow_type="unknown",
        workflow_state="intake",
    )
