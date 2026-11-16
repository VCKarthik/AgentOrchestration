"""
repositories/audit_repository.py
----------------------------------
In-memory repository for AuditLog records.

Stores all delegation decisions with their full audit context.
Replace with an append-only database table or event store for production.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..models.outputs import AuditLog


class AuditRepository:
    """
    In-memory append-only store for AuditLog entries.

    Each delegation evaluation writes exactly one audit record.
    Supports lookup by audit ID, task ID, and bulk retrieval.
    """

    def __init__(self) -> None:
        self._store: Dict[str, AuditLog] = {}

    def save(self, log: AuditLog) -> None:
        """Persist an audit log entry."""
        self._store[log.audit_log_id] = log

    def get_by_id(self, audit_log_id: str) -> Optional[AuditLog]:
        """Retrieve an audit log entry by its ID; returns None if not found."""
        return self._store.get(audit_log_id)

    def get_by_task_id(self, task_id: str) -> List[AuditLog]:
        """Return all audit records for a given task (supports reassignment history)."""
        return [log for log in self._store.values() if log.task_id == task_id]

    def get_all(self) -> List[AuditLog]:
        """Return all stored audit records (ordered by timestamp ascending)."""
        return sorted(self._store.values(), key=lambda x: x.timestamp)

    def count(self) -> int:
        """Return total number of audit records stored."""
        return len(self._store)
