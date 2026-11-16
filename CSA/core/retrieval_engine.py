from core.db_schema import get_connection

def fetch_context(case_id, case_type, source_types=None):
    if source_types is None:
        source_types = ["emails","documents","calendar_events","case_history"]
    conn = get_connection()
    result = {}
    if "emails"          in source_types: result["emails"]          = _fetch_emails(conn, case_id, case_type)
    if "documents"       in source_types: result["documents"]       = _fetch_documents(conn, case_id, case_type)
    if "calendar_events" in source_types: result["calendar_events"] = _fetch_events(conn, case_id, case_type)
    if "case_history"    in source_types: result["case_history"]    = _fetch_history(conn, case_id, case_type)
    conn.close()
    return result

def _fetch_emails(conn, case_id, case_type):
    c = conn.cursor()
    c.execute("SELECT * FROM emails WHERE case_id=? AND case_type=? ORDER BY date ASC", (case_id, case_type))
    return [_email_to_dict(r) for r in c.fetchall()]

def _fetch_documents(conn, case_id, case_type):
    c = conn.cursor()
    c.execute("SELECT * FROM documents WHERE case_id=? AND case_type=? ORDER BY created_at ASC", (case_id, case_type))
    return [_doc_to_dict(r) for r in c.fetchall()]

def _fetch_events(conn, case_id, case_type):
    c = conn.cursor()
    c.execute("SELECT * FROM calendar_events WHERE case_id=? AND case_type=? ORDER BY start_time ASC", (case_id, case_type))
    return [_event_to_dict(r) for r in c.fetchall()]

def _fetch_history(conn, case_id, case_type):
    c = conn.cursor()
    c.execute("SELECT * FROM case_history WHERE case_id=? AND case_type=? ORDER BY timestamp ASC", (case_id, case_type))
    return [dict(r) for r in c.fetchall()]

def _email_to_dict(row):
    d = dict(row)
    d["file_link"] = f"file:///{d['file_path'].lstrip('/')}" if d.get("file_path") else None
    att = d.get("attachments", "")
    if isinstance(att, list):
        d["attachments"] = att
    elif isinstance(att, str) and att.strip():
        d["attachments"] = [a.strip() for a in att.split(",") if a.strip()]
    else:
        d["attachments"] = []
    return d

def _doc_to_dict(row):
    d = dict(row)
    d["file_link"] = f"file:///{d['file_path'].lstrip('/')}" if d.get("file_path") else None
    d["tags"] = [t.strip() for t in d["tags"].split(",") if t.strip()] if d.get("tags") else []
    return d

def _event_to_dict(row):
    d = dict(row)
    d["attendees"] = [a.strip() for a in d["attendees"].split(",") if a.strip()] if d.get("attendees") else []
    return d

def get_all_records(source_type):
    conn = get_connection()
    c = conn.cursor()
    table_map = {"emails":"emails","documents":"documents",
                 "calendar_events":"calendar_events","case_history":"case_history"}
    table = table_map.get(source_type)
    if not table:
        conn.close(); return []
    c.execute(f"SELECT * FROM {table} ORDER BY case_id")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for r in rows:
        if r.get("file_path"):
            r["file_link"] = f"file:///{r['file_path'].lstrip('/')}"
    return rows

def validate_context(context):
    warnings, missing, total = [], [], 0
    for source, records in context.items():
        total += len(records)
        if len(records) == 0:
            missing.append(source)
            warnings.append(f"No {source.replace('_',' ')} found for this case.")
    for doc in context.get("documents", []):
        if not doc.get("file_path"):
            warnings.append(f"Document '{doc.get('filename')}' has no file path.")

    if total == 0:
        confidence = 0.0
        status = "EMPTY"
    else:
        confidence = round(1.0 - (len(missing)/max(len(context),1))*0.25, 2)
        status = "COMPLETE" if not missing else "PARTIAL" if len(missing)<len(context) else "EMPTY"

    return {"status":status,"missing_fields":missing,"warnings":warnings,
            "confidence_score":confidence,"total_sources":total}