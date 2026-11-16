"""
repositories/bandwidth_repository.py
------------------------------------

Improved Bandwidth Repository

✔ Fixes KeyError issue
✔ Adds logging (important for audit + debugging)
✔ Adds utilization calculation (needed for intelligent assignment)
✔ Future-ready for LLM + dynamic workload systems
"""

from __future__ import annotations

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class BandwidthRepository:
    """
    Tracks PA workload and availability.

    IMPORTANT:
    - Uses SAME IDs as AssigneeRepository (EMP-001, etc.)
    - Provides safe fallbacks (no crashes)
    - Adds observability (logs warnings)
    """

    def __init__(self):

        # MUST match AssigneeRepository IDs
        self._store: Dict[str, Dict] = {
            "EMP-001": {"capacity": 40, "assigned_hours": 28},
            "EMP-002": {"capacity": 40, "assigned_hours": 35},
            "EMP-003": {"capacity": 40, "assigned_hours": 10},
            "EMP-004": {"capacity": 40, "assigned_hours": 20},
            "EMP-005": {"capacity": 40, "assigned_hours": 30},
            "EMP-006": {"capacity": 40, "assigned_hours": 40},  # fully booked
            "EMP-007": {"capacity": 40, "assigned_hours": 5},
            "EMP-008": {"capacity": 40, "assigned_hours": 15},
            "EMP-009": {"capacity": 40, "assigned_hours": 0},
        }

    # ------------------------------------------------------------
    # CORE FUNCTION — AVAILABLE HOURS
    # ------------------------------------------------------------
    def get_available_hours(self, emp_id: str) -> float:
        """
        Returns remaining available hours.

        ✔ Safe fallback (prevents crash)
        ✔ Logs missing employees (important for debugging)
        """

        data = self._store.get(emp_id)

        if data is None:
            logger.warning(
                "[BandwidthRepo] Missing EMP ID %s — assuming full availability",
                emp_id,
            )
            return 40.0

        return float(data["capacity"] - data["assigned_hours"])

    # ------------------------------------------------------------
    # NEW — UTILIZATION (VERY IMPORTANT FOR SCORING)
    # ------------------------------------------------------------
    def get_utilization(self, emp_id: str) -> float:
        """
        Returns utilization percentage (0–100).
        """

        data = self._store.get(emp_id)

        if data is None:
            return 0.0

        capacity = data["capacity"]
        used = data["assigned_hours"]

        if capacity == 0:
            return 0.0

        return round((used / capacity) * 100, 2)

    # ------------------------------------------------------------
    # OPTIONAL — UPDATE WORKLOAD
    # ------------------------------------------------------------
    def consume_hours(self, emp_id: str, hours: float) -> None:
        """
        Simulates assigning work to a PA.
        """

        if emp_id not in self._store:
            logger.warning(
                "[BandwidthRepo] Cannot update workload — unknown EMP %s",
                emp_id,
            )
            return

        self._store[emp_id]["assigned_hours"] += hours

    # ------------------------------------------------------------
    # OPTIONAL — SYNC (FUTURE READY)
    # ------------------------------------------------------------
    def sync_with_assignees(self, assignees) -> None:
        """
        Ensures every assignee has a bandwidth entry.

        Future use: prevents mismatch when new employees are added.
        """

        for a in assignees:
            if a.assignee_id not in self._store:
                logger.info(
                    "[BandwidthRepo] Auto-adding missing EMP %s",
                    a.assignee_id,
                )
                self._store[a.assignee_id] = {
                    "capacity": 40,
                    "assigned_hours": 0,
                }

    # ------------------------------------------------------------
    # DEBUG / INSPECTION
    # ------------------------------------------------------------
    def get_all(self) -> Dict:
        return self._store