import uuid, json, os
from datetime import datetime
from core.db_schema import get_connection
from core.retrieval_engine import fetch_context, validate_context

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../data/outputs")

def stitch_structured(case_id, case_type, task_query="", source_types=None):
    run_id    = _make_run_id()
    timestamp = _now()
    context    = fetch_context(case_id, case_type, source_types)
    validation = validate_context(context)
    packet = {
        "task_id":   run_id,
        "task_text": task_query or f"Context fetch for {case_id} ({case_type})",
        "case_id":   case_id,
        "case_type": case_type,
        "timestamp": timestamp,
        "context": {
            "emails":          context.get("emails",[]),
            "documents":       context.get("documents",[]),
            "calendar_events": context.get("calendar_events",[]),
            "case_history":    context.get("case_history",[]),
        },
        "validation": validation,
        "meta": {
            "total_sources":    validation["total_sources"],
            "sql_hits":         validation["total_sources"],
            "qdrant_hits":      0,
            "keywords_used":    [],
            "retrieval_method": "exact_match_sql",
        }
    }
    _save_and_log(packet, run_id, case_id, case_type, task_query, timestamp, validation)
    return packet

def stitch(task_text, top_k=5):
    from core.hybrid_retriever import hybrid_fetch
    run_id    = _make_run_id()
    timestamp = _now()
    hybrid    = hybrid_fetch(task_text, top_k=top_k)
    results   = hybrid["results"]
    meta      = hybrid["meta"]
    validation = validate_context(results)
    packet = {
        "task_id":   run_id,
        "task_text": task_text,
        "case_id":   meta.get("case_id"),
        "case_type": meta.get("case_type"),
        "timestamp": timestamp,
        "context": {
            "emails":          results.get("emails",[]),
            "documents":       results.get("documents",[]),
            "calendar_events": results.get("calendar_events",[]),
            "case_history":    results.get("case_history",[]),
        },
        "validation": validation,
        "meta": {
            "total_sources":    validation["total_sources"],
            "sql_hits":         meta.get("sql_hits",0),
            "qdrant_hits":      meta.get("qdrant_hits",0),
            "keywords_used":    meta.get("keywords",[]),
            "retrieval_method": "hybrid_sql_qdrant",
        }
    }
    _save_and_log(packet, run_id, meta.get("case_id"), meta.get("case_type"),
                  task_text, timestamp, validation)
    return packet

def _make_run_id():
    return f"CSA-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:6].upper()}"

def _now():
    return datetime.utcnow().isoformat() + "Z"

def _save_and_log(packet, run_id, case_id, case_type, task_query, timestamp, validation):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"{run_id}.json")
    with open(output_path, "w") as f:
        json.dump(packet, f, indent=2)
    try:
        conn = get_connection()
        conn.execute("""INSERT INTO query_runs
            (run_id,case_id,case_type,task_query,timestamp,output_path,total_sources,confidence)
            VALUES (?,?,?,?,?,?,?,?)""",
            (run_id,case_id,case_type,task_query,timestamp,output_path,
             validation["total_sources"],validation["confidence_score"]))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"[warn] {e}")

def get_output_history():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM query_runs ORDER BY timestamp DESC")
        rows = [dict(r) for r in c.fetchall()]
        conn.close(); return rows
    except Exception: return []

def load_output(run_id):
    path = os.path.join(OUTPUT_DIR, f"{run_id}.json")
    if os.path.exists(path):
        with open(path) as f: return json.load(f)
    return {}