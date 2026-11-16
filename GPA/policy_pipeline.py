from sqlalchemy.orm import Session
from .models import PolicyDocument, PolicyChunk, PolicyRule
from .document_processor import extract_text_from_document
from .chunker import chunk_text
from .rule_extractor import extract_rules_from_chunk


def process_policy_document(db: Session, document_id: int):
    document = db.query(PolicyDocument).filter(PolicyDocument.id == document_id).first()
    if not document:
        raise ValueError(f"Policy document {document_id} not found")

    text = extract_text_from_document(document)
    if not text or not text.strip():
        raise ValueError("No extractable text found in the policy document")

    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("Chunking failed because extracted text was empty")

    # Remove existing rules and chunks for reprocessing
    db.query(PolicyRule).filter(PolicyRule.document_id == document.id).delete()
    db.query(PolicyChunk).filter(PolicyChunk.document_id == document.id).delete()
    db.commit()

    # Insert chunks
    for idx, chunk in enumerate(chunks):
        db.add(
            PolicyChunk(
                document_id=document.id,
                chunk_index=idx,
                chunk_text=chunk,
                section_name=None
            )
        )
    db.commit()

    stored_chunks = (
        db.query(PolicyChunk)
        .filter(PolicyChunk.document_id == document.id)
        .order_by(PolicyChunk.chunk_index.asc())
        .all()
    )

    rules_created = 0

    for chunk_row in stored_chunks:
        extracted_rules = extract_rules_from_chunk(chunk_row.chunk_text)

        # Deduplicate rules based on the same fields used by DB unique constraint
        seen = set()

        for rule in extracted_rules:
            dedupe_key = (
                document.id,
                chunk_row.id,
                rule.get("subject"),
                rule.get("operator"),
                rule.get("value"),
                rule.get("action"),
            )

            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            db.add(
                PolicyRule(
                    document_id=document.id,
                    chunk_id=chunk_row.id,
                    rule_type=rule["rule_type"],
                    subject=rule["subject"],
                    operator=rule["operator"],
                    value=rule["value"],
                    unit=rule["unit"],
                    action=rule["action"],
                    condition_text=rule["condition_text"],
                    confidence=rule["confidence"],
                    approver=rule.get("approver")
                )
            )
            rules_created += 1

    db.commit()

    document.processing_status = "PROCESSED"
    db.commit()

    return {
        "document_id": document.id,
        "file_name": document.file_name,
        "chunks_created": len(stored_chunks),
        "rules_created": rules_created,
        "status": document.processing_status
    }