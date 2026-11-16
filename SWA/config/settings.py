"""
Central configuration. All thresholds tunable via environment variables.

V3 changes:
  - ANALYSIS_WINDOW_DAYS bumped to 90 (200 cases need a wider window)
  - DBSCAN_EPS loosened to 1.2 (denser dataset still needs some breathing room)
  - Added all 6 agent actors to the registry
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project root = two levels up from this file (config/settings.py → root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings:
    # ── Database ──────────────────────────────────────────────────
    # Default resolves to <project_root>/swa_v3.db regardless of where
    # Python is launched from — safe when included as a subfolder in a
    # larger repo by another team.
    DB_PATH = os.getenv("DB_PATH", str(_PROJECT_ROOT / "swa_v3.db"))

    # ── LLM ───────────────────────────────────────────────────────
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-2.0-flash"

    # ── Heuristic detector thresholds ─────────────────────────────
    ANALYSIS_WINDOW_DAYS = int(os.getenv("ANALYSIS_WINDOW_DAYS", "90"))
    MIN_REPETITION_THRESHOLD = int(os.getenv("MIN_REPETITION_THRESHOLD", "3"))
    MIN_REGULARITY_SCORE = float(os.getenv("MIN_REGULARITY_SCORE", "0.7"))
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))

    # ── ML clustering thresholds ──────────────────────────────────
    DBSCAN_EPS = float(os.getenv("DBSCAN_EPS", "1.2"))
    DBSCAN_MIN_SAMPLES = int(os.getenv("DBSCAN_MIN_SAMPLES", "5"))

    # Minimum events and cases required before DBSCAN is worth running.
    # Below these thresholds the agent falls back to heuristic detectors only.
    ML_MIN_EVENTS = int(os.getenv("ML_MIN_EVENTS", "100"))
    ML_MIN_CASES  = int(os.getenv("ML_MIN_CASES",  "10"))

    # ─────────────────────────────────────────────────────────────────
    # CLOSED ACTION VOCABULARY
    # ─────────────────────────────────────────────────────────────────
    AUTOMATABLE_ACTIONS = {
        "sent_followup", "sent_reminder", "status_check",
        "requested_document", "scheduled_meeting",
        "data_lookup", "policy_check",
    }

    APPROVAL_TYPE_ACTIONS = {
        "approved", "rejected", "escalated_to_human",
        "manual_override", "policy_exception_granted",
    }

    INFORMATIONAL_ACTIONS = {
        "received_message", "logged_note", "viewed_document",
        "case_opened", "case_closed", "task_assigned",
        "context_gathered", "risk_flagged", "intent_predicted",
    }

    @property
    def ALL_ACTION_TYPES(self) -> set[str]:
        return (
            self.AUTOMATABLE_ACTIONS
            | self.APPROVAL_TYPE_ACTIONS
            | self.INFORMATIONAL_ACTIONS
        )

    # ─────────────────────────────────────────────────────────────────
    # CLOSED TARGET ENTITY TYPES
    # ─────────────────────────────────────────────────────────────────
    VALID_TARGET_TYPES = {
        "external_contact", "internal_system", "internal_user",
        "task", "document",
    }

    # ─────────────────────────────────────────────────────────────────
    # AGENT REGISTRY
    # ─────────────────────────────────────────────────────────────────
    KNOWN_AGENT_ACTORS = {
        "context_stitching_agent", "risk_radar_agent",
        "governance_policy_agent", "delegation_agent",
        "intent_anticipation_agent", "shadow_work_agent",
    }


settings = Settings()
