"""
db.py — Convenience re-exports from sqlite_init for import ergonomics.

Import from here, not sqlite_init, so callers don't need to know the file name.

Usage:
    from infra.db import get_connection, upsert_state, list_active_cases, get_amp_state
"""
from .sqlite_init import (
    get_connection,
    upsert_state,
    list_active_cases,
    get_amp_state,
    DB_PATH,
)

__all__ = [
    "get_connection",
    "upsert_state",
    "list_active_cases",
    "get_amp_state",
    "DB_PATH",
]
