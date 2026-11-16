import os
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from .config import UPLOAD_DIR
from .db import Base, engine, get_db
from .models import PolicyDocument, PolicyChunk, PolicyRule, IncomingTask, GovernanceDecision
from .schemas import TaskInput
from .policy_pipeline import process_policy_document
from .decision_engine import run_governance_decision

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Governance & Policy Agent")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def health():
    return {"status": "ok", "service": "governance_policy_agent"}


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "governance_policy_agent"}


@app.post("/dev/upload-policy")
async def dev_upload_policy(
    file: UploadFile = File(...),
    policy_type: str = "general_policy",
    department: str = "general",
    version: str = "v1",
    db: Session = Depends(get_db)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()

    document = PolicyDocument(
        file_name=file.filename,
        title=file.filename,
        policy_type=policy_type,
        department=department,
        version=version,
        file_data=file_bytes,
        source="dev_upload",
        processing_status="NEW"
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return {
        "document_id": document.id,
        "file_name": document.file_name,
        "status": document.processing_status
    }


@app.post("/process-policy/{document_id}")
def process_one_policy(document_id: int, db: Session = Depends(get_db)):
    document = db.query(PolicyDocument).filter(PolicyDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Policy document not found")

    try:
        return process_policy_document(db, document_id)
    except Exception as exc:
        document.processing_status = "FAILED"
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/evaluate-task")
def evaluate_task(task: TaskInput, db: Session = Depends(get_db)):
    try:
        existing = db.query(IncomingTask).filter(
            IncomingTask.task_id == task.task_id
        ).first()

        if existing:
            existing.task_type = task.task_type
            existing.payload   = task.model_dump()
            db.commit()
        else:
            db.add(IncomingTask(
                task_id=task.task_id,
                task_type=task.task_type,
                payload=task.model_dump()
            ))
            db.commit()

        decision_payload = run_governance_decision(db, task.model_dump())

        db.add(
            GovernanceDecision(
                task_id=decision_payload["task_id"],
                decision=decision_payload["decision"],
                reason=decision_payload.get("reason", ""),
                confidence=decision_payload["confidence"],
                requires_approval=decision_payload["requires_approval"],
                next_agent=decision_payload["next_agent"],
                matched_rule_ids=decision_payload.get("matched_rule_ids", []),
                matched_chunk_ids=decision_payload.get("matched_chunk_ids", []),
                decision_payload=decision_payload
            )
        )

        db.commit()

        return decision_payload  # 👈 IMPORTANT

    except Exception as e:
        print("🔥 ERROR:", str(e))   # 👈 THIS WILL SHOW IN TERMINAL
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(PolicyDocument).all()
    return [
        {
            "id": d.id,
            "file_name": d.file_name,
            "title": d.title,
            "policy_type": d.policy_type,
            "department": d.department,
            "version": d.version,
            "source": d.source,
            "processing_status": d.processing_status
        }
        for d in docs
    ]


@app.get("/chunks/{document_id}")
def list_chunks(document_id: int, db: Session = Depends(get_db)):
    chunks = db.query(PolicyChunk).filter(PolicyChunk.document_id == document_id).all()
    return [
        {
            "id": c.id,
            "chunk_index": c.chunk_index,
            "chunk_text": c.chunk_text
        }
        for c in chunks
    ]


@app.get("/rules/{document_id}")
def list_rules(document_id: int, db: Session = Depends(get_db)):
    rules = db.query(PolicyRule).filter(PolicyRule.document_id == document_id).all()
    return [
        {
            "id": r.id,
            "rule_type": r.rule_type,
            "subject": r.subject,
            "operator": r.operator,
            "value": r.value,
            "unit": r.unit,
            "action": r.action,
            "condition_text": r.condition_text,
            "confidence": r.confidence
        }
        for r in rules
    ]


@app.get("/decisions")
def list_decisions(db: Session = Depends(get_db)):
    decisions = db.query(GovernanceDecision).all()
    return [
        {
            "id": d.id,
            "task_id": d.task_id,
            "decision": d.decision,
            "reason": d.reason,
            "confidence": d.confidence,
            "requires_approval": d.requires_approval,
            "next_agent": d.next_agent,
            "matched_rule_ids": d.matched_rule_ids,
            "matched_chunk_ids": d.matched_chunk_ids
        }
        for d in decisions
    ]