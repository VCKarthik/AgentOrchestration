"""
models/task.py
--------------
Pydantic models representing an incoming task payload for the Delegation Agent.
Covers all required fields from the Phase 1 specification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Urgency(str, Enum):
    IMMEDIATE = "immediate"
    URGENT = "urgent"
    MODERATE = "moderate"
    LOW = "low"


class CustomerTier(str, Enum):
    VIP = "vip"
    PREMIUM = "premium"
    STANDARD = "standard"


class FlagSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class TaskType(str, Enum):
    CLAIM_REVIEW = "claim_review"
    CUSTOMER_INQUIRY = "customer_inquiry"
    TECHNICAL_SUPPORT = "technical_support"
    VENDOR_ONBOARDING = "vendor_onboarding"
    COMPLIANCE_REVIEW = "compliance_review"
    FINANCIAL_APPROVAL = "financial_approval"
    FRAUD_INVESTIGATION = "fraud_investigation"
    GENERAL = "general"


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------

class PolicyFlag(BaseModel):
    """Represents a policy-level flag attached to a task."""
    flag_id: str
    label: str
    severity: FlagSeverity = FlagSeverity.NONE
    description: Optional[str] = None


class ComplianceFlag(BaseModel):
    """Represents a compliance/regulatory flag attached to a task."""
    flag_id: str
    label: str
    severity: FlagSeverity = FlagSeverity.NONE
    regulation: Optional[str] = None


class RiskFlag(BaseModel):
    """Represents an operational or financial risk flag."""
    flag_id: str
    label: str
    severity: FlagSeverity = FlagSeverity.NONE
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Core Task Model
# ---------------------------------------------------------------------------

class Task(BaseModel):
    """
    Represents an incoming task routed to the Delegation Agent.

    Required fields are enforced by Pydantic. Optional fields that are absent
    will trigger fallback logic in the engine (e.g. default priority, warnings).
    """

    # --- Identity ---
    task_id: str = Field(..., description="Unique task identifier (alphanumeric)")
    task_type: TaskType = Field(..., description="Categorical type of the task")
    title: str = Field(..., description="Short human-readable task title")
    description: str = Field(..., description="Full description of the work required")

    # --- Scheduling & Effort ---
    priority: Priority = Field(default=Priority.MEDIUM, description="Task urgency tier")
    urgency: Urgency = Field(default=Urgency.MODERATE, description="Time sensitivity")
    estimated_effort: float = Field(
        ..., ge=0.0, description="Estimated hours of effort required"
    )
    due_date: datetime = Field(..., description="Deadline for task completion")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # --- Domain & Skills ---
    business_domain: str = Field(..., description="Business area (e.g. 'claims', 'finance')")
    required_skills: List[str] = Field(
        default_factory=list,
        description="List of skill tags needed to complete this task",
    )

    # --- Source & Ownership ---
    source_system: str = Field(default="unknown", description="Origin system name")
    requester: str = Field(..., description="Person or system that created the task")
    current_assignee: Optional[str] = Field(
        None, description="Existing assignee ID if task is being reassigned"
    )
    recommended_candidates: Optional[List[str]] = Field(
        None,
        description="Optional list of preferred assignee IDs from upstream agents",
    )

    # --- Customer & Financial Context ---
    customer_tier: CustomerTier = Field(default=CustomerTier.STANDARD)
    monetary_value: float = Field(
        default=0.0, ge=0.0, description="Dollar value associated with the task"
    )

    # --- Flags ---
    policy_flags: List[PolicyFlag] = Field(default_factory=list)
    compliance_flags: List[ComplianceFlag] = Field(default_factory=list)
    risk_flags: List[RiskFlag] = Field(default_factory=list)

    # --- Reassignment Tracking ---
    reassignment_count: int = Field(
        default=0, ge=0, description="Number of times task has already been reassigned"
    )

    @field_validator("task_id")
    @classmethod
    def task_id_must_be_alphanumeric(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"task_id must be alphanumeric (got '{v}')")
        return v

    @field_validator("due_date", "created_at", mode="before")
    @classmethod
    def ensure_timezone_aware_datetime(cls, v):
        """
        Ensure datetimes are timezone-aware.
        If a naive datetime is provided, assume UTC.
        """
        if isinstance(v, datetime):
            return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        return v

    # --- Computed helpers ---

    def has_critical_flags(self) -> bool:
        """Returns True if any flag (policy, compliance, risk) is CRITICAL severity."""
        for flag in self.policy_flags + self.compliance_flags + self.risk_flags:
            if flag.severity == FlagSeverity.CRITICAL:
                return True
        return False

    def hours_until_due(self) -> float:
        """Returns the number of hours remaining until the due date."""
        now = datetime.now(timezone.utc)
        delta = self.due_date - now
        return max(delta.total_seconds() / 3600.0, 0.0)

    def is_sla_at_risk(self) -> bool:
        """
        SLA is at risk when remaining time is less than estimated effort.
        Includes a 20% buffer for handoff overhead.
        """
        buffer = self.estimated_effort * 1.2
        return self.hours_until_due() < buffer

    model_config = ConfigDict(use_enum_values=True)