"""
models/assignee.py
------------------
Pydantic model for a team member / resource who may be assigned a task.
Covers all resource fields from the Phase 1 specification.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    OUT_OF_OFFICE = "out_of_office"
    ON_LEAVE = "on_leave"


class Seniority(str, Enum):
    JUNIOR = "junior"
    INTERMEDIATE = "intermediate"
    SENIOR = "senior"
    EXPERT = "expert"
    LEAD = "lead"


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------

class SkillProficiency(BaseModel):
    """A skill tag paired with a proficiency score (0–100)."""
    skill: str
    proficiency: int = Field(..., ge=0, le=100, description="Proficiency level 0-100")


# ---------------------------------------------------------------------------
# Core Assignee Model
# ---------------------------------------------------------------------------

class Assignee(BaseModel):
    """
    Represents a team member available for task assignment.

    Seniority, skills, domain coverage, and real-time workload data are
    all considered by the scoring engine.
    """

    # --- Identity ---
    assignee_id: str = Field(..., description="Unique employee/resource ID")
    name: str
    role: str = Field(..., description="Job title / functional role")

    # --- Skills & Domain ---
    skills: List[SkillProficiency] = Field(
        default_factory=list,
        description="Skills with proficiency levels (0-100)",
    )
    business_domains: List[str] = Field(
        default_factory=list,
        description="Business domains this assignee covers (e.g. 'claims', 'finance')",
    )
    certifications: List[str] = Field(
        default_factory=list,
        description="Professional certifications or regulatory authorizations",
    )

    # --- Experience ---
    seniority: Seniority = Field(default=Seniority.INTERMEDIATE)
    performance_score: float = Field(
        default=75.0,
        ge=0.0,
        le=100.0,
        description="Historical performance score (0-100); feeds scoring engine",
    )

    # --- Workload & Capacity ---
    capacity_limit: int = Field(
        ..., ge=1, description="Maximum concurrent tasks this assignee can handle"
    )
    current_workload: int = Field(
        ..., ge=0, description="Number of active tasks currently assigned"
    )
    active_tasks_count: int = Field(
        ..., ge=0, description="Alias/mirror of current_workload for compatibility"
    )
    utilization_percent: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Current capacity utilization percentage (0-100)",
    )
    availability_status: AvailabilityStatus = Field(default=AvailabilityStatus.AVAILABLE)

    # --- Authority ---
    escalation_authority: bool = Field(
        default=False,
        description="Whether this assignee has authority to make escalation decisions",
    )

    # --- Optional Metadata ---
    department: Optional[str] = None
    geographic_region: Optional[str] = None
    time_zone: Optional[str] = None
    task_history_ids: List[str] = Field(
        default_factory=list,
        description="IDs of previous tasks this assignee has worked on",
    )

    @field_validator("utilization_percent", mode="before")
    @classmethod
    def clamp_utilization(cls, v: float) -> float:
        return max(0.0, min(100.0, float(v)))

    # --- Computed helpers ---

    def skill_names(self) -> List[str]:
        """Return a flat list of skill tag strings."""
        return [s.skill.lower() for s in self.skills]

    def skill_map(self) -> Dict[str, int]:
        """Return a dict mapping skill name -> proficiency."""
        return {s.skill.lower(): s.proficiency for s in self.skills}

    def is_available(self) -> bool:
        """True if status is AVAILABLE and below hard capacity ceiling."""
        return (
            self.availability_status == AvailabilityStatus.AVAILABLE
            and self.current_workload < self.capacity_limit
        )

    def has_capacity(self) -> bool:
        """True when utilization is below 95% (hard ceiling threshold)."""
        return self.utilization_percent < 95.0

    def covers_domain(self, domain: str) -> bool:
        """Check if assignee covers the given business domain (case-insensitive)."""
        return domain.lower() in [d.lower() for d in self.business_domains]

    def has_required_skills(self, required: List[str]) -> bool:
        """Return True only if ALL required skills are present."""
        owned = set(self.skill_names())
        return all(r.lower() in owned for r in required)

    class Config:
        use_enum_values = True
