"""Flask UI server for Shadow Work Agent v3."""
import json
from flask import Flask, jsonify, render_template
from db.db import get_connection, _loads
from config.settings import settings

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


# ── LLM STATUS ────────────────────────────────────────────────────

@app.route("/api/llm-status")
def llm_status():
    key = settings.GEMINI_API_KEY or ""
    model = settings.GEMINI_MODEL

    if not key or key.strip() in ("", "<your-key>", "your-key-here"):
        return jsonify({
            "status": "no_key", "label": "No API key set", "model": model,
            "detail": "Set GEMINI_API_KEY in your .env file to enable LLM enrichment.",
        })
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        client = genai.GenerativeModel(model)
        resp = client.generate_content("Reply with the single word: ok")
        return jsonify({
            "status": "active", "label": "LLM active", "model": model,
            "detail": f"Gemini ({model}) is reachable and responding.",
        })
    except Exception as e:
        err = str(e)
        if "API_KEY_INVALID" in err or "invalid" in err.lower():
            label, detail = "Invalid API key", "Key rejected by Gemini. Check GEMINI_API_KEY."
        elif "quota" in err.lower() or "429" in err:
            label, detail = "Quota exceeded", "Key valid but rate-limited."
        else:
            label, detail = "LLM unreachable", f"Error: {err[:120]}"
        return jsonify({"status": "error", "label": label, "model": model, "detail": detail})


# ── DOMAINS ───────────────────────────────────────────────────────

@app.route("/api/domains")
def get_domains():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT case_type, COUNT(*) AS case_count
            FROM cases GROUP BY case_type ORDER BY case_type
        """).fetchall()
    return jsonify([{"domain": r["case_type"], "count": r["case_count"]} for r in rows])


# ── CASES ─────────────────────────────────────────────────────────

@app.route("/api/cases/<domain>")
def get_cases(domain):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.case_id, c.status, c.created_at, c.closed_at,
                   COUNT(a.event_id) AS event_count
            FROM cases c
            LEFT JOIN activity_log a ON a.case_id = c.case_id
            WHERE c.case_type = ?
            GROUP BY c.case_id, c.status, c.created_at, c.closed_at
            ORDER BY c.created_at DESC
        """, (domain,)).fetchall()
    return jsonify([
        {
            "case_id": r["case_id"],
            "status": r["status"],
            "created_at": r["created_at"],
            "closed_at": r["closed_at"],
            "event_count": r["event_count"],
        }
        for r in rows
    ])


# ── CASE DETAIL ───────────────────────────────────────────────────

@app.route("/api/case/<case_id>")
def get_case_detail(case_id):
    with get_connection() as conn:
        case = conn.execute(
            "SELECT * FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if not case:
            return jsonify({"error": "Case not found"}), 404

        events = conn.execute("""
            SELECT event_id, timestamp, actor_id, actor_type,
                   action_type, target_entity, target_entity_type,
                   outcome, context_payload
            FROM activity_log WHERE case_id = ? ORDER BY timestamp ASC
        """, (case_id,)).fetchall()

        outcome_rows = conn.execute("""
            SELECT outcome, COUNT(*) AS cnt
            FROM activity_log WHERE case_id = ? GROUP BY outcome
        """, (case_id,)).fetchall()

    outcome_counts = {r["outcome"]: r["cnt"] for r in outcome_rows}

    events_list = [
        {
            "event_id": e["event_id"],
            "timestamp": e["timestamp"],
            "actor_id": e["actor_id"],
            "actor_type": e["actor_type"],
            "action_type": e["action_type"],
            "target_entity": e["target_entity"],
            "target_entity_type": e["target_entity_type"],
            "outcome": e["outcome"],
            "context_payload": _loads(e["context_payload"]),
        }
        for e in events
    ]

    return jsonify({
        "case": {
            "case_id": case["case_id"],
            "case_type": case["case_type"],
            "status": case["status"],
            "created_at": case["created_at"],
            "closed_at": case["closed_at"],
            "domain_metadata": _loads(case["domain_metadata"]),
        },
        "outcome_summary": {
            "success": outcome_counts.get("success", 0),
            "pending": outcome_counts.get("pending", 0),
            "failed": outcome_counts.get("failed", 0),
        },
        "events": events_list,
    })


# ── ANALYSIS ──────────────────────────────────────────────────────

def _consolidate_findings(findings):
    if not findings:
        return None
    decision_rank = {"escalate": 2, "watch": 1, "recommend": 0}
    final_decision = max(findings, key=lambda f: decision_rank.get(f.get("decision", "recommend"), 0))["decision"]
    confidences = [f.get("confidence", 0) for f in findings]
    base_confidence = sum(confidences) / len(confidences)
    boost = min(0.03 * (len(findings) - 1), 0.10)
    aggregate_confidence = round(min(base_confidence + boost, 0.99), 3)
    risk_rank = {"high": 2, "medium": 1, "low": 0}
    risk_level = max(findings, key=lambda f: risk_rank.get(f.get("risk_level", "low"), 0))["risk_level"]
    best_ar, best_hours = None, -1
    for f in findings:
        ar = f.get("automation_recommendation") or {}
        h = ar.get("estimated_time_saved_per_week_hours") or 0
        if h > best_hours:
            best_hours, best_ar = h, ar
    ts_list = [f["temporal_signature"] for f in findings if f.get("temporal_signature")]
    agg_ts = None
    if ts_list:
        agg_ts = {
            "mean_interval_hours": round(sum(t["mean_interval_hours"] for t in ts_list) / len(ts_list), 1),
            "regularity_score": round(sum(t["regularity_score"] for t in ts_list) / len(ts_list), 3),
        }
    return {
        "decision": final_decision,
        "aggregate_confidence": aggregate_confidence,
        "pattern_count": len(findings),
        "risk_level": risk_level,
        "total_occurrences": sum(f.get("occurrences", 0) for f in findings),
        "actors_involved": sorted({a for f in findings for a in f.get("actors_involved", [])}),
        "requires_human_approval": any(f.get("requires_human_approval") for f in findings),
        "temporal_signature": agg_ts,
        "automation_recommendation": best_ar,
        "patterns": [
            {"signature": f.get("pattern_signature"), "detector": f.get("detector_source"),
             "confidence": f.get("confidence"), "occurrences": f.get("occurrences")}
            for f in findings
        ],
    }


def _consolidate_escalations(escalations):
    if not escalations:
        return None
    return {
        "pattern_count": len(escalations),
        "total_occurrences": sum(e.get("occurrences", 0) for e in escalations),
        "evidence_count": len({ev for e in escalations for ev in e.get("evidence_event_ids", [])}),
        "recommended_human_roles": sorted({e.get("recommended_human_role") for e in escalations if e.get("recommended_human_role")}),
        "reasons": list({e.get("reason") for e in escalations if e.get("reason")}),
        "summaries": [e.get("summary_for_human") for e in escalations if e.get("summary_for_human")],
        "patterns": [
            {"signature": e.get("pattern_signature"), "occurrences": e.get("occurrences"), "reason": e.get("reason")}
            for e in escalations
        ],
    }


@app.route("/api/case/<case_id>/analysis")
def get_case_analysis(case_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT output_json FROM analysis_runs ORDER BY run_timestamp DESC LIMIT 1"
        ).fetchone()

    if not row:
        return jsonify({"recommendation": None, "escalation": None})

    data = _loads(row["output_json"])

    with get_connection() as conn:
        eid_rows = conn.execute(
            "SELECT event_id FROM activity_log WHERE case_id = ?", (case_id,)
        ).fetchall()
    case_event_ids = {r["event_id"] for r in eid_rows}

    findings = [
        f for f in data.get("findings", [])
        if case_id in f.get("cases_involved", [])
        or bool(set(f.get("evidence_event_ids", [])) & case_event_ids)
    ]
    escalations = [
        e for e in data.get("escalations", [])
        if bool(set(e.get("evidence_event_ids", [])) & case_event_ids)
    ]

    return jsonify({
        "recommendation": _consolidate_findings(findings),
        "escalation": _consolidate_escalations(escalations),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5050)
