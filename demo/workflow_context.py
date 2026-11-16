"""
Workflow-context upload panel for the Streamlit demo sidebar.

The presenter uploads a JSON file describing past cases for one workflow
domain (vendor onboarding, claim review, interview scheduling). The cases
and events are ingested into the SWA SQLite DB and used as backdrop when
SWA's analyze() is triggered for a new case in the same domain.

Schema (matches SWA IncomingCase + IncomingEvent exactly):

    {
      "metadata": { "domain": "vendor_onboarding", "description": "..." },
      "cases":  [ IncomingCase, ... ],
      "events": [ IncomingEvent, ... ]
    }

Sample files live in `data/workflow_contexts/`. Generate them with
`python3 SWA/data/export_workflow_contexts.py`.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import streamlit as st

# ── Make SWA imports work ─────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SWA_ROOT = os.path.join(_REPO_ROOT, "SWA")
for p in (_SWA_ROOT, _REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


def _ingest_payload(payload: dict[str, Any]) -> tuple[bool, str, dict]:
    """
    Validate the JSON payload and push cases + events into the SWA DB.
    Returns (ok, message, stats).
    """
    if not isinstance(payload, dict):
        return False, "Top level must be a JSON object.", {}
    if "cases" not in payload or "events" not in payload:
        return False, "JSON must contain `cases` and `events` arrays.", {}
    if not isinstance(payload["cases"], list) or not isinstance(payload["events"], list):
        return False, "`cases` and `events` must both be arrays.", {}

    metadata = payload.get("metadata") or {}
    domain = metadata.get("domain") or "unknown"

    # Lazy import — keeps the demo importable even if SWA's deps fail
    try:
        from agent.logging_tool import ingest_case, ingest_batch  # type: ignore[import]
    except Exception as e:
        return False, f"SWA import failed: {e}", {}

    cases_added = 0
    cases_failed = 0
    new_case_ids: list[str] = []
    for case in payload["cases"]:
        if not isinstance(case, dict):
            cases_failed += 1
            continue
        if ingest_case(case):
            cases_added += 1
            cid = case.get("case_id")
            if cid:
                new_case_ids.append(cid)
        else:
            cases_failed += 1

    batch_result = ingest_batch(payload["events"], source_agent="demo_context_upload")
    events_accepted = batch_result.get("accepted", 0)
    events_rejected = batch_result.get("rejected", 0)

    # Track uploaded IDs so we can wipe just these later.
    upload_log = st.session_state.setdefault("uploaded_case_ids", {})
    upload_log.setdefault(domain, set()).update(new_case_ids)

    stats = {
        "domain":           domain,
        "cases_added":      cases_added,
        "cases_failed":     cases_failed,
        "events_accepted":  events_accepted,
        "events_rejected":  events_rejected,
    }
    msg = (
        f"Loaded **{cases_added}** cases / **{events_accepted}** events for "
        f"`{domain}`."
    )
    if cases_failed or events_rejected:
        msg += f"  ⚠ rejected: {cases_failed} cases, {events_rejected} events."
    return True, msg, stats


def _summarize_swa_db() -> list[tuple[str, int, int]]:
    """Return [(case_type, n_cases, n_events), ...] from the SWA SQLite DB."""
    try:
        from db import db  # type: ignore[import]
    except Exception:
        return []

    try:
        with db.get_connection() as conn:
            rows = conn.execute("""
                SELECT c.case_type,
                       COUNT(DISTINCT c.case_id) AS n_cases,
                       COUNT(a.event_id)         AS n_events
                FROM cases AS c
                LEFT JOIN activity_log AS a ON a.case_id = c.case_id
                GROUP BY c.case_type
                ORDER BY n_cases DESC
            """).fetchall()
        return [(r["case_type"], r["n_cases"], r["n_events"]) for r in rows]
    except Exception:
        return []


def _reset_swa_db() -> dict[str, int]:
    """
    Full reset of the SWA database — back to a fresh-install state.

    Wipes BOTH source data (cases + activity_log) AND derived analysis state
    (analysis_runs, cluster_snapshots, case_portfolios, ingestion_log). Without
    clearing the derived tables, stale findings/escalations from previous runs
    keep showing up in the Observatory even after upstream data is gone.

    Schema is preserved. Returns per-table row counts that were deleted.
    """
    try:
        from db import db  # type: ignore[import]
    except Exception:
        return {}

    tables = [
        # Order matters only if FKs exist; current schema has none, but we
        # delete derived first then source for clarity.
        "ingestion_log",
        "case_portfolios",
        "cluster_snapshots",
        "analysis_runs",
        "activity_log",
        "cases",
    ]
    counts: dict[str, int] = {}
    with db.get_connection() as conn:
        for t in tables:
            try:
                counts[t] = conn.execute(f"DELETE FROM {t}").rowcount
            except Exception:
                counts[t] = 0
        conn.commit()

    # Clear session-state tracking so the uploader re-accepts the same files.
    st.session_state["uploaded_case_ids"] = {}
    st.session_state["ctx_loaded_files"] = set()
    return counts


# ── Public renderer ──────────────────────────────────────────────────────────

def render_sidebar_panel() -> None:
    """
    Render the workflow-context upload panel. Call inside a sidebar block.
    """
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Workflow Context")
    st.sidebar.caption(
        "Upload past cases as backdrop. SWA uses this when running a workflow "
        "in the same domain."
    )

    sample_path = os.path.join(_REPO_ROOT, "data", "workflow_contexts")
    if os.path.isdir(sample_path):
        with st.sidebar.expander("Sample files"):
            samples = sorted(
                f for f in os.listdir(sample_path) if f.endswith(".json")
            )
            for s in samples:
                st.markdown(f"- `data/workflow_contexts/{s}`")
            st.caption("Drag any of these into the uploader below.")

    uploaded = st.sidebar.file_uploader(
        "Upload context JSON",
        type=["json"],
        key="ctx_uploader",
        label_visibility="collapsed",
    )

    if uploaded is not None and uploaded.name not in st.session_state.get("ctx_loaded_files", set()):
        try:
            payload = json.load(uploaded)
        except json.JSONDecodeError as e:
            st.sidebar.error(f"Invalid JSON: {e}")
        else:
            ok, msg, stats = _ingest_payload(payload)
            if ok:
                st.sidebar.success(msg)
                loaded = st.session_state.setdefault("ctx_loaded_files", set())
                loaded.add(uploaded.name)
            else:
                st.sidebar.error(msg)

    # ── Reset button ─────────────────────────────────────────────────────────
    # Full reset: wipes cases, events, AND the analysis byproducts (findings,
    # escalations, cluster snapshots, ingestion log). Anything less leaves
    # stale findings showing up in the Observatory after the upstream data is
    # gone — confusing during a demo.
    summary = _summarize_swa_db()
    has_anything = bool(summary) or bool(st.session_state.get("ctx_loaded_files"))
    if has_anything:
        if st.sidebar.button(
            "Reset SWA database",
            width='stretch',
            key="reset_swa_btn",
            help="Clears all cases, events, findings, and run history. "
                 "Use between demos for a clean slate.",
        ):
            counts = _reset_swa_db()
            cs = counts.get("cases", 0)
            ev = counts.get("activity_log", 0)
            ar = counts.get("analysis_runs", 0)
            st.sidebar.warning(
                f"Reset: {cs} cases, {ev} events, {ar} analysis runs cleared."
            )
            st.rerun()

    # ── Current SWA DB content ───────────────────────────────────────────────
    if summary:
        with st.sidebar.expander("SWA DB now contains", expanded=False):
            total_c = sum(r[1] for r in summary)
            total_e = sum(r[2] for r in summary)
            st.markdown(f"**Total: {total_c} cases / {total_e} events**")
            st.markdown("")
            for ct, n_c, n_e in summary:
                st.markdown(f"- `{ct}` — **{n_c}** cases, {n_e} events")
    else:
        st.sidebar.caption("_SWA DB is empty — upload a context to begin._")
