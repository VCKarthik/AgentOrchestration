"""DB layer — SQLite backend. Returns pandas DataFrames for analysis-friendly access."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from config.settings import settings


# ── CONNECTION ────────────────────────────────────────────────────

def _db_path() -> str:
    return settings.DB_PATH


@contextmanager
def get_connection():
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── HELPERS ───────────────────────────────────────────────────────

def _dumps(v: Any) -> str:
    return json.dumps(v, default=str)


def _loads(v: Any) -> Any:
    if v is None:
        return {}
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return {}


def _ts(v: Any) -> Optional[str]:
    """Convert a datetime (or None) to an ISO string for storage."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def _parse_ts(v: Any) -> Optional[datetime]:
    """Parse an ISO string from SQLite into a timezone-aware datetime."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(v))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ── SCHEMA INIT ───────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    schema = Path(__file__).parent / "schema.sql"
    sql = schema.read_text()
    with get_connection() as conn:
        conn.executescript(sql)


# ── CASES ─────────────────────────────────────────────────────────

def upsert_case(case: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO cases (case_id, case_type, status, created_at, closed_at, domain_metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE
            SET status = excluded.status,
                closed_at = excluded.closed_at,
                domain_metadata = excluded.domain_metadata
        """, (
            case["case_id"], case["case_type"], case["status"],
            _ts(case["created_at"]), _ts(case.get("closed_at")),
            _dumps(case.get("domain_metadata", {})),
        ))


def list_all_cases() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT case_id FROM cases ORDER BY created_at").fetchall()
    return [r["case_id"] for r in rows]


def count_cases() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]


# ── ACTIVITY LOG ──────────────────────────────────────────────────

def insert_event(event: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO activity_log
            (event_id, case_id, timestamp, actor_id, actor_type, action_type,
             target_entity, target_entity_type, parent_task_id, context_payload, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event["event_id"], event["case_id"], _ts(event["timestamp"]),
            event["actor_id"], event["actor_type"], event["action_type"],
            event["target_entity"], event["target_entity_type"],
            event.get("parent_task_id"),
            _dumps(event.get("context_payload", {})),
            event["outcome"],
        ))


def fetch_events_in_window(
    window_start: datetime,
    window_end: datetime,
    case_id: Optional[str] = None,
    case_type: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch activity_log events between [window_start, window_end).

    Filters:
      - case_id:   restrict to a single case (most specific).
      - case_type: restrict to all cases of a given domain (e.g. "vendor_onboarding").
                   Joins activity_log → cases on case_id. Use this to keep pattern
                   detection domain-aware so vendor onboardings don't get clustered
                   with claim reviews.
    case_id wins over case_type if both are set.
    """
    start_s = _ts(window_start)
    end_s = _ts(window_end)

    base_select = """
        SELECT a.event_id, a.case_id, a.timestamp, a.actor_id, a.actor_type, a.action_type,
               a.target_entity, a.target_entity_type, a.parent_task_id, a.context_payload, a.outcome
        FROM activity_log AS a
    """

    if case_id:
        query = base_select + """
            WHERE a.timestamp >= ? AND a.timestamp < ? AND a.case_id = ?
            ORDER BY a.timestamp ASC
        """
        params = (start_s, end_s, case_id)
    elif case_type:
        query = base_select + """
            JOIN cases AS c ON c.case_id = a.case_id
            WHERE a.timestamp >= ? AND a.timestamp < ? AND c.case_type = ?
            ORDER BY a.timestamp ASC
        """
        params = (start_s, end_s, case_type)
    else:
        query = base_select + """
            WHERE a.timestamp >= ? AND a.timestamp < ?
            ORDER BY a.timestamp ASC
        """
        params = (start_s, end_s)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    df["context_payload"] = df["context_payload"].apply(_loads)
    return df


def count_events() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]


# ── CASE PORTFOLIOS ───────────────────────────────────────────────

def save_case_portfolio(portfolio: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO case_portfolios
            (case_id, last_updated, total_events, distinct_actors,
             distinct_actions, case_duration_hours, portfolio_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE
            SET last_updated = excluded.last_updated,
                total_events = excluded.total_events,
                distinct_actors = excluded.distinct_actors,
                distinct_actions = excluded.distinct_actions,
                case_duration_hours = excluded.case_duration_hours,
                portfolio_json = excluded.portfolio_json
        """, (
            portfolio["case_id"], _ts(datetime.now(timezone.utc)),
            portfolio["total_events"], portfolio["distinct_actors"],
            portfolio["distinct_actions"], portfolio.get("case_duration_hours"),
            _dumps(portfolio["portfolio_json"]),
        ))


def get_case_portfolio(case_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM case_portfolios WHERE case_id = ?", (case_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["portfolio_json"] = _loads(d.get("portfolio_json"))
    return d


# ── INGESTION LOG ─────────────────────────────────────────────────

def log_ingestion(record: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO ingestion_log
            (source_agent, event_id, case_id, status, rejection_reason, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            record.get("source_agent"), record.get("event_id"),
            record.get("case_id"), record["status"],
            record.get("rejection_reason"),
            _dumps(record.get("raw_payload", {})),
        ))


# ── ANALYSIS RUNS ─────────────────────────────────────────────────

def save_analysis_run(record: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO analysis_runs
            (run_id, run_timestamp, scope, window_start, window_end,
             events_processed, patterns_detected, recommendations, escalations, output_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["run_id"], _ts(record["run_timestamp"]), record["scope"],
            _ts(record["window_start"]), _ts(record["window_end"]),
            record["events_processed"], record["patterns_detected"],
            record["recommendations"], record["escalations"],
            _dumps(record["output_json"]),
        ))


# ── CLUSTER SNAPSHOTS ─────────────────────────────────────────────

def save_cluster_snapshot(
    run_id: str,
    total_cases: int,
    total_events: int,
    clusters: list[dict],
) -> str:
    snapshot_id = f"snap_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO cluster_snapshots
            (snapshot_id, run_id, snapshot_timestamp, total_cases, total_events, clusters_found, cluster_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_id, run_id, _ts(datetime.now(timezone.utc)),
            total_cases, total_events, len(clusters), _dumps(clusters),
        ))
    return snapshot_id


def get_latest_snapshot() -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("""
            SELECT snapshot_id, run_id, snapshot_timestamp, total_cases,
                   total_events, clusters_found, cluster_summary
            FROM cluster_snapshots
            ORDER BY snapshot_timestamp DESC LIMIT 1
        """).fetchone()
    if not row:
        return None
    d = dict(row)
    d["cluster_summary"] = _loads(d.get("cluster_summary"))
    return d


def get_previous_snapshot(before_run_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("""
            SELECT snapshot_id, run_id, snapshot_timestamp, total_cases,
                   total_events, clusters_found, cluster_summary
            FROM cluster_snapshots
            WHERE run_id != ?
            ORDER BY snapshot_timestamp DESC LIMIT 1
        """, (before_run_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["cluster_summary"] = _loads(d.get("cluster_summary"))
    return d


def list_all_snapshots() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT snapshot_id, run_id, snapshot_timestamp, total_cases,
                   total_events, clusters_found
            FROM cluster_snapshots
            ORDER BY snapshot_timestamp ASC
        """).fetchall()
    return [dict(r) for r in rows]


# ── HELPERS ───────────────────────────────────────────────────────

def default_window() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=settings.ANALYSIS_WINDOW_DAYS)
    return start, now
