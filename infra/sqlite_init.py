"""
sqlite_init.py — Create the unified AMP workflow state table.

Manages active case state for the orchestrator and dashboard.
Agent-local DBs (CSA/csa.db, GPA/governance_agent.db) remain
separate — they are internal to each agent and isolated by the
HTTP boundary.

SWA's Postgres tables are out of scope (postgres-specific DDL).
See BLOCKERS.md.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "state.db"

DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS active_workflow_state (
    case_id                TEXT PRIMARY KEY,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    current_stage          TEXT NOT NULL,
    agent_status           TEXT NOT NULL DEFAULT '{}',
    amp_state_json         TEXT NOT NULL DEFAULT '{}',
    risk_score             REAL,
    requires_escalation    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_updated_at
    ON active_workflow_state(updated_at);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def upsert_state(case_id: str, stage: str, agent_status: dict, amp_state: dict, *, db_path: Path = DB_PATH) -> None:
    import json
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    risk_score = None
    requires_escalation = 0
    if ro := amp_state.get("risk_output"):
        level_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
        risk_score = level_map.get(str(ro.get("overall_risk_level", "low")).lower(), 0.2)
    if amp_state.get("meta", {}).get("requires_escalation"):
        requires_escalation = 1

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO active_workflow_state
                (case_id, created_at, updated_at, current_stage,
                 agent_status, amp_state_json, risk_score, requires_escalation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                updated_at          = excluded.updated_at,
                current_stage       = excluded.current_stage,
                agent_status        = excluded.agent_status,
                amp_state_json      = excluded.amp_state_json,
                risk_score          = excluded.risk_score,
                requires_escalation = excluded.requires_escalation
            """,
            (
                case_id, now, now, stage,
                json.dumps(agent_status),
                json.dumps(amp_state),
                risk_score,
                requires_escalation,
            ),
        )
        conn.commit()


def list_active_cases(db_path: Path = DB_PATH) -> list[dict]:
    import json
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM active_workflow_state ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {
            "case_id":             r["case_id"],
            "created_at":          r["created_at"],
            "updated_at":          r["updated_at"],
            "current_stage":       r["current_stage"],
            "agent_status":        json.loads(r["agent_status"]),
            "risk_score":          r["risk_score"],
            "requires_escalation": bool(r["requires_escalation"]),
        }
        for r in rows
    ]


def get_amp_state(case_id: str, db_path: Path = DB_PATH) -> dict | None:
    import json
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT amp_state_json FROM active_workflow_state WHERE case_id = ?",
            (case_id,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["amp_state_json"])


def init_sqlite(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(DDL)
    logger.info("SQLite state DB initialised at %s", db_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_sqlite()
