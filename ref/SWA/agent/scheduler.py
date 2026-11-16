"""
agent/scheduler.py
─────────────────────────────────────────────────────────────────
Auto-trigger for Shadow Work Agent.

NEW FILE — add to agent/ folder alongside orchestrator.py.
No existing files are changed.

How it works:
  After your teammate's integration layer calls ingest_batch(),
  they call check_and_run() once. The scheduler checks if enough
  new cases have accumulated since the last run. If yes, it fires
  analyze() automatically. If no, it does nothing.

Threshold (default): 20 new cases since last run.
Configurable via .env: SCHEDULER_CASE_THRESHOLD=20

Usage in your teammate's integration layer:
  from agent.scheduler import check_and_run

  # After ingesting events for a case:
  ingest_case(case_payload)
  ingest_batch(events, source_agent="integration_layer")
  check_and_run()   ← one line, handles everything else
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("shadow_work.scheduler")

# ── Config ────────────────────────────────────────────────────────────
CASE_THRESHOLD = int(os.getenv("SCHEDULER_CASE_THRESHOLD", "20"))

# ── State file ────────────────────────────────────────────────────────
# Stores the case count at the time of the last successful run.
# Lives in output/ folder alongside agent.log.
# Simple text file — no extra DB table needed.
_STATE_FILE = Path("output/scheduler_state.txt")


def _read_last_count() -> int:
    """Read the case count from the last run. Returns 0 if first run."""
    try:
        _STATE_FILE.parent.mkdir(exist_ok=True)
        if _STATE_FILE.exists():
            return int(_STATE_FILE.read_text().strip())
        return 0
    except Exception:
        return 0


def _write_last_count(count: int) -> None:
    """Persist the current case count after a successful run."""
    try:
        _STATE_FILE.parent.mkdir(exist_ok=True)
        _STATE_FILE.write_text(str(count))
    except Exception as e:
        logger.warning(f"[scheduler] could not write state file: {e}")


def get_status() -> dict:
    """
    Return current scheduler status — useful for your teammate to
    show in a dashboard or log.
    """
    try:
        from db import db
        current_count = db.count_cases()
    except Exception as e:
        return {"error": str(e)}

    last_count = _read_last_count()
    new_since_last_run = current_count - last_count

    return {
        "current_cases":        current_count,
        "cases_at_last_run":    last_count,
        "new_since_last_run":   new_since_last_run,
        "threshold":            CASE_THRESHOLD,
        "will_trigger_on_next": new_since_last_run >= CASE_THRESHOLD,
        "cases_until_trigger":  max(0, CASE_THRESHOLD - new_since_last_run),
    }


def check_and_run(force: bool = False) -> dict:
    """
    Main entry point for the integration layer.

    Call this after every ingest_batch(). It checks whether enough
    new cases have accumulated to warrant a Shadow Work run.

    Args:
        force: if True, run regardless of threshold (useful for testing).

    Returns:
        dict with keys:
          triggered   (bool)   — whether the agent ran
          reason      (str)    — why it did or did not run
          run_id      (str)    — run_id if triggered, else None
          metrics     (dict)   — run metrics if triggered, else None
          status      (dict)   — current scheduler status
    """
    Path("output").mkdir(exist_ok=True)

    # ── Check case count ──────────────────────────────────────────────
    try:
        from db import db
        current_count = db.count_cases()
    except Exception as e:
        logger.error(f"[scheduler] DB count failed: {e}")
        return {
            "triggered": False,
            "reason":    f"DB error: {e}",
            "run_id":    None,
            "metrics":   None,
            "status":    {},
        }

    last_count = _read_last_count()
    new_cases  = current_count - last_count

    logger.info(
        f"[scheduler] cases: current={current_count}, "
        f"last_run={last_count}, new={new_cases}, threshold={CASE_THRESHOLD}"
    )

    # ── Decide whether to trigger ─────────────────────────────────────
    if not force and new_cases < CASE_THRESHOLD:
        reason = (
            f"only {new_cases} new cases since last run "
            f"(threshold: {CASE_THRESHOLD}). "
            f"Need {CASE_THRESHOLD - new_cases} more."
        )
        logger.info(f"[scheduler] skipping — {reason}")
        return {
            "triggered": False,
            "reason":    reason,
            "run_id":    None,
            "metrics":   None,
            "status":    get_status(),
        }

    # ── Trigger analysis ──────────────────────────────────────────────
    trigger_reason = "forced" if force else f"{new_cases} new cases >= threshold {CASE_THRESHOLD}"
    logger.info(f"[scheduler] triggering analysis — {trigger_reason}")

    try:
        from agent.orchestrator import analyze
        output, meta = analyze(trigger_type="auto_scheduler")

        # Persist current count so next check compares against this run
        _write_last_count(current_count)

        metrics = {
            "events_processed":     output.metrics.events_processed,
            "patterns_detected":    output.metrics.patterns_detected,
            "recommendations_made": output.metrics.recommendations_made,
            "escalations_raised":   output.metrics.escalations_raised,
            "processing_time_ms":   output.metrics.processing_time_ms,
        }

        evolution_summary = None
        if meta.get("cluster_evolution"):
            d = meta["cluster_evolution"].get("delta_summary", {})
            evolution_summary = {
                "new_clusters":         d.get("new_clusters", 0),
                "strengthened_clusters":d.get("strengthened_clusters", 0),
                "stable_clusters":      d.get("stable_clusters", 0),
                "dissolved_clusters":   d.get("dissolved_clusters", 0),
            }

        logger.info(
            f"[scheduler] run complete — run_id={output.run_id}, "
            f"recommendations={metrics['recommendations_made']}, "
            f"escalations={metrics['escalations_raised']}"
        )

        return {
            "triggered":        True,
            "reason":           trigger_reason,
            "run_id":           output.run_id,
            "metrics":          metrics,
            "cluster_evolution":evolution_summary,
            "status":           get_status(),
        }

    except Exception as e:
        logger.error(f"[scheduler] analysis failed: {e}")
        return {
            "triggered": False,
            "reason":    f"analysis error: {e}",
            "run_id":    None,
            "metrics":   None,
            "status":    get_status(),
        }
