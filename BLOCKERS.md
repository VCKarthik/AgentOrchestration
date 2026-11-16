# Project AMP — Refactor Blockers

Blockers that would take >2 hours to resolve. Logged and moved on per refactor rules.

---

## ~~BLOCKER-1: SWA PostgreSQL → SQLite migration~~ — RESOLVED (Session 7)

> **Resolved:** SWA was replaced wholesale from `ref/SWA/` with a SQLite-backed
> build (`SWA/db/db.py` uses `sqlite3`, DB at `SWA/swa_v3.db`). Postgres vars and
> the `psycopg` dependency have been removed. Original blocker kept for history:

## BLOCKER-1: SWA PostgreSQL → SQLite migration

**Phase 3** planned to drop Postgres and run everything on SQLite. SWA's DB uses:
- `TIMESTAMPTZ` (timezone-aware timestamps)
- `JSONB` (binary JSON with operators)
- `BIGSERIAL` (auto-increment)
- `ON CONFLICT` upsert syntax with Postgres semantics

None of these port directly to SQLite without rewriting `SWA/db/db.py` and `SWA/db/schema.sql`.

**Impact for demo:** None. SWA runs in-process (imported directly by orchestrator, no HTTP). Its Postgres DB is only needed if SWA runs standalone. For `make demo`, SWA is embedded in the orchestrator container and needs no external DB.

**Workaround applied:** `docker-compose.yml` does NOT start a Postgres service. SWA runs in-process without its DB. The `SWA/config/settings.py` DB config will simply not connect — SWA analysis still runs (it's in-memory).

**To fix properly (post-demo):** Rewrite `SWA/db/db.py` with SQLite-compatible DDL. Estimated: 3–4 hours.

---

## BLOCKER-2: CSA/GPA agent-local DB consolidation

**Phase 3** planned to collapse CSA/csa.db and GPA/governance_agent.db into the single `infra/state.db`.

**Why deferred:** Both DBs are used internally by agent ORM/SQL code. Consolidating requires:
- Changing CSA's `DB_PATH` reference and refactoring query logic
- Migrating GPA's 5 SQLAlchemy models to the new schema or adding a new engine config

Touching agent source code violates the refactor rule ("Never modify agent source code to accommodate orchestrator needs").

**Impact for demo:** None. Both DBs work. The new `infra/state.db` is the orchestrator-level state layer; agent-local DBs remain agent-local.

**To fix properly (post-demo):** Extract CSA DB layer behind an abstraction, point both agents at `infra/state.db`. Estimated: 2–3 hours.

---

## BLOCKER-3: IAA qdrant_store path on Docker

**Phase 4 note:** IAA's `qdrant_client_singleton.py` reads `QDRANT_PATH=./IAA/qdrant_store` (relative to CWD). Inside Docker, CWD is `/app` (IAA's build context), so the path resolves to `/app/qdrant_store`. The compose volume mount must align with this path.

**Workaround:** Set `QDRANT_HOST` env var in compose to point IAA at the shared Qdrant container instead of local file mode.
