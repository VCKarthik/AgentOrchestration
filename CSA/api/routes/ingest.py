import os, uuid, shutil
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from core.db_schema import get_connection

router = APIRouter()
UPLOAD_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/files"))

class EmailIn(BaseModel):
    case_id: str; case_type: str; subject: str; sender: str
    recipients: str; date: str; body: str
    attachments: Optional[str]=""; thread_id: Optional[str]=""; file_path: Optional[str]=""

class DocumentIn(BaseModel):
    case_id: str; case_type: str; filename: str; file_type: str; file_path: str
    description: Optional[str]=""; tags: Optional[str]=""; created_at: Optional[str]=""

class EventIn(BaseModel):
    case_id: str; case_type: str; title: str; start_time: str; end_time: str
    attendees: Optional[str]=""; location: Optional[str]=""
    description: Optional[str]=""; status: Optional[str]="confirmed"

class CaseIn(BaseModel):
    case_id: str; case_type: str; event_type: str
    actor: str; timestamp: str; notes: str; status: str

def _ok(rid, msg): return {"success":True,"id":rid,"message":msg}

@router.post("/ingest/email")
def ingest_email(req: EmailIn):
    rid = f"E{str(uuid.uuid4())[:6].upper()}"
    try:
        conn = get_connection()
        conn.execute("""INSERT INTO emails
            (id,case_id,case_type,subject,sender,recipients,date,body,attachments,thread_id,file_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (rid,req.case_id,req.case_type,req.subject,req.sender,req.recipients,
             req.date,req.body,req.attachments,req.thread_id,req.file_path))
        conn.commit(); conn.close()
        return _ok(rid,"Email ingested.")
    except Exception as e: raise HTTPException(500,detail=str(e))

@router.post("/ingest/document")
def ingest_document(req: DocumentIn):
    rid = f"D{str(uuid.uuid4())[:6].upper()}"
    try:
        conn = get_connection()
        conn.execute("""INSERT INTO documents
            (id,case_id,case_type,filename,file_type,description,tags,created_at,file_path)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (rid,req.case_id,req.case_type,req.filename,req.file_type,
             req.description,req.tags,req.created_at,req.file_path))
        conn.commit(); conn.close()
        return _ok(rid,"Document ingested.")
    except Exception as e: raise HTTPException(500,detail=str(e))

@router.post("/ingest/calendar")
def ingest_calendar(req: EventIn):
    rid = f"EV{str(uuid.uuid4())[:6].upper()}"
    try:
        conn = get_connection()
        conn.execute("""INSERT INTO calendar_events
            (id,case_id,case_type,title,start_time,end_time,attendees,location,description,status)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (rid,req.case_id,req.case_type,req.title,req.start_time,req.end_time,
             req.attendees,req.location,req.description,req.status))
        conn.commit(); conn.close()
        return _ok(rid,"Event ingested.")
    except Exception as e: raise HTTPException(500,detail=str(e))

@router.post("/ingest/case")
def ingest_case(req: CaseIn):
    rid = f"H{str(uuid.uuid4())[:6].upper()}"
    try:
        conn = get_connection()
        conn.execute("""INSERT INTO case_history
            (id,case_id,case_type,event_type,actor,timestamp,notes,status)
            VALUES (?,?,?,?,?,?,?,?)""",
            (rid,req.case_id,req.case_type,req.event_type,
             req.actor,req.timestamp,req.notes,req.status))
        conn.commit(); conn.close()
        return _ok(rid,"Case history ingested.")
    except Exception as e: raise HTTPException(500,detail=str(e))

@router.post("/ingest/upload/{case_id}/{case_type}")
async def upload_file(case_id: str, case_type: str, file: UploadFile = File(...)):
    try:
        dest_dir  = os.path.join(UPLOAD_BASE,"documents")
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, file.filename)
        with open(dest_path,"wb") as f: shutil.copyfileobj(file.file, f)
        ext = file.filename.rsplit(".",1)[-1].lower() if "." in file.filename else "unknown"
        rid = f"D{str(uuid.uuid4())[:6].upper()}"
        conn = get_connection()
        conn.execute("""INSERT INTO documents
            (id,case_id,case_type,filename,file_type,description,tags,created_at,file_path)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (rid,case_id,case_type,file.filename,ext,
             f"Uploaded: {file.filename}","",datetime.utcnow().strftime("%Y-%m-%d"),dest_path))
        conn.commit(); conn.close()
        return _ok(rid,f"Saved to {dest_path}.")
    except Exception as e: raise HTTPException(500,detail=str(e))