"""
SWA Observatory — process intelligence dashboard.

Reads pre-computed SWA results from SQLite and renders a multi-tab analytics
view for process engineers / system admins. A "Run analysis now" button can
trigger a fresh SWA analyze() over a chosen window.

Data sources (all in SWA SQLite, see SWA/db/schema.sql):
  - activity_log: every event ingested into SWA
  - analysis_runs: each analyze() invocation, with output_json (findings, escalations, metrics)
  - cluster_snapshots: ML cluster_summary per run
  - cases: registered cases
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd
import streamlit as st


# ── SWA path bootstrap ───────────────────────────────────────────────────────

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SWA_PATH = os.path.join(_REPO_ROOT, "SWA")
if _SWA_PATH not in sys.path:
    sys.path.insert(0, _SWA_PATH)


def _swa_db_path() -> str:
    try:
        from config.settings import settings  # type: ignore[import]
        return settings.DB_PATH
    except Exception:
        return os.path.join(_REPO_ROOT, "swa_v3.db")


def _connect() -> Optional[sqlite3.Connection]:
    path = _swa_db_path()
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ── Queries ──────────────────────────────────────────────────────────────────

def _q(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def _latest_run(conn: sqlite3.Connection) -> Optional[dict]:
    df = _q(conn, "SELECT * FROM analysis_runs ORDER BY run_timestamp DESC LIMIT 1")
    if df.empty:
        return None
    row = df.iloc[0].to_dict()
    try:
        row["output"] = json.loads(row.get("output_json") or "{}")
    except Exception:
        row["output"] = {}
    return row


def _all_findings(conn: sqlite3.Connection, since: Optional[str] = None) -> list[dict]:
    sql = "SELECT run_id, run_timestamp, output_json FROM analysis_runs"
    if since:
        sql += " WHERE run_timestamp >= ?"
        df = _q(conn, sql + " ORDER BY run_timestamp DESC", (since,))
    else:
        df = _q(conn, sql + " ORDER BY run_timestamp DESC")
    findings: list[dict] = []
    for _, r in df.iterrows():
        try:
            out = json.loads(r["output_json"] or "{}")
        except Exception:
            continue
        for f in out.get("findings", []) or []:
            f = dict(f)
            f["_run_id"] = r["run_id"]
            f["_run_ts"] = r["run_timestamp"]
            findings.append(f)
    return findings


def _all_escalations(conn: sqlite3.Connection, since: Optional[str] = None) -> list[dict]:
    sql = "SELECT run_id, run_timestamp, output_json FROM analysis_runs"
    if since:
        sql += " WHERE run_timestamp >= ?"
        df = _q(conn, sql + " ORDER BY run_timestamp DESC", (since,))
    else:
        df = _q(conn, sql + " ORDER BY run_timestamp DESC")
    out_list: list[dict] = []
    for _, r in df.iterrows():
        try:
            out = json.loads(r["output_json"] or "{}")
        except Exception:
            continue
        for e in out.get("escalations", []) or []:
            e = dict(e)
            e["_run_id"] = r["run_id"]
            e["_run_ts"] = r["run_timestamp"]
            out_list.append(e)
    return out_list


def _latest_clusters(conn: sqlite3.Connection) -> Optional[dict]:
    df = _q(
        conn,
        "SELECT * FROM cluster_snapshots ORDER BY snapshot_timestamp DESC LIMIT 1",
    )
    if df.empty:
        return None
    row = df.iloc[0].to_dict()
    try:
        row["clusters"] = json.loads(row.get("cluster_summary") or "[]")
    except Exception:
        row["clusters"] = []
    return row


# ── UI helpers ───────────────────────────────────────────────────────────────

# (bg, fg, border) tuples — soft pastels for light theme.
_URGENCY_COLORS = {
    "critical": ("#FEE2E2", "#7F1D1D", "#FCA5A5"),
    "high":     ("#FEF2F2", "#B91C1C", "#FECACA"),
    "medium":   ("#FEF3C7", "#B45309", "#FCD34D"),
    "low":      ("#DCFCE7", "#15803D", "#86EFAC"),
}


def _pill(text: str, color: str = "#F1F5F9") -> str:
    """
    Render a soft-pill badge. `color` may be either:
      - a tuple (bg, fg, border) for fully-themed pills, or
      - a single hex string used as the background (legacy callers).
    """
    if isinstance(color, tuple) and len(color) == 3:
        bg, fg, border = color
    else:
        bg, fg, border = color, "#0F172A", "#E2E8F0"
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {border};'
        f'padding:2px 10px;border-radius:10px;font-size:11px;'
        f'font-weight:600;display:inline-block;margin:2px 4px 2px 0;">{text}</span>'
    )


# ── Render ───────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        '<div style="background:#FFFFFF;color:#0F172A;padding:18px 24px;'
        'border-radius:3px;margin-bottom:20px;border:1px solid #E2E8F0;'
        'border-top:2px solid #0F2A47;'
        'box-shadow:0 1px 2px rgba(15,23,42,0.03);">'
        '<div style="font-size:10px;letter-spacing:1.8px;color:#64748B;'
        'font-weight:600;text-transform:uppercase;">'
        'Shadow Work Agent &nbsp;·&nbsp; Observatory</div>'
        '<div style="font-size:22px;font-weight:700;color:#0F172A;margin-top:6px;'
        'letter-spacing:-0.4px;line-height:1.15;">Process Intelligence</div>'
        '<div style="color:#475569;font-size:13px;margin-top:6px;line-height:1.5;'
        'max-width:640px;">'
        'Aggregated findings, escalations, clusters, and per-agent performance '
        'across the case corpus.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    conn = _connect()
    if conn is None:
        st.warning(
            f"No SWA database found at `{_swa_db_path()}`. "
            "Run `python -m infra.init_all` and execute at least one case "
            "from the Case Workspace tab to populate it."
        )
        return

    # ── Run-now control ───────────────────────────────────────────────────
    # No window picker. Observatory shows every case + event in the SWA DB —
    # what's loaded is what's visible. analyze() runs over a wide window
    # (1 year back through tomorrow) so any uploaded historical data is
    # included regardless of timestamp.
    _, run_col = st.columns([4, 1])
    with run_col:
        run_now = st.button("Run analysis now", width='stretch', key="obs_run_now")

    if run_now:
        with st.spinner("Running SWA analysis…"):
            try:
                from agent.orchestrator import analyze  # type: ignore[import]
                wide_start = datetime.now(timezone.utc) - timedelta(days=365)
                wide_end   = datetime.now(timezone.utc) + timedelta(days=1)
                analyze(window_start=wide_start, window_end=wide_end,
                        trigger_type="manual_observatory")
                st.success("Analysis complete.")
                st.rerun()
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")

    # ── Overview tiles ────────────────────────────────────────────────────
    total_events = int(_q(
        conn, "SELECT COUNT(*) AS c FROM activity_log",
    ).iloc[0]["c"])
    total_cases  = int(_q(
        conn, "SELECT COUNT(DISTINCT case_id) AS c FROM activity_log",
    ).iloc[0]["c"])
    findings_all    = _all_findings(conn)
    escalations_all = _all_escalations(conn)
    latest_run = _latest_run(conn)

    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric("Events", f"{total_events:,}")
    t2.metric("Cases", f"{total_cases:,}")
    t3.metric("Findings", f"{len(findings_all):,}")
    t4.metric("Escalations", f"{len(escalations_all):,}")
    t5.metric(
        "Last run",
        (latest_run.get("run_timestamp", "—")[:19] if latest_run else "—"),
    )

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_find, tab_esc, tab_clu, tab_act, tab_perf = st.tabs([
        "Findings & Recommendations",
        "Escalations",
        "Patterns / Clusters",
        "Activity Timeline",
        "Per-agent Performance",
    ])

    # Findings
    with tab_find:
        if not findings_all:
            st.info("No findings yet — click Run analysis now to generate them.")
        else:
            min_conf = st.slider("Minimum confidence", 0.0, 1.0, 0.5, 0.05, key="obs_minconf")

            visible: list[dict] = []
            rows: list[dict] = []
            for f in findings_all:
                conf = float(f.get("confidence_score") or f.get("confidence") or 0.0)
                if conf < min_conf:
                    continue
                visible.append(f)
                rec = f.get("automation_recommendation") or f.get("recommendation") or {}
                if isinstance(rec, dict):
                    rec_label = (
                        rec.get("action")
                        or rec.get("recommended_action")
                        or rec.get("type")
                        or ""
                    )
                else:
                    rec_label = str(rec)
                rows.append({
                    "run_id":    f.get("_run_id"),
                    "run_ts":    (f.get("_run_ts") or "")[:19],
                    "pattern":   f.get("pattern_type") or f.get("type") or "",
                    "confidence": round(conf, 2),
                    "evidence":  len(f.get("evidence_event_ids") or []),
                    "recommendation": rec_label,
                    "description": f.get("description") or f.get("summary") or "",
                })

            if not visible:
                st.info("No findings above the chosen confidence threshold.")
            else:
                st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

                st.divider()
                st.markdown("**Detailed view**")
                for f in visible:
                    pattern_type = f.get("pattern_type") or f.get("type") or "pattern"
                    conf         = float(f.get("confidence_score") or f.get("confidence") or 0.0)
                    rec          = f.get("automation_recommendation") or {}
                    rec_action   = rec.get("action") if isinstance(rec, dict) else str(rec)
                    rec_type     = rec.get("type") if isinstance(rec, dict) else None
                    rec_trigger  = rec.get("trigger") if isinstance(rec, dict) else None
                    rec_savings  = rec.get("estimated_time_saved_per_week_hours") if isinstance(rec, dict) else None

                    risk_level   = (f.get("risk_level") or "low").lower()
                    risk_color   = _URGENCY_COLORS.get(
                        risk_level,
                        _URGENCY_COLORS.get("low"),
                    )
                    decision     = (f.get("decision") or "recommend").upper()
                    requires_h   = bool(f.get("requires_human_approval"))

                    sig          = f.get("pattern_signature") or "—"
                    occurrences  = f.get("occurrences")
                    actors       = f.get("actors_involved") or []
                    cases        = f.get("cases_involved") or []
                    evidence     = f.get("evidence_event_ids") or []
                    detector     = f.get("detector_source") or ""
                    domain_desc  = (
                        f.get("domain_contextualized_description")
                        or f.get("description")
                        or ""
                    )
                    temporal     = f.get("temporal_signature") or {}
                    mean_h       = temporal.get("mean_interval_hours")
                    stddev_h     = temporal.get("stddev_interval_hours")
                    regularity   = temporal.get("regularity_score")

                    with st.container(border=True):
                        # Header — pattern type + risk + confidence + decision
                        header_bits = [
                            _pill(pattern_type.replace("_", " "), ("#EEF2FF", "#1E3A8A", "#C7D2FE")),
                            _pill(f"risk: {risk_level}", risk_color),
                            _pill(f"confidence: {conf:.2f}", ("#F1F5F9", "#0F172A", "#E2E8F0")),
                            _pill(decision, ("#DCFCE7", "#15803D", "#86EFAC") if decision == "RECOMMEND" else ("#FEF3C7", "#B45309", "#FCD34D")),
                        ]
                        if requires_h:
                            header_bits.append(_pill("HUMAN REVIEW", ("#FEE2E2", "#B91C1C", "#FCA5A5")))
                        st.markdown(" ".join(header_bits), unsafe_allow_html=True)

                        # Recommendation — the actionable part
                        if rec_action:
                            st.markdown(f"### {rec_action}")
                        if domain_desc:
                            st.markdown(domain_desc)

                        # Recommendation breakdown
                        rec_lines: list[str] = []
                        if rec_type:
                            rec_lines.append(f"**Automation type:** `{rec_type}`")
                        if rec_trigger:
                            rec_lines.append(f"**Trigger:** {rec_trigger}")
                        if rec_savings is not None:
                            rec_lines.append(f"**Estimated time saved:** {rec_savings} h/week")
                        if rec_lines:
                            st.markdown("  \n".join(rec_lines))

                        # Pattern facts
                        fact_bits: list[str] = []
                        fact_bits.append(f"**Pattern:** `{sig}`")
                        if occurrences is not None:
                            fact_bits.append(f"**Occurrences:** {occurrences}")
                        if mean_h is not None:
                            tt = f"**Mean interval:** {mean_h:.1f} h"
                            if stddev_h is not None:
                                tt += f" (σ {stddev_h:.1f})"
                            fact_bits.append(tt)
                        if regularity is not None:
                            fact_bits.append(f"**Regularity:** {regularity:.2f}")
                        st.markdown(" &nbsp;·&nbsp; ".join(fact_bits))

                        # Scope — actors + cases counts (lists are too long for inline)
                        scope_bits: list[str] = []
                        if actors:
                            scope_bits.append(f"**Actors involved:** {len(actors)}")
                        if cases:
                            scope_bits.append(f"**Cases spanned:** {len(cases)}")
                        if evidence:
                            scope_bits.append(f"**Evidence events:** {len(evidence)}")
                        if scope_bits:
                            st.markdown(" &nbsp;·&nbsp; ".join(scope_bits))

                        # Drill-down expanders
                        if actors:
                            with st.expander(f"Actors ({len(actors)})"):
                                for a in actors:
                                    st.markdown(f"- `{a}`")
                        if cases:
                            with st.expander(f"Cases ({len(cases)})"):
                                for c in cases[:50]:
                                    st.markdown(f"- `{c}`")
                                if len(cases) > 50:
                                    st.caption(f"... and {len(cases) - 50} more")
                        if evidence:
                            with st.expander(f"Evidence event IDs ({len(evidence)})"):
                                for ev_id in evidence[:30]:
                                    st.code(ev_id, language=None)
                                if len(evidence) > 30:
                                    st.caption(f"... and {len(evidence) - 30} more")

                        # Footer
                        foot_parts = []
                        if f.get("finding_id"):
                            foot_parts.append(f"Finding `{f.get('finding_id')}`")
                        if detector:
                            foot_parts.append(f"Detected by: {detector}")
                        foot_parts.append(f"Run `{f.get('_run_id')}`")
                        foot_parts.append((f.get("_run_ts") or "")[:19])
                        st.caption(" · ".join(foot_parts))

    # Escalations
    with tab_esc:
        if not escalations_all:
            st.info("No escalations yet.")
        else:
            for e in escalations_all:
                urgency = (e.get("urgency") or "medium").lower()
                color   = _URGENCY_COLORS.get(urgency, ("#F1F5F9", "#475569", "#E2E8F0"))
                # Title: prefer the short `reason`, fall back to pattern shape.
                title = (
                    e.get("title")
                    or e.get("reason")
                    or e.get("pattern_signature")
                    or e.get("pattern_type")
                    or "Escalation"
                )
                # Body: SWA emits `summary_for_human` — that's the readable
                # paragraph. Older shape used `description`/`summary`.
                body = (
                    e.get("summary_for_human")
                    or e.get("description")
                    or e.get("summary")
                    or ""
                )
                pattern_sig = e.get("pattern_signature")
                occurrences = e.get("occurrences")
                role        = e.get("recommended_human_role")
                evidence    = e.get("evidence_event_ids") or []
                esc_id      = e.get("escalation_id")

                with st.container(border=True):
                    st.markdown(
                        _pill(urgency.upper(), color)
                        + f" <strong>{title}</strong>",
                        unsafe_allow_html=True,
                    )
                    if body:
                        st.markdown(body)

                    # Detail row — small, structured facts the auditor needs.
                    detail_bits: list[str] = []
                    if pattern_sig:
                        detail_bits.append(f"**Pattern:** `{pattern_sig}`")
                    if occurrences is not None:
                        detail_bits.append(f"**Occurrences:** {occurrences}")
                    if role:
                        detail_bits.append(
                            f"**Recommended reviewer:** {role.replace('_', ' ').title()}"
                        )
                    if evidence:
                        detail_bits.append(f"**Evidence events:** {len(evidence)}")
                    if detail_bits:
                        st.markdown(" &nbsp;·&nbsp; ".join(detail_bits))

                    if evidence:
                        with st.expander(f"Evidence event IDs ({len(evidence)})"):
                            for ev_id in evidence[:20]:
                                st.code(ev_id, language=None)
                            if len(evidence) > 20:
                                st.caption(f"... and {len(evidence) - 20} more")

                    foot_parts = []
                    if esc_id:
                        foot_parts.append(f"Escalation `{esc_id}`")
                    foot_parts.append(f"Run `{e.get('_run_id')}`")
                    foot_parts.append((e.get('_run_ts') or '')[:19])
                    st.caption(" · ".join(foot_parts))

    # Clusters
    with tab_clu:
        snap = _latest_clusters(conn)
        if not snap:
            st.info("No cluster snapshots yet — run analysis with sufficient events.")
        else:
            st.caption(
                f"Snapshot {snap['snapshot_id']} · "
                f"cases={snap['total_cases']} · events={snap['total_events']} · "
                f"clusters={snap['clusters_found']}"
            )
            clusters = snap.get("clusters") or []
            if not clusters:
                st.info("Snapshot has no cluster summary.")
            else:
                # SWA cluster shape:
                #   fingerprint, action_type, target_entity_type,
                #   dominant_actor_type, median_hour_of_day, size, n_actors,
                #   n_cases, mean_interval_hours
                rows = []
                for c in clusters:
                    rows.append({
                        "fingerprint":          c.get("fingerprint") or c.get("cluster_id") or "—",
                        "action":               c.get("action_type") or c.get("dominant_action") or c.get("top_action") or "—",
                        "target":               c.get("target_entity_type") or "—",
                        "actor type":           c.get("dominant_actor_type") or "—",
                        "events":               c.get("size") or c.get("event_count"),
                        "cases":                c.get("n_cases") or c.get("case_count"),
                        "actors":               c.get("n_actors"),
                        "median hour":          c.get("median_hour_of_day"),
                        "mean interval (h)":    (
                            round(c.get("mean_interval_hours"), 1)
                            if c.get("mean_interval_hours") is not None else None
                        ),
                    })
                st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

    # Activity timeline
    with tab_act:
        df_act = _q(
            conn,
            "SELECT date(timestamp) AS day, action_type, COUNT(*) AS n "
            "FROM activity_log "
            "GROUP BY day, action_type ORDER BY day",
        )
        if df_act.empty:
            st.info("No activity yet — upload a workflow context to populate.")
        else:
            daily = df_act.groupby("day")["n"].sum().reset_index().set_index("day")
            st.markdown("**Events per day**")
            st.bar_chart(daily, height=220)

            pivot = df_act.pivot_table(
                index="day", columns="action_type", values="n", fill_value=0,
            )
            st.markdown("**By action type**")
            st.bar_chart(pivot, height=260)

    # Per-agent performance
    with tab_perf:
        df_perf = _q(
            conn,
            "SELECT actor_id AS agent, "
            "COUNT(*) AS events, "
            "SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) AS successes, "
            "COUNT(DISTINCT case_id) AS cases "
            "FROM activity_log WHERE actor_type='agent' "
            "GROUP BY actor_id ORDER BY events DESC",
        )
        if df_perf.empty:
            st.info("No agent activity yet.")
        else:
            df_perf["success_rate"] = (
                df_perf["successes"] / df_perf["events"].replace(0, 1)
            ).round(3)
            df_perf["events_per_case"] = (
                df_perf["events"] / df_perf["cases"].replace(0, 1)
            ).round(2)
            st.dataframe(df_perf, width='stretch', hide_index=True)
            st.bar_chart(df_perf.set_index("agent")["events"], height=240)

    conn.close()
