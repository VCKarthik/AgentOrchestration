"""
GPA policy seeder — populates policy_documents, policy_chunks, and policy_rules
from data/policies/*.md for the three AMP demo domains.

Safe to re-run: skips any PolicyDocument whose file_name already exists
(INSERT OR IGNORE semantics via pre-existence check).

NOTE: The GPA rule_extractor.py is designed for procurement-style PDF prose
(patterns like "exceeding $X", "board of trustees must approve"). It does not
fire on markdown table syntax ("> $X | Board approval required |"). Rules are
therefore inserted directly here, derived from a manual read of each policy file.

ref/GPA_ref approach reviewed — same rule-matching logic, no structural benefit
over the direct seed approach used here.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)

# ── Policy definitions ────────────────────────────────────────────────────────
# Each entry maps one .md file to its ORM fields and a list of concrete rules.
# Rules are tuples: (rule_type, subject, operator, value, unit, action,
#                    condition_text, confidence, approver)

_POLICIES: list[dict] = [
    {
        "file_name":   "procurement.md",
        "title":       "Procurement & Vendor Onboarding Policy",
        "policy_type": "vendor_onboarding",
        "department":  "procurement",
        "source":      "data/policies/procurement.md",
        "rules": [
            (
                "approval_threshold", "monetary_value", ">=", "500000", "USD", "ESCALATE",
                "Contract value exceeds $500,000 — Board approval required.",
                0.95, "board_of_trustees",
            ),
            (
                "approval_threshold", "monetary_value", ">=", "100000", "USD", "ESCALATE",
                "Contract value exceeds $100,000 — CFO and Procurement Director approval required.",
                0.90, "cfo",
            ),
            (
                "approval_threshold", "monetary_value", ">=", "10000", "USD", "ESCALATE",
                "Contract value exceeds $10,000 — Procurement Director approval required.",
                0.85, "procurement_director",
            ),
        ],
    },
    {
        "file_name":   "claims.md",
        "title":       "Claims Review Policy",
        "policy_type": "claim_review",
        "department":  "claims",
        "source":      "data/policies/claims.md",
        "rules": [
            # Auto-approval threshold lifted to $1,500 to match the
            # POL-GOLD policy advertised in the demo deck. Claims under
            # $1,500 with all documents present pass through GPA without
            # human approval.
            (
                "approval_threshold", "monetary_value", ">=", "25000", "USD", "ESCALATE",
                "Claim amount exceeds $25,000 — mandatory escalation required.",
                0.95, "claims_committee",
            ),
            (
                "approval_threshold", "monetary_value", ">", "5000", "USD", "ESCALATE",
                "Property damage claim exceeds $5,000 — Risk committee review required.",
                0.88, "risk_committee",
            ),
            (
                "approval_threshold", "monetary_value", ">=", "1500", "USD", "ESCALATE",
                "Claim amount exceeds $1,500 — exceeds POL-GOLD auto-approval threshold; manager sign-off required.",
                0.82, "manager",
            ),
        ],
    },
    {
        "file_name":   "fraud.md",
        "title":       "Fraud Investigation Policy",
        "policy_type": "fraud_investigation",
        "department":  "compliance",
        "source":      "data/policies/fraud.md",
        "rules": [
            (
                "approval_threshold", "monetary_value", ">=", "5000", "USD", "ESCALATE",
                "Financial threshold exceeded ($5,000+) — SAR filing required; escalate to Compliance Officer.",
                0.95, "compliance_officer",
            ),
            (
                "case_type_requirement", "task_type", "==", "fraud_investigation", None, "ESCALATE",
                "All fraud investigation cases require Compliance Officer review before delegation.",
                0.90, "compliance_officer",
            ),
        ],
    },
    {
        "file_name":   "compliance.md",
        "title":       "Compliance Review Policy",
        "policy_type": "compliance_review",
        "department":  "legal",
        "source":      "data/policies/compliance.md",
        "rules": [
            (
                "approval_threshold", "monetary_value", ">=", "100000", "USD", "ESCALATE",
                "Compliance review scope exceeds $100,000 — General Counsel and Compliance Director approval required.",
                0.90, "general_counsel",
            ),
            (
                "approval_threshold", "monetary_value", ">=", "50000", "USD", "ESCALATE",
                "Compliance review scope exceeds $50,000 — Compliance Director approval required.",
                0.85, "compliance_director",
            ),
        ],
    },
    {
        "file_name":   "financial.md",
        "title":       "Financial Approval Policy",
        "policy_type": "financial_approval",
        "department":  "finance",
        "source":      "data/policies/financial.md",
        "rules": [
            (
                "approval_threshold", "monetary_value", ">=", "100000", "USD", "ESCALATE",
                "Transaction exceeds $100,000 — CFO approval required.",
                0.92, "cfo",
            ),
            (
                "approval_threshold", "monetary_value", ">=", "50000", "USD", "ESCALATE",
                "Transaction exceeds $50,000 — Finance Director approval required.",
                0.87, "finance_director",
            ),
            (
                "approval_threshold", "monetary_value", ">=", "10000", "USD", "ESCALATE",
                "Transaction exceeds $10,000 — Finance Manager approval required.",
                0.80, "finance_manager",
            ),
        ],
    },
    {
        "file_name":   "hr_policy.md",
        "title":       "HR Escalation Policy",
        "policy_type": "hr_escalation",
        "department":  "human_resources",
        "source":      "data/policies/hr_policy.md",
        "rules": [
            (
                "case_type_requirement", "task_type", "==", "hr_escalation", None, "ESCALATE",
                "All HR escalation cases require HR Director and Legal Counsel review before any action is taken.",
                0.92, "hr_director",
            ),
        ],
    },
    {
        "file_name":   "claim_processing.md",
        "title":       "Claim Processing Policy",
        "policy_type": "claim_processing",
        "department":  "claims",
        "source":      "data/policies/claim_processing.md",
        "rules": [
            (
                "approval_threshold", "monetary_value", ">", "10000", "USD", "ESCALATE",
                "Claim amount exceeds $10,000 — Claims Director review required.",
                0.90, "claims_director",
            ),
            (
                "approval_threshold", "monetary_value", ">", "5000", "USD", "ESCALATE",
                "Claim amount exceeds $5,000 — Risk Committee review required.",
                0.85, "risk_committee",
            ),
        ],
    },
    {
        "file_name":   "document_review.md",
        "title":       "Document Review Policy",
        "policy_type": "document_review",
        "department":  "legal",
        "source":      "data/policies/document_review.md",
        "rules": [
            (
                "approval_threshold", "monetary_value", ">", "20000", "USD", "ESCALATE",
                "Document review scope exceeds $20,000 — General Counsel approval required.",
                0.90, "general_counsel",
            ),
            (
                "approval_threshold", "monetary_value", ">", "5000", "USD", "ESCALATE",
                "Document review scope exceeds $5,000 — Legal Counsel review required.",
                0.82, "legal_counsel",
            ),
        ],
    },
    {
        "file_name":   "interview_scheduling.md",
        "title":       "Interview Scheduling & Approval Policy",
        "policy_type": "interview_scheduling",
        "department":  "human_resources",
        "source":      "data/policies/interview_scheduling.md",
        "rules": [
            # monetary_value here represents the role's annual total compensation —
            # the orchestrator passes it through as part of task_intake metadata.
            (
                "approval_threshold", "monetary_value", ">=", "350000", "USD", "ESCALATE",
                "Executive hire (annual comp >= $350,000) — CEO sign-off required.",
                0.95, "ceo",
            ),
            (
                "approval_threshold", "monetary_value", ">=", "200000", "USD", "ESCALATE",
                "Senior hire (annual comp >= $200,000) — CHRO and CFO approval required.",
                0.90, "chro",
            ),
            (
                "approval_threshold", "monetary_value", ">=", "150000", "USD", "ESCALATE",
                "Senior hire (annual comp >= $150,000) — CHRO approval required.",
                0.85, "chro",
            ),
            (
                "approval_threshold", "monetary_value", ">=", "100000", "USD", "ESCALATE",
                "Mid-level hire (annual comp >= $100,000) — Recruiting Director approval required.",
                0.80, "recruiting_director",
            ),
            (
                "case_type_requirement", "task_type", "==", "interview_scheduling", None, "ESCALATE",
                "Interview scheduling cases require recruiting team review and structured-panel sign-off before offer extension.",
                0.75, "recruiting_manager",
            ),
        ],
    },
]


def seed_gpa_policies() -> None:
    """
    Insert policy documents, chunks, and rules into the GPA SQLite DB.
    Idempotent — skips any document whose file_name already exists.
    """
    # Import GPA ORM inside the function so this module is safe to import
    # from infra/ without triggering GPA's FastAPI startup side-effects.
    from GPA.db import SessionLocal, engine, Base
    from GPA.models import PolicyDocument, PolicyChunk, PolicyRule
    from GPA.chunker import chunk_text

    # Ensure tables exist (GPA app normally does this on startup).
    Base.metadata.create_all(bind=engine)

    policies_root = ROOT / "data" / "policies"
    db = SessionLocal()

    try:
        for policy in _POLICIES:
            file_name = policy["file_name"]

            # INSERT OR IGNORE semantics — skip if already seeded
            existing = db.query(PolicyDocument).filter_by(file_name=file_name).first()
            if existing:
                logger.info("  GPA seed: %s already exists — skipped", file_name)
                continue

            # Read markdown text
            md_path = policies_root / file_name
            if not md_path.exists():
                logger.warning("  GPA seed: %s not found at %s — skipped", file_name, md_path)
                continue
            text = md_path.read_text(encoding="utf-8")

            # Insert PolicyDocument (no file_data — text is stored in chunks)
            doc = PolicyDocument(
                file_name=file_name,
                title=policy["title"],
                policy_type=policy["policy_type"],
                department=policy["department"],
                version="v1",
                file_path=str(md_path),
                source=policy["source"],
                processing_status="PROCESSED",
            )
            db.add(doc)
            db.flush()  # get doc.id without committing

            # Chunk the text and insert PolicyChunk rows
            chunks = chunk_text(text)
            chunk_objs: list[PolicyChunk] = []
            for idx, chunk_text_val in enumerate(chunks):
                c = PolicyChunk(
                    document_id=doc.id,
                    chunk_index=idx,
                    chunk_text=chunk_text_val,
                    section_name=None,
                )
                db.add(c)
                chunk_objs.append(c)
            db.flush()  # get chunk IDs

            # Use first chunk as the anchor for all rules (rules reference chunks,
            # not the full document; first chunk captures the purpose section).
            anchor_chunk = chunk_objs[0] if chunk_objs else None
            if anchor_chunk is None:
                logger.warning("  GPA seed: %s produced no chunks — rules skipped", file_name)
                db.commit()
                continue

            # Insert PolicyRule rows
            rules_inserted = 0
            seen_keys: set[tuple] = set()
            for (
                rule_type, subject, operator, value, unit,
                action, condition_text, confidence, approver,
            ) in policy["rules"]:
                dedup_key = (doc.id, anchor_chunk.id, subject, operator, value, action)
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                db.add(PolicyRule(
                    document_id=doc.id,
                    chunk_id=anchor_chunk.id,
                    rule_type=rule_type,
                    subject=subject,
                    operator=operator,
                    value=value,
                    unit=unit,
                    action=action,
                    condition_text=condition_text,
                    confidence=confidence,
                    approver=approver,
                ))
                rules_inserted += 1

            db.commit()
            logger.info(
                "  GPA seed: %s → %d chunks, %d rules (policy_type=%s)",
                file_name, len(chunks), rules_inserted, policy["policy_type"],
            )

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_gpa_policies()
