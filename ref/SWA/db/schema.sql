-- Shadow Work Agent v3 — SQLite Schema

CREATE TABLE IF NOT EXISTS cases (
    case_id          TEXT PRIMARY KEY,
    case_type        TEXT NOT NULL,
    status           TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    closed_at        TEXT,
    domain_metadata  TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_type   ON cases(case_type);

CREATE TABLE IF NOT EXISTS activity_log (
    event_id           TEXT PRIMARY KEY,
    case_id            TEXT NOT NULL,
    timestamp          TEXT NOT NULL,
    actor_id           TEXT NOT NULL,
    actor_type         TEXT NOT NULL,
    action_type        TEXT NOT NULL,
    target_entity      TEXT NOT NULL,
    target_entity_type TEXT NOT NULL,
    parent_task_id     TEXT,
    context_payload    TEXT DEFAULT '{}',
    outcome            TEXT NOT NULL,
    created_at         TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_activity_case    ON activity_log(case_id);
CREATE INDEX IF NOT EXISTS idx_activity_ts      ON activity_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_activity_actor   ON activity_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_activity_action  ON activity_log(action_type);
CREATE INDEX IF NOT EXISTS idx_activity_case_ts ON activity_log(case_id, timestamp);

CREATE TABLE IF NOT EXISTS case_portfolios (
    case_id             TEXT PRIMARY KEY,
    last_updated        TEXT NOT NULL DEFAULT (datetime('now')),
    total_events        INTEGER NOT NULL DEFAULT 0,
    distinct_actors     INTEGER NOT NULL DEFAULT 0,
    distinct_actions    INTEGER NOT NULL DEFAULT 0,
    case_duration_hours REAL,
    portfolio_json      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id            TEXT PRIMARY KEY,
    run_timestamp     TEXT NOT NULL DEFAULT (datetime('now')),
    scope             TEXT NOT NULL,
    window_start      TEXT NOT NULL,
    window_end        TEXT NOT NULL,
    events_processed  INTEGER NOT NULL,
    patterns_detected INTEGER NOT NULL,
    recommendations   INTEGER NOT NULL,
    escalations       INTEGER NOT NULL,
    output_json       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON analysis_runs(run_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_runs_scope     ON analysis_runs(scope);

CREATE TABLE IF NOT EXISTS ingestion_log (
    ingestion_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT NOT NULL DEFAULT (datetime('now')),
    source_agent     TEXT,
    event_id         TEXT,
    case_id          TEXT,
    status           TEXT NOT NULL,
    rejection_reason TEXT,
    raw_payload      TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingestion_timestamp ON ingestion_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ingestion_status    ON ingestion_log(status);

CREATE TABLE IF NOT EXISTS cluster_snapshots (
    snapshot_id        TEXT PRIMARY KEY,
    run_id             TEXT NOT NULL,
    snapshot_timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    total_cases        INTEGER NOT NULL,
    total_events       INTEGER NOT NULL,
    clusters_found     INTEGER NOT NULL,
    cluster_summary    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON cluster_snapshots(snapshot_timestamp DESC);
