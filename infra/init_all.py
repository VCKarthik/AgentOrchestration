"""
infra/init_all.py — AMP data layer initialization entry point.

Run once before starting agents:
  python -m infra.init_all

Order:
  1. SQLite state DB (infra/state.db)
  2. CSA demo seed (CSA/data/csa.db)
  3. Qdrant collections (historical_cases + policy_knowledge)

All steps are idempotent — safe to re-run on every startup.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("=== AMP: Initializing data layer ===")

    logger.info("Step 1/4: SQLite state DB")
    try:
        from infra.sqlite_init import init_sqlite
        init_sqlite()
        logger.info("  state.db ready")
    except Exception as exc:
        logger.error("  state.db init failed: %s", exc)
        raise

    logger.info("Step 2/4: CSA demo seed")
    try:
        from infra.seed_csa_db import seed_csa
        seed_csa()
        logger.info("  CSA seed done")
    except Exception as exc:
        logger.warning("  CSA seed failed (non-fatal): %s", exc)

    logger.info("Step 3/4: Qdrant collections")
    # NOTE: Qdrant policy_knowledge is also pre-seeded with policy embeddings
    # in production mode this would be empty until upload, but keeping for now
    # since GPA decision_engine has fallbacks. May revisit.
    try:
        from infra.qdrant_init import init_qdrant
        init_qdrant()
        logger.info("  Qdrant ready")
    except Exception as exc:
        logger.warning("  Qdrant init failed (non-fatal): %s", exc)

    # Production mode: GPA also starts empty. Customer uploads their own
    # policy documents via the Streamlit sidebar (or GPA's /dev/upload-policy
    # endpoint). Schema-only init via GPA's ORM happens lazily on first request.

    logger.info("Step 4/4: SWA SQLite schema")
    try:
        import os
        import subprocess
        import sys
        swa_path = os.path.join(os.path.dirname(__file__), "..", "SWA")
        # Run in a clean subprocess with SWA as cwd: under start_agents.sh,
        # PYTHONPATH=IAA:GPA makes GPA/db.py (a regular module) shadow SWA's
        # namespace package `db/`, so an in-process import picks the wrong db.
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        proc = subprocess.run(
            [sys.executable, "-c", "from db import db; db.init_db(); print(db._db_path())"],
            cwd=swa_path, env=env, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0:
            logger.info("  SWA DB ready at %s", proc.stdout.strip())
        else:
            logger.warning("  SWA DB init failed (non-fatal): %s", proc.stderr.strip()[-300:])
    except Exception as exc:
        logger.warning("  SWA DB init failed (non-fatal): %s", exc)

    # Production mode: SWA DB starts empty. The customer (or the Streamlit
    # workflow-context uploader) feeds in their own historical events.
    # New cases submitted via the orchestrator add to the corpus over time.

    logger.info("=== AMP: Data layer ready ===")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    main()
