from fastapi import APIRouter, Query
from core.retrieval_engine import get_all_records
from core.db_schema import get_all_case_ids, get_connection

router = APIRouter()

@router.get("/records/emails")
def list_emails(case_id: str=Query(None), case_type: str=Query(None)):
    rows = get_all_records("emails")
    if case_id:   rows = [r for r in rows if r["case_id"]==case_id]
    if case_type: rows = [r for r in rows if r["case_type"]==case_type]
    return {"count":len(rows),"records":rows}

@router.get("/records/documents")
def list_documents(case_id: str=Query(None), case_type: str=Query(None)):
    rows = get_all_records("documents")
    if case_id:   rows = [r for r in rows if r["case_id"]==case_id]
    if case_type: rows = [r for r in rows if r["case_type"]==case_type]
    return {"count":len(rows),"records":rows}

@router.get("/records/calendar_events")
def list_events(case_id: str=Query(None)):
    rows = get_all_records("calendar_events")
    if case_id: rows = [r for r in rows if r["case_id"]==case_id]
    return {"count":len(rows),"records":rows}

@router.get("/records/case_history")
def list_history(case_id: str=Query(None), status: str=Query(None)):
    rows = get_all_records("case_history")
    if case_id: rows = [r for r in rows if r["case_id"]==case_id]
    if status:  rows = [r for r in rows if r["status"]==status]
    return {"count":len(rows),"records":rows}

@router.get("/cases")
def list_cases(): return get_all_case_ids()

@router.get("/health")
def health():
    conn = get_connection()
    counts = {}
    for t in ["emails","documents","calendar_events","case_history","query_runs"]:
        c = conn.cursor(); c.execute(f"SELECT COUNT(*) FROM {t}")
        counts[t] = c.fetchone()[0]
    conn.close()
    return {"status":"ok","version":"2.0.0","db_records":counts}