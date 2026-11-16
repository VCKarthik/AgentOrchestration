"""
infra/seed_csa_db.py — Seed CSA/data/csa.db with the three demo workflows.

Idempotent: uses INSERT OR IGNORE throughout. Safe to re-run on every startup.

Cases (matches the demo spec):
  CASE-1001  vendor_onboarding      TechSupply Inc. — insurance cert missing
  CASE-2001  interview_scheduling   Sarah Johnson — background check pending,
                                    conflict of interest (competitor)
  CASE-3001  claim_review           David Kim — $1,200 — all docs verified
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve CSA db path relative to this file's location
_CSA_DB = Path(__file__).parent.parent / "CSA" / "data" / "csa.db"

# Old/stale case_ids that were previously seeded — wiped on each run so the
# Case Workspace / Observatory don't show ghosts from earlier demo iterations.
_STALE_CASE_IDS = (
    "CASE-VND-001", "CASE-CLM-002", "CASE-FRD-003",
    "CASE-CMP-004", "CASE-CLA-005", "CASE-DOC-006",
    "CASE-AUTO-007", "CASE-CLM-008", "CASE-INT-003",
    "CASE-1234", "CASE-123456", "CASE-FIN-005",
    "CASE-HR-006", "CASE-2002", "CASE-3003",
)

# ── Source data ──────────────────────────────────────────────────────────────

EMAILS: list[tuple] = [
    # CASE-1001 — Vendor onboarding
    ("EM-001", "CASE-1001", "vendor_onboarding",
     "Vendor Registration Request - TechSupply Inc.",
     "vendor@techsupply.com", "procurement@acme.com",
     "2026-05-01 09:00:00",
     "Hi — submitting our vendor registration package. Tax certificate "
     "attached. Please confirm next steps for insurance and NDA.",
     "tax_certificate_techsupply.pdf",
     "VTHREAD-1001", ""),
    ("EM-002", "CASE-1001", "vendor_onboarding",
     "Re: Vendor Registration - Documents Required",
     "procurement@acme.com", "vendor@techsupply.com",
     "2026-05-01 11:30:00",
     "Tax cert received. Still need: (1) certificate of insurance "
     "(min $1M liability), (2) signed NDA. Onboarding meeting May 6.",
     "", "VTHREAD-1001", ""),
    ("EM-003", "CASE-1001", "vendor_onboarding",
     "Re: Vendor Registration - NDA Signed",
     "vendor@techsupply.com", "procurement@acme.com",
     "2026-05-02 08:00:00",
     "Signed NDA attached. Insurance certificate is in process — expected "
     "by EOD May 3.",
     "nda_signed_techsupply.pdf", "VTHREAD-1001", ""),

    # CASE-2001 — Interview scheduling
    ("EM-004", "CASE-2001", "interview_scheduling",
     "Application for Senior Developer Role",
     "sarah.johnson@gmail.com", "hr@acme.com",
     "2026-05-02 08:45:00",
     "Submitting my application for the Senior Developer role. Resume "
     "attached. Available for interviews on weekday mornings.",
     "sarah_johnson_resume.pdf", "ITHREAD-2001", ""),
    ("EM-005", "CASE-2001", "interview_scheduling",
     "Interview Invitation - Senior Developer Position",
     "hr@acme.com", "sarah.johnson@gmail.com",
     "2026-05-02 10:00:00",
     "Pleased to invite you to a technical interview on May 7 at 11:00. "
     "Interviewer: Mike Chen. We will follow up with calendar invite.",
     "", "ITHREAD-2001", ""),
    ("EM-006", "CASE-2001", "interview_scheduling",
     "Re: Interview Invitation - Confirmed",
     "sarah.johnson@gmail.com", "hr@acme.com",
     "2026-05-02 12:15:00",
     "Confirmed. Looking forward to it. For context my prior employer was "
     "TechRival Inc. (left 2 weeks ago).",
     "", "ITHREAD-2001", ""),

    # CASE-3001 — Claim review
    ("EM-007", "CASE-3001", "claim_review",
     "Medical Claim Submission - CLM-001",
     "david.kim@acme.com", "claims@acme.com",
     "2026-05-01 14:00:00",
     "Submitting claim for hospital visit on April 28. Total $1,200. "
     "Hospital receipt attached.",
     "hospital_receipt_april28.pdf", "CTHREAD-3001", ""),
    ("EM-008", "CASE-3001", "claim_review",
     "Claim CLM-001 Received - Action Required",
     "claims@acme.com", "david.kim@acme.com",
     "2026-05-01 15:30:00",
     "Receipt received. Need a doctors note for the procedure to complete "
     "the policy check. Please upload by May 3.",
     "", "CTHREAD-3001", ""),
    ("EM-009", "CASE-3001", "claim_review",
     "Re: Claim CLM-001 - Doctors Note Uploaded",
     "david.kim@acme.com", "claims@acme.com",
     "2026-05-02 09:00:00",
     "Doctors note uploaded. All requested documents now provided.",
     "doctors_note_april28.pdf", "CTHREAD-3001", ""),
]

DOCUMENTS: list[tuple] = [
    # CASE-1001
    ("DOC-001", "CASE-1001", "vendor_onboarding",
     "tax_certificate_techsupply.pdf", "pdf",
     "TechSupply Inc. tax certificate", "tax,verified",
     "2026-05-01", "", "verified"),
    ("DOC-002", "CASE-1001", "vendor_onboarding",
     "insurance_certificate_techsupply.pdf", "pdf",
     "Public liability insurance — outstanding", "insurance,missing",
     "2026-05-01", "", "missing"),
    ("DOC-003", "CASE-1001", "vendor_onboarding",
     "nda_signed_techsupply.pdf", "pdf",
     "Mutual NDA — signed by vendor, pending legal review",
     "nda,pending_review", "2026-05-02", "", "pending_review"),

    # CASE-2001
    ("DOC-004", "CASE-2001", "interview_scheduling",
     "sarah_johnson_resume.pdf", "pdf",
     "Candidate resume — 7 years backend experience",
     "resume,verified", "2026-05-02", "", "verified"),
    ("DOC-005", "CASE-2001", "interview_scheduling",
     "interview_scorecard_senior_dev.pdf", "pdf",
     "Senior Developer interview scorecard template",
     "scorecard,active", "2026-05-02", "", "active"),
    ("DOC-006", "CASE-2001", "interview_scheduling",
     "job_description_senior_developer.pdf", "pdf",
     "Senior Developer job description",
     "jd,active", "2026-04-15", "", "active"),
    ("DOC-BG001", "CASE-2001", "interview_scheduling",
     "background_check_status.pdf", "pdf",
     "Background check report — pending vendor turnaround",
     "background_check,pending", "2026-05-02", "", "pending"),

    # CASE-3001
    ("DOC-007", "CASE-3001", "claim_review",
     "hospital_receipt_april28.pdf", "pdf",
     "Itemized hospital receipt — $1,200",
     "receipt,verified", "2026-05-01", "", "verified"),
    ("DOC-008", "CASE-3001", "claim_review",
     "doctors_note_april28.pdf", "pdf",
     "Attending physician note — outpatient procedure",
     "medical,verified", "2026-05-02", "", "verified"),
    ("DOC-009", "CASE-3001", "claim_review",
     "gold_policy_POL-GOLD.pdf", "pdf",
     "POL-GOLD policy summary — per-claim cap $1,500, annual $5,000",
     "policy,active", "2026-01-01", "", "active"),
]

CALENDAR_EVENTS: list[tuple] = [
    # (id, case_id, case_type, title, start_time, end_time, attendees, location, description, status)
    ("CAL-001", "CASE-1001", "vendor_onboarding",
     "Vendor Onboarding Review - TechSupply Inc.",
     "2026-05-06 10:00:00", "2026-05-06 11:00:00",
     "procurement@acme.com,vendor@techsupply.com,compliance@acme.com",
     "Conf Room A / Zoom",
     "Review onboarding package — insurance + NDA must be cleared.",
     "scheduled"),
    ("CAL-002", "CASE-1001", "vendor_onboarding",
     "Compliance Sign-off Meeting - TechSupply",
     "2026-05-08 14:00:00", "2026-05-08 14:30:00",
     "compliance@acme.com,procurement@acme.com",
     "Conf Room B",
     "Final compliance sign-off on TechSupply onboarding.",
     "pending"),

    ("CAL-003", "CASE-2001", "interview_scheduling",
     "Technical Interview - Sarah Johnson",
     "2026-05-07 11:00:00", "2026-05-07 12:00:00",
     "sarah.johnson@gmail.com,mike.chen@acme.com",
     "Zoom",
     "Senior Developer technical screen — system design + coding.",
     "scheduled"),
    ("CAL-004", "CASE-2001", "interview_scheduling",
     "HR Debrief - Senior Developer Round 1",
     "2026-05-07 14:00:00", "2026-05-07 14:30:00",
     "hr@acme.com,mike.chen@acme.com",
     "Conf Room A",
     "Calibration call after Sarah Johnson's technical round.",
     "scheduled"),

    ("CAL-005", "CASE-3001", "claim_review",
     "Claim Review Meeting - CLM-001",
     "2026-05-05 15:00:00", "2026-05-05 15:30:00",
     "claims@acme.com",
     "Internal",
     "Internal review of CLM-001 — all documentation now received.",
     "completed"),
    ("CAL-006", "CASE-3001", "claim_review",
     "Claim Decision Call - David Kim",
     "2026-05-06 11:00:00", "2026-05-06 11:15:00",
     "claims@acme.com,david.kim@acme.com",
     "Phone",
     "Notify David Kim of approval decision.",
     "scheduled"),
]

CASE_HISTORY: list[tuple] = [
    # (id, case_id, case_type, event_type, actor, timestamp, notes, status)
    # CASE-1001
    ("CH-001", "CASE-1001", "vendor_onboarding", "case_opened",
     "procurement@acme.com", "2026-05-01 09:05:00",
     "Vendor onboarding case created for TechSupply Inc.", "open"),
    ("CH-002", "CASE-1001", "vendor_onboarding", "document_reviewed",
     "compliance@acme.com", "2026-05-01 14:00:00",
     "Tax cert verified; insurance + NDA still required.", "in_progress"),
    ("CH-003", "CASE-1001", "vendor_onboarding", "document_received",
     "vendor@techsupply.com", "2026-05-02 08:05:00",
     "NDA received. Insurance still outstanding.", "in_progress"),

    # CASE-2001
    ("CH-004", "CASE-2001", "interview_scheduling", "case_opened",
     "hr@acme.com", "2026-05-02 09:00:00",
     "Application received for Senior Developer role.", "open"),
    ("CH-005", "CASE-2001", "interview_scheduling", "interview_scheduled",
     "hr@acme.com", "2026-05-02 10:05:00",
     "Technical interview scheduled for May 7 11:00.", "in_progress"),
    ("CH-006", "CASE-2001", "interview_scheduling", "interviewer_assigned",
     "mike.chen@acme.com", "2026-05-02 10:10:00",
     "Mike Chen assigned as interviewer.", "in_progress"),
    ("CH-COI-001", "CASE-2001", "interview_scheduling", "conflict_of_interest_flagged",
     "hr_system", "2026-05-02 10:15:00",
     "Candidate's prior employer (TechRival Inc.) is a competitor — "
     "policy HR-09 review required.",
     "in_progress"),

    # CASE-3001
    ("CH-007", "CASE-3001", "claim_review", "case_opened",
     "claims@acme.com", "2026-05-01 14:05:00",
     "Claim CLM-001 submitted for $1,200.", "open"),
    ("CH-008", "CASE-3001", "claim_review", "document_missing",
     "claims@acme.com", "2026-05-01 15:35:00",
     "Doctors note required to proceed.", "on_hold"),
    ("CH-009", "CASE-3001", "claim_review", "document_received",
     "david.kim@acme.com", "2026-05-02 09:05:00",
     "Doctors note uploaded — all documents now received.",
     "under_review"),
    ("CH-010", "CASE-3001", "claim_review", "policy_check",
     "claims@acme.com", "2026-05-02 10:00:00",
     "Policy check passed — $1,200 within $1,500 per-claim cap.",
     "under_review"),
]


def _conn(db_path: Path = _CSA_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_status_column(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN status TEXT")
        conn.commit()
    except Exception:
        pass  # column already exists


def _wipe_stale(c: sqlite3.Cursor) -> None:
    """Remove any rows for old/test case_ids before re-seeding."""
    placeholders = ",".join("?" * len(_STALE_CASE_IDS))
    for table in ("emails", "documents", "calendar_events", "case_history"):
        try:
            c.execute(
                f"DELETE FROM {table} WHERE case_id IN ({placeholders})",
                _STALE_CASE_IDS,
            )
        except Exception:
            pass


def seed_csa(db_path: Path = _CSA_DB) -> None:
    if not db_path.exists():
        logger.warning("CSA db not found at %s — run CSA init first", db_path)
        return

    conn = _conn(db_path)
    _ensure_status_column(conn)
    c = conn.cursor()

    # Idempotency: if all 3 demo cases already have rows, skip.
    c.execute(
        "SELECT case_id FROM emails "
        "WHERE case_id IN ('CASE-1001','CASE-2001','CASE-3001') "
        "GROUP BY case_id"
    )
    already = {r[0] for r in c.fetchall()}
    target = {"CASE-1001", "CASE-2001", "CASE-3001"}

    if already == target:
        logger.info("CSA demo seed already present — skipping")
        conn.close()
        return

    logger.info("Seeding CSA demo cases — wiping stale rows first")
    _wipe_stale(c)

    c.executemany(
        "INSERT OR IGNORE INTO emails "
        "(id,case_id,case_type,subject,sender,recipients,date,body,attachments,thread_id,file_path) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        EMAILS,
    )
    c.executemany(
        "INSERT OR IGNORE INTO documents "
        "(id,case_id,case_type,filename,file_type,description,tags,created_at,file_path,status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        DOCUMENTS,
    )
    c.executemany(
        "INSERT OR IGNORE INTO calendar_events "
        "(id,case_id,case_type,title,start_time,end_time,attendees,location,description,status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        CALENDAR_EVENTS,
    )
    c.executemany(
        "INSERT OR IGNORE INTO case_history "
        "(id,case_id,case_type,event_type,actor,timestamp,notes,status) "
        "VALUES (?,?,?,?,?,?,?,?)",
        CASE_HISTORY,
    )

    conn.commit()
    logger.info(
        "CSA seed applied: %d emails / %d docs / %d calendar / %d history rows",
        len(EMAILS), len(DOCUMENTS), len(CALENDAR_EVENTS), len(CASE_HISTORY),
    )
    conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_csa()
    logger.info("Done.")
