"""
repositories/assignee_repository.py
------------------------------------
In-memory repository for Assignee records.

Production mode: customer's roster is loaded from a JSON file at
`data/assignee_rosters/active_roster.json`. The Streamlit demo's "Team Roster"
panel writes to that path; resetting it deletes the file.

If no override file exists the repository starts EMPTY — DA will then return
escalations because no candidates are available, which is the correct
production-mode behaviour ("you haven't told me about your team yet").
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from ..models.assignee import (
    Assignee,
    AvailabilityStatus,
    Seniority,
    SkillProficiency,
)

logger = logging.getLogger(__name__)


# Resolve the active-roster JSON path relative to the repo root.
# DA/delegation_agent/repositories/assignee_repository.py
#   ../..      → DA/
#   ../../..   → repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ACTIVE_ROSTER_PATH = _REPO_ROOT / "data" / "assignee_rosters" / "active_roster.json"


def _load_assignees_from_json(path: Path) -> List[Assignee]:
    """
    Load assignees from a JSON file. Expected schema:
        { "assignees": [ { Assignee fields ... }, ... ] }

    Invalid records are skipped with a warning rather than crashing the agent.
    """
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[AssigneeRepository] Failed to read %s: %s", path, exc)
        return []

    if not isinstance(payload, dict) or "assignees" not in payload:
        logger.warning(
            "[AssigneeRepository] %s missing top-level 'assignees' key", path
        )
        return []

    out: List[Assignee] = []
    for raw in payload.get("assignees") or []:
        try:
            out.append(Assignee(**raw))
        except Exception as exc:
            logger.warning(
                "[AssigneeRepository] Skipping invalid assignee %r: %s",
                raw.get("assignee_id", "<no-id>"),
                exc,
            )
    return out


def get_active_roster_path() -> Path:
    """Public path accessor — used by the Streamlit demo panel."""
    return _ACTIVE_ROSTER_PATH



# Sample assignee data factory

def _default_assignees() -> List[Assignee]:
    """
    Production-mode default. If an active roster JSON exists, load it.
    Otherwise return an empty list — the customer hasn't uploaded their team
    yet, so DA correctly has no candidates to assign tasks to.
    """
    if _ACTIVE_ROSTER_PATH.exists():
        loaded = _load_assignees_from_json(_ACTIVE_ROSTER_PATH)
        logger.info(
            "[AssigneeRepository] Loaded %d assignees from %s",
            len(loaded),
            _ACTIVE_ROSTER_PATH,
        )
        return loaded
    return []


def _build_sample_assignees() -> List[Assignee]:
    """
    DEPRECATED — preserved for backwards compatibility with unit tests that
    pass `assignees=_build_sample_assignees()` explicitly.

    The default `AssigneeRepository()` constructor no longer calls this.
    For demos/tests that want the full hardcoded sample, upload
    `data/assignee_rosters/sample_roster.json` via the Streamlit panel
    (or copy it to active_roster.json directly).
    """
    return [
        Assignee(
            assignee_id="EMP-001",
            name="Suyash Wagh",
            role="Senior Claims Adjuster",
            seniority=Seniority.SENIOR,
            department="Claims",
            skills=[
                SkillProficiency(skill="claim_review", proficiency=95),
                SkillProficiency(skill="compliance", proficiency=80),
                SkillProficiency(skill="negotiation", proficiency=75),
                SkillProficiency(skill="customer_communication", proficiency=85),
            ],
            business_domains=["claims", "insurance", "customer_service"],
            certifications=["AIC", "CPCU"],
            capacity_limit=10,
            current_workload=6,
            active_tasks_count=6,
            utilization_percent=60.0,
            availability_status=AvailabilityStatus.AVAILABLE,
            escalation_authority=True,
            performance_score=92.0,
            task_history_ids=["TSK-001", "TSK-002", "TSK-003"],
        ),
        Assignee(
            assignee_id="EMP-002",
            name="Virat Kohli",
            role="Compliance Analyst",
            seniority=Seniority.INTERMEDIATE,
            department="Compliance",
            skills=[
                SkillProficiency(skill="compliance", proficiency=90),
                SkillProficiency(skill="regulatory_review", proficiency=85),
                SkillProficiency(skill="risk_assessment", proficiency=78),
                SkillProficiency(skill="documentation", proficiency=70),
            ],
            business_domains=["compliance", "risk", "finance"],
            certifications=["CRCM"],
            capacity_limit=8,
            current_workload=7,
            active_tasks_count=7,
            utilization_percent=87.5,
            availability_status=AvailabilityStatus.BUSY,
            escalation_authority=False,
            performance_score=84.0,
        ),
        Assignee(
            assignee_id="EMP-003",
            name="Ramesh Patel",
            role="Junior Customer Service Rep",
            seniority=Seniority.JUNIOR,
            department="Customer Service",
            skills=[
                SkillProficiency(skill="customer_communication", proficiency=82),
                SkillProficiency(skill="ticket_management", proficiency=70),
                SkillProficiency(skill="data_entry", proficiency=90),
            ],
            business_domains=["customer_service"],
            certifications=[],
            capacity_limit=12,
            current_workload=3,
            active_tasks_count=3,
            utilization_percent=25.0,
            availability_status=AvailabilityStatus.AVAILABLE,
            escalation_authority=False,
            performance_score=76.0,
        ),
        Assignee(
            assignee_id="EMP-004",
            name="David Kim",
            role="Lead Financial Analyst",
            seniority=Seniority.LEAD,
            department="Finance",
            skills=[
                SkillProficiency(skill="financial_review", proficiency=98),
                SkillProficiency(skill="compliance", proficiency=88),
                SkillProficiency(skill="risk_assessment", proficiency=90),
                SkillProficiency(skill="negotiation", proficiency=85),
                SkillProficiency(skill="vendor_management", proficiency=80),
            ],
            business_domains=["finance", "vendor_onboarding", "risk", "compliance"],
            certifications=["CFA", "CPA"],
            capacity_limit=8,
            current_workload=2,
            active_tasks_count=2,
            utilization_percent=25.0,
            availability_status=AvailabilityStatus.AVAILABLE,
            escalation_authority=True,
            performance_score=96.0,
        ),
        Assignee(
            assignee_id="EMP-005",
            name="Rachel Okonkwo",
            role="Procurement Associate",
            seniority=Seniority.INTERMEDIATE,
            department="Procurement",
            skills=[
                SkillProficiency(skill="vendor_management", proficiency=88),
                SkillProficiency(skill="vendor_onboarding", proficiency=85),
                SkillProficiency(skill="documentation", proficiency=80),
                SkillProficiency(skill="negotiation", proficiency=72),
            ],
            business_domains=["vendor_onboarding", "procurement"],
            certifications=["CPSM"],
            capacity_limit=10,
            current_workload=4,
            active_tasks_count=4,
            utilization_percent=40.0,
            availability_status=AvailabilityStatus.AVAILABLE,
            escalation_authority=False,
            performance_score=88.0,
        ),
        Assignee(
            assignee_id="EMP-006",
            name="James Fitzgerald",
            role="Senior Technical Specialist",
            seniority=Seniority.SENIOR,
            department="Technical Support",
            skills=[
                SkillProficiency(skill="technical_support", proficiency=95),
                SkillProficiency(skill="system_administration", proficiency=90),
                SkillProficiency(skill="troubleshooting", proficiency=92),
                SkillProficiency(skill="documentation", proficiency=70),
            ],
            business_domains=["technical_support", "it_operations"],
            certifications=["ITIL", "AWS-SAA"],
            capacity_limit=8,
            current_workload=8,
            active_tasks_count=8,
            utilization_percent=100.0,  # fully saturated — triggers hard rule
            availability_status=AvailabilityStatus.BUSY,
            escalation_authority=False,
            performance_score=90.0,
        ),
        Assignee(
            assignee_id="EMP-007",
            name="Angela Torres",
            role="Expert Risk Analyst",
            seniority=Seniority.EXPERT,
            department="Risk Management",
            skills=[
                SkillProficiency(skill="risk_assessment", proficiency=97),
                SkillProficiency(skill="compliance", proficiency=90),
                SkillProficiency(skill="financial_review", proficiency=85),
                SkillProficiency(skill="regulatory_review", proficiency=88),
                SkillProficiency(skill="claim_review", proficiency=75),
            ],
            business_domains=["risk", "compliance", "finance", "claims", "insurance"],
            certifications=["FRM", "CRCM", "CPCU"],
            capacity_limit=6,
            current_workload=0,
            active_tasks_count=0,
            utilization_percent=0.0,
            availability_status=AvailabilityStatus.AVAILABLE,
            escalation_authority=True,
            performance_score=98.0,
        ),
        Assignee(
            assignee_id="EMP-008",
            name="Tom Bradley",
            role="Operations Coordinator",
            seniority=Seniority.INTERMEDIATE,
            department="Operations",
            skills=[
                SkillProficiency(skill="ticket_management", proficiency=78),
                SkillProficiency(skill="customer_communication", proficiency=75),
                SkillProficiency(skill="data_entry", proficiency=85),
                SkillProficiency(skill="documentation", proficiency=80),
            ],
            business_domains=["operations", "customer_service", "general"],
            certifications=[],
            capacity_limit=15,
            current_workload=9,
            active_tasks_count=9,
            utilization_percent=60.0,
            availability_status=AvailabilityStatus.AVAILABLE,
            escalation_authority=False,
            performance_score=80.0,
        ),
        # Out-of-office assignee — should be filtered out
        Assignee(
            assignee_id="EMP-009",
            name="Patricia Walsh",
            role="Senior Compliance Officer",
            seniority=Seniority.SENIOR,
            department="Compliance",
            skills=[
                SkillProficiency(skill="compliance", proficiency=95),
                SkillProficiency(skill="regulatory_review", proficiency=92),
            ],
            business_domains=["compliance", "risk"],
            certifications=["CRCM", "CCEP"],
            capacity_limit=8,
            current_workload=0,
            active_tasks_count=0,
            utilization_percent=0.0,
            availability_status=AvailabilityStatus.OUT_OF_OFFICE,  # will be filtered
            escalation_authority=True,
            performance_score=94.0,
        ),
    ]


# ---------------------------------------------------------------------------
# Repository class
# ---------------------------------------------------------------------------

class AssigneeRepository:
    """
    In-memory store for Assignee records.

    Supports lookup by ID, domain, skills, and retrieval of the full pool.
    Replace with SQLAlchemy / DynamoDB / REST client for production use.
    """

    def __init__(self, assignees: Optional[List[Assignee]] = None) -> None:
        self._store: Dict[str, Assignee] = {}
        # Default = read from active_roster.json (production mode).
        # Tests can still pass an explicit list via the `assignees` kwarg.
        initial = assignees if assignees is not None else _default_assignees()
        for assignee in initial:
            self._store[assignee.assignee_id] = assignee

    # --- CRUD ---

    def add(self, assignee: Assignee) -> None:
        """Persist or overwrite an assignee record."""
        self._store[assignee.assignee_id] = assignee

    def get_by_id(self, assignee_id: str) -> Optional[Assignee]:
        """Retrieve an assignee by their unique ID; returns None if not found."""
        return self._store.get(assignee_id)

    def get_all(self) -> List[Assignee]:
        """Return all assignees in the repository."""
        return list(self._store.values())

    def remove(self, assignee_id: str) -> bool:
        """Remove an assignee; returns True if it existed."""
        if assignee_id in self._store:
            del self._store[assignee_id]
            return True
        return False

    # --- Filtered queries ---

    def get_by_domain(self, domain: str) -> List[Assignee]:
        """Return assignees that cover the specified business domain."""
        return [a for a in self._store.values() if a.covers_domain(domain)]

    def get_available(self) -> List[Assignee]:
        """Return all assignees currently marked as available."""
        return [
            a for a in self._store.values()
            if a.availability_status == AvailabilityStatus.AVAILABLE
        ]

    def get_with_skill(self, skill: str) -> List[Assignee]:
        """Return assignees who possess the given skill (case-insensitive)."""
        skill_lower = skill.lower()
        return [
            a for a in self._store.values()
            if skill_lower in a.skill_names()
        ]

    def count(self) -> int:
        """Return total number of assignees in the repository."""
        return len(self._store)
