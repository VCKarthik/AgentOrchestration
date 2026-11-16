"""
init_db.py — One-shot AMP data layer initializer.

Run once before starting agents:
    python data/init_db.py

Creates:
  infra/state.db          — SQLite orchestrator state
  infra/qdrant_store/     — Qdrant local file store
    collections:
      iaa_corpus           — IAA RAG corpus (process history)
      policy_knowledge     — GPA/RRA policy docs (tag-filtered by case_type)
"""
import logging
import sys
from pathlib import Path

# Allow running from any cwd
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.sqlite_init import init_sqlite
from infra.qdrant_init import init_qdrant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("=== AMP data layer init ===")
    init_sqlite()
    init_qdrant(ingest_cases=True, ingest_policies_flag=True)
    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
