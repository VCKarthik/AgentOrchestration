"""
Project AMP — Enterprise Dashboard
Run: streamlit run demo/app.py

Three-column layout:
  Left   — Priority task queue (pre-loaded demo cases + "New Case" dialog)
  Center — Active case workspace: case card + live agent progress + result tabs
  Right  — Orchestration log (live, color-coded) + Suggested Next Actions (IAA)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from orchestrator.flow import run_amp_workflow
try:
    from infra.sqlite_init import upsert_state, init_sqlite
    _SQLITE_AVAILABLE = True
    init_sqlite()
except Exception:
    _SQLITE_AVAILABLE = False

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AMP — Agentic Microservices Prototyping",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────


# ── Top header bar ────────────────────────────────────────────────────────────

st.markdown(
    # Refined enterprise header — flat white surface, deep navy top rule,
    # restrained typography, geometric mark.
    '<div style="background:#FFFFFF;color:#0F172A;padding:14px 24px;'
    'border-radius:4px;margin-bottom:18px;display:flex;align-items:center;'
    'gap:18px;border:1px solid #E2E8F0;border-top:3px solid #0F2A47;'
    'box-shadow:0 1px 2px rgba(15,23,42,0.04);">'
    # Geometric mark — two stacked rules, no letter — feels like a banking logo
    '<div style="display:flex;flex-direction:column;justify-content:center;'
    'gap:2px;height:28px;flex-shrink:0;">'
    '<div style="width:22px;height:3px;background:#0F2A47;"></div>'
    '<div style="width:14px;height:3px;background:#475569;"></div>'
    '<div style="width:18px;height:3px;background:#94A3B8;"></div>'
    '</div>'
    # Wordmark + descriptor
    '<div style="line-height:1.15;">'
    '<div style="font-size:11px;font-weight:600;letter-spacing:2.5px;'
    'color:#64748B;text-transform:uppercase;">Project</div>'
    '<div style="font-size:20px;font-weight:700;letter-spacing:-0.4px;'
    'color:#0F172A;">AMP</div>'
    '</div>'
    # Vertical separator
    '<div style="width:1px;height:32px;background:#E2E8F0;"></div>'
    '<div style="font-size:13px;color:#475569;font-weight:500;">'
    'Agentic Microservices Platform</div>'
    # Right-aligned status
    '<div style="margin-left:auto;display:flex;gap:14px;align-items:center;">'
    '<span style="display:inline-flex;align-items:center;gap:6px;'
    'background:#FFFFFF;color:#15803D;padding:4px 10px;border-radius:3px;'
    'font-size:11px;font-weight:600;border:1px solid #BBF7D0;'
    'letter-spacing:0.4px;text-transform:uppercase;">'
    '<span style="width:6px;height:6px;border-radius:50%;background:#15803D;'
    'display:inline-block;"></span>Live</span>'
    '<span style="color:#64748B;font-size:11px;letter-spacing:0.5px;'
    'font-family:&#39;JetBrains Mono&#39;,&#39;SF Mono&#39;,monospace;">'
    'CSA · RRA · GPA · IAA · DA · SWA</span>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+Pro:wght@600;700&display=swap');

/* ── Project AMP — refined enterprise palette ─────────────────────────────
   Deep navy primary (#0F2A47), high-contrast text, tighter geometry.
   Aimed at "deployable internal tool", not "AI app".

   --bg-page         #F8FAFC   slate-50  page background
   --bg-card         #FFFFFF   white     cards, panels
   --bg-muted        #F1F5F9   slate-100 secondary surfaces
   --border          #E2E8F0   slate-200 default
   --border-strong   #CBD5E1   slate-300 hover / focused
   --text-primary    #0F172A   slate-900 headings
   --text-body       #334155   slate-700 body
   --text-muted      #64748B   slate-500 meta
   --navy            #0F2A47   deep navy brand mark
   --navy-action    #1E40AF   blue-800  primary action
   --green           #15803D   green-700 success
   --amber           #B45309   amber-700 warning
   --red             #B91C1C   red-700   danger
   ──────────────────────────────────────────────────────────────────────── */

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: #0F172A;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
h1, h2, h3, h4, h5 { letter-spacing: -0.3px; color: #0F172A; }
.block-container { padding: 1.25rem 2.25rem 2.5rem; max-width: 1440px; }

/* Hide Streamlit chrome */
header[data-testid="stHeader"] { display: none !important; }
#MainMenu { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }

/* Scrollbar — neutral */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: #F1F5F9; }
::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #94A3B8; }

/* Buttons — sharp 3px corner, deep navy */
button[kind="primary"] {
    background: #0F2A47 !important;
    color: #FFFFFF !important;
    border-radius: 3px !important;
    border: 1px solid #0F2A47 !important;
    padding: 8px 18px !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    letter-spacing: 0.3px !important;
    box-shadow: none !important;
    transition: background 0.12s ease, border-color 0.12s ease;
}
button[kind="primary"]:hover { background: #1E40AF !important; border-color: #1E40AF !important; }
button[kind="secondary"] {
    background: #FFFFFF !important;
    color: #0F172A !important;
    border-radius: 3px !important;
    border: 1px solid #CBD5E1 !important;
    padding: 8px 18px !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    box-shadow: none !important;
}
button[kind="secondary"]:hover { background: #F8FAFC !important; border-color: #94A3B8 !important; }

/* Generic card */
.card {
    background: #FFFFFF;
    padding: 16px 18px;
    border-radius: 4px;
    border: 1px solid #E2E8F0;
    margin-bottom: 12px;
}

/* Task queue items */
.task-item {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-left: 3px solid transparent;
    border-radius: 3px;
    padding: 12px 14px;
    margin-bottom: 8px;
    transition: background 0.12s ease, border-color 0.12s ease;
}
.task-item:hover { background: #F8FAFC; border-color: #CBD5E1; }
.task-item.selected { border-left: 3px solid #0F2A47; background: #F8FAFC; }

/* Typography */
.title-lg  { font-size: 22px; font-weight: 700; color: #0F172A; letter-spacing: -0.4px; line-height: 1.2; }
.title-md  { font-size: 15px; font-weight: 600; color: #0F172A; letter-spacing: -0.1px; }
.label-sm  { font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 0.8px; }
.body-text { font-size: 14px; font-weight: 400; color: #334155; line-height: 1.55; }
.meta-text { font-size: 12px; font-weight: 400; color: #64748B; }

/* Priority badges — refined squares, all-caps */
.badge-p1 { background: #FEF2F2; color: #991B1B; padding: 2px 8px; border-radius: 2px; font-size: 10px; font-weight: 700; letter-spacing: 0.6px; border: 1px solid #FCA5A5; text-transform: uppercase; }
.badge-p2 { background: #FFFBEB; color: #92400E; padding: 2px 8px; border-radius: 2px; font-size: 10px; font-weight: 700; letter-spacing: 0.6px; border: 1px solid #FCD34D; text-transform: uppercase; }
.badge-p3 { background: #F8FAFC; color: #475569; padding: 2px 8px; border-radius: 2px; font-size: 10px; font-weight: 700; letter-spacing: 0.6px; border: 1px solid #CBD5E1; text-transform: uppercase; }

/* Status chips — minimal pills */
.chip-pending   { background: #F8FAFC; color: #64748B; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; border: 1px solid #E2E8F0; }
.chip-running   { background: #EFF6FF; color: #1E40AF; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; border: 1px solid #BFDBFE; }
.chip-done      { background: #F0FDF4; color: #15803D; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; border: 1px solid #BBF7D0; }
.chip-escalated { background: #FEF2F2; color: #B91C1C; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; border: 1px solid #FCA5A5; }

/* Case type badge */
.case-type-badge { background: #F8FAFC; color: #0F2A47; padding: 3px 10px; border-radius: 3px; font-size: 11px; font-weight: 600; letter-spacing: 0.4px; border: 1px solid #CBD5E1; text-transform: uppercase; }

/* Agent chips */
.agent-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 10px; border-radius: 3px;
    font-size: 11px; font-weight: 500; margin-right: 6px; margin-bottom: 4px;
    border: 1px solid #CBD5E1;
    background: #FFFFFF;
    color: #475569;
    letter-spacing: 0.3px;
}

/* Case header card */
.case-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-top: 2px solid #0F2A47;
    border-radius: 3px;
    padding: 18px 22px;
    margin-bottom: 14px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}

/* Executive summary banner */
.exec-banner {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 3px;
    padding: 20px 26px;
    margin-bottom: 18px;
    display: flex;
    gap: 0;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.exec-stat {
    flex: 1; text-align: center; padding: 0 18px;
    border-right: 1px solid #E2E8F0;
}
.exec-stat:last-child { border-right: none; }
.exec-stat-value { font-size: 26px; font-weight: 700; color: #0F172A; line-height: 1.15; letter-spacing: -0.5px; }
.exec-stat-label { font-size: 10px; color: #64748B; margin-top: 6px; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }

/* Agent section cards */
.agent-section {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 3px;
    margin-bottom: 14px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.agent-section-header {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 18px;
    border-bottom: 1px solid #E2E8F0;
    background: #F8FAFC;
    font-size: 11px; font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: #0F172A;
}
.agent-section-body { padding: 18px; color: #334155; }

/* Log lines */
.log-line { font-family: 'JetBrains Mono','Courier New',monospace; font-size: 11px; padding: 3px 0; border-bottom: 1px solid #F1F5F9; color: #475569; }
.log-blue  { color: #1E40AF; }
.log-green { color: #15803D; }
.log-red   { color: #B91C1C; }

/* Status bar (collapsed log) */
.status-bar {
    background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 3px;
    padding: 8px 14px; font-family: 'JetBrains Mono','SF Mono','Courier New',monospace;
    font-size: 11px; color: #475569; display: flex; align-items: center; gap: 12px;
}
.status-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }

/* Stat card */
.stat-card { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 3px; padding: 16px 18px; text-align: center; margin-bottom: 8px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03); }
.stat-value { font-size: 22px; font-weight: 700; color: #0F172A; letter-spacing: -0.4px; }
.stat-label { font-size: 10px; color: #64748B; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }

/* Action cards */
.action-card     { border: 1px solid #E2E8F0; border-radius: 3px; padding: 12px 14px; margin-bottom: 8px; background: #FFFFFF; }
.action-card-rec { border: 1px solid #BBF7D0; border-left: 3px solid #15803D; border-radius: 3px; padding: 12px 14px; margin-bottom: 8px; background: #F0FDF4; }
.conf-badge { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 10px; background: #F0FDF4; color: #15803D; border: 1px solid #BBF7D0; letter-spacing: 0.4px; text-transform: uppercase; }

/* Sidebar — white, subtle border */
section[data-testid="stSidebar"] {
    background-color: #FFFFFF;
    border-right: 1px solid #E2E8F0;
}
section[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
section[data-testid="stSidebar"] h3 {
    font-size: 13px !important;
    font-weight: 700 !important;
    letter-spacing: 0.4px !important;
    color: #0F172A !important;
    text-transform: uppercase;
    margin-top: 14px !important;
    margin-bottom: 6px !important;
}

/* Inputs — flat 3px corner */
[data-baseweb="input"] input,
[data-baseweb="select"] > div,
.stTextInput > div > div > input,
.stTextArea textarea,
.stDateInput input,
.stNumberInput input {
    border-radius: 3px !important;
    border: 1px solid #CBD5E1 !important;
    background: #FFFFFF !important;
}
[data-testid="stFileUploaderDropzone"] {
    background: #F8FAFC !important;
    border: 1px dashed #CBD5E1 !important;
    border-radius: 3px !important;
}

/* Streamlit metric */
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 3px;
    padding: 14px 16px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
[data-testid="stMetricLabel"] { color: #64748B !important; font-size: 10px !important; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
[data-testid="stMetricValue"] { color: #0F172A !important; letter-spacing: -0.4px !important; }

/* Expanders */
[data-testid="stExpander"] details {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 3px;
}
[data-testid="stExpander"] details summary {
    font-size: 13px;
    font-weight: 500;
    color: #0F172A;
}

/* Tabs */
[data-baseweb="tab-list"] {
    border-bottom: 1px solid #E2E8F0 !important;
    gap: 24px;
}
[data-baseweb="tab"] {
    font-weight: 500;
    font-size: 13px;
    color: #475569;
}
[data-baseweb="tab"][aria-selected="true"] {
    color: #0F2A47 !important;
    font-weight: 600;
}
[data-baseweb="tab-highlight"] {
    background-color: #0F2A47 !important;
    height: 2px !important;
}

/* Dividers */
hr {
    margin: 12px 0 !important;
    border: 0 !important;
    border-top: 1px solid #E2E8F0 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────

AGENTS = ["CSA", "RRA", "GPA", "IAA", "DA", "SWA"]
STATUS_COLORS = {
    "waiting":  "#9CA3AF",
    "scanning": "#3B82F6",
    "done":     "#10B981",
    "flagged":  "#EF4444",
}
STATUS_LABELS = {
    "waiting":  "○",
    "scanning": "↻",
    "done":     "✓",
    "flagged":  "⚑",
}

DEMO_CASES = [
    # The three canonical workflows from the Project AMP kickoff doc and
    # the per-case demo spec. Each is wired to a specific source-data set
    # in CSA/data/csa.db and to a policy / candidate the downstream agents
    # can match. See infra/seed_csa_db.py for the source records.
    {
        "case_id":          "CASE-1001",
        "case_type":        "vendor_onboarding",
        "task_type":        "vendor_onboarding",
        "title":            "Vendor onboarding — incomplete documents — TechSupply Inc.",
        "description":      "TechSupply Inc. onboarding stalled. Insurance certificate "
                            "missing and NDA pending review. Must complete before May 6 "
                            "onboarding meeting.",
        "priority":         "high",
        "urgency":          "urgent",
        "requester":        "procurement@acme.com",
        "requester_role":   "procurement_manager",
        "business_domain":  "procurement",
        "estimated_effort": 4.0,
        "monetary_value":   150000,
    },
    {
        "case_id":          "CASE-2001",
        "case_type":        "interview_scheduling",
        "task_type":        "interview_scheduling",
        "title":            "Interview scheduled — Sarah Johnson — background check and "
                            "conflict of interest pending",
        "description":      "Technical interview confirmed May 7. Background check not "
                            "complete. Candidate's prior employer is a direct competitor — "
                            "conflict of interest review required before interview proceeds.",
        "priority":         "medium",
        "urgency":          "moderate",
        "requester":        "hr@acme.com",
        "requester_role":   "hr_manager",
        "business_domain":  "human_resources",
        "estimated_effort": 2.0,
        "monetary_value":   175000,
    },
    {
        "case_id":          "CASE-3001",
        "case_type":        "claim_review",
        "task_type":        "claim_review",
        "title":            "Medical claim review — David Kim — $1,200 — all documents received",
        "description":      "Claim CLM-001 for $1,200. All documents now complete. Policy "
                            "check shows within limits. Ready for final approval decision.",
        "priority":         "medium",
        "urgency":          "moderate",
        "requester":        "claims@acme.com",
        "requester_role":   "claims_processor",
        "business_domain":  "insurance",
        "estimated_effort": 1.0,
        "monetary_value":   1200,
    },
]

# ── Priority helpers ──────────────────────────────────────────────────────────

def _priority_badge(priority: str) -> str:
    p = (priority or "").lower()
    if p in ("critical", "high"):
        return '<span class="badge-p1">P1</span>'
    if p == "medium":
        return '<span class="badge-p2">P2</span>'
    return '<span class="badge-p3">P3</span>'


def _status_chip(status: str) -> str:
    css = {
        "pending": "chip-pending", "running": "chip-running",
        "done": "chip-done", "escalated": "chip-escalated",
    }.get(status, "chip-pending")
    return f'<span class="{css}">{status.upper()}</span>'


# ── Render helpers ────────────────────────────────────────────────────────────

def _get(obj, attr, default="—"):
    """Attribute access that works on both Pydantic models and dicts."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default) or default


def _pill(text: str, color) -> str:
    """
    Inline HTML pill badge.
    `color` may be a (bg, fg, border) tuple for full theming, or a single
    hex string used as the background. Defaults to dark text on light fill.
    """
    if isinstance(color, tuple) and len(color) == 3:
        bg, fg, border = color
    else:
        bg, fg, border = color, "#0F172A", "#E2E8F0"
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {border};'
        f'padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600;">'
        f'{text}</span>'
    )


# (bg, fg, border) — soft pastels readable on white.
_RISK_COLORS = {
    "low":      ("#DCFCE7", "#15803D", "#86EFAC"),
    "medium":   ("#FEF3C7", "#B45309", "#FCD34D"),
    "high":     ("#FEE2E2", "#B91C1C", "#FCA5A5"),
    "critical": ("#FECACA", "#7F1D1D", "#F87171"),
}
_DECISION_COLORS = {
    "APPROVE":  ("#DCFCE7", "#15803D", "#86EFAC"),
    "ESCALATE": ("#FEE2E2", "#B91C1C", "#FCA5A5"),
}


AGENT_COLORS = {
    "CSA": "#0D9488",   # teal
    "RRA": "#EF4444",   # red
    "GPA": "#8B5CF6",   # purple
    "IAA": "#3B82F6",   # blue
    "DA":  "#10B981",   # green
    "SWA": "#F59E0B",   # amber
}
AGENT_ICONS = {
    "CSA": "🔍", "RRA": "⚠", "GPA": "⚖", "IAA": "🧠", "DA": "👤", "SWA": "👁",
}

def _render_agent_bar(statuses: dict, container) -> None:
    parts = []
    for agent in AGENTS:
        s = statuses.get(agent, "waiting")
        base_color = AGENT_COLORS[agent]
        icon = AGENT_ICONS[agent]
        if s == "waiting":
            bg = "#1E293B"; border = base_color + "44"; text_color = "#475569"
            status_icon = "○"
        elif s == "scanning":
            bg = base_color + "22"; border = base_color; text_color = "#F1F5F9"
            status_icon = "↻"
        elif s == "done":
            bg = base_color + "22"; border = base_color; text_color = base_color
            status_icon = "✓"
        else:  # flagged
            bg = "#450A0A"; border = "#EF4444"; text_color = "#FCA5A5"
            status_icon = "⚑"
        parts.append(
            f'<span class="agent-chip" style="background:{bg};border-color:{border};color:{text_color};">'
            f'{icon} {agent} <span style="font-size:10px;opacity:0.8;">{status_icon}</span></span>'
        )
    html = '<div style="margin:10px 0 16px 0;display:flex;flex-wrap:wrap;">' + "".join(parts) + "</div>"
    container.markdown(html, unsafe_allow_html=True)


def _render_log(messages: list[dict], container) -> None:
    if not messages:
        container.markdown(
            '<p style="color:#9CA3AF;font-size:13px;">Waiting for workflow to start…</p>',
            unsafe_allow_html=True,
        )
        return
    lines = []
    for m in messages[-60:]:   # keep last 60 lines to avoid overflow
        css = {"blue": "log-blue", "green": "log-green", "red": "log-red"}.get(m["color"], "log-blue")
        prefix = {"blue": "INFO", "green": "SUCCESS", "red": "ERROR"}.get(m["color"], "INFO")
        text = m["text"].replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f'<div class="log-line {css}">[{m["ts"]}] {prefix} ▸ {text}</div>')
    html = '<div style="max-height:340px;overflow-y:auto;">' + "".join(lines) + "</div>"
    container.markdown(html, unsafe_allow_html=True)


def _render_suggested_actions(iaa_output, container) -> None:
    if not iaa_output:
        container.markdown(
            '<p style="color:#9CA3AF;font-size:13px;">No IAA output yet.</p>',
            unsafe_allow_html=True,
        )
        return

    rec_id = (iaa_output.recommended_action.action_id
              if iaa_output.recommended_action else None)

    actions = iaa_output.predicted_actions or []
    if not actions and iaa_output.recommended_action:
        actions = [iaa_output.recommended_action]

    parts = []
    for a in actions[:3]:
        is_rec = a.action_id == rec_id
        css = "action-card-rec" if is_rec else "action-card"
        conf_pct = int((a.confidence or 0) * 100)
        rec_label = " ★ Recommended" if is_rec else ""
        label_html = a.label or a.action_id
        reasoning = (a.reasoning or "")[:120]
        parts.append(
            f'<div class="{css}">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<strong style="font-size:13px;">{label_html}</strong>'
            f'<span>'
            f'<span class="conf-badge">{conf_pct}%</span>'
            f'<span style="color:#6B7280;font-size:11px;margin-left:6px;">{rec_label}</span>'
            f'</span></div>'
            f'<div style="color:#6B7280;font-size:12px;margin-top:4px;">{reasoning}</div>'
            f"</div>"
        )
    container.markdown("".join(parts), unsafe_allow_html=True)


# ── on_progress callback parser ───────────────────────────────────────────────

def _parse_progress(
    msg: str,
    agent_statuses: dict,
    log_messages: list,
    agent_bar_container,
    log_container,
) -> None:
    """Parse a progress message, update agent statuses + log, re-render containers."""
    msg_lower = msg.lower()

    if "stage 1" in msg_lower and ("csa" in msg_lower or "fetching" in msg_lower):
        agent_statuses["CSA"] = "scanning"
        color = "blue"
    elif "stage 1 complete" in msg_lower:
        agent_statuses["CSA"] = "done"
        color = "green"
    elif "stage 2" in msg_lower and "parallel" in msg_lower:
        for a in ("RRA", "GPA", "IAA"):
            agent_statuses[a] = "scanning"
        agent_statuses["SWA"] = "scanning"   # SWA fires async here
        color = "blue"
    elif msg_lower.lstrip().startswith("rra:") or "  rra:" in msg_lower:
        flagged = "escalate=true" in msg_lower or any(
            x in msg_lower for x in ("high", "critical", "escalat")
        )
        agent_statuses["RRA"] = "flagged" if flagged else "done"
        color = "red" if flagged else "green"
    elif msg_lower.lstrip().startswith("gpa:") or "  gpa:" in msg_lower:
        flagged = "escalate" in msg_lower or "requires_approval=true" in msg_lower
        agent_statuses["GPA"] = "flagged" if flagged else "done"
        color = "red" if flagged else "green"
    elif msg_lower.lstrip().startswith("iaa:") or "  iaa:" in msg_lower:
        flagged = "escalat" in msg_lower or "override" in msg_lower or "fast_path" in msg_lower
        agent_statuses["IAA"] = "flagged" if flagged else "done"
        color = "red" if flagged else "green"
    elif "stage 2 complete" in msg_lower or "building" in msg_lower:
        color = "blue"
    elif "da:" in msg_lower and "sending" in msg_lower:
        agent_statuses["DA"] = "scanning"
        color = "blue"
    elif "stage 3 complete" in msg_lower or "da complete" in msg_lower or (
        "da:" in msg_lower and ("status=" in msg_lower or "assigned" in msg_lower)
    ):
        agent_statuses["DA"] = "done"
        color = "green"
    elif "workflow complete" in msg_lower:
        agent_statuses["DA"] = agent_statuses.get("DA") or "done"
        agent_statuses["SWA"] = "done"
        color = "green"
    elif any(x in msg_lower for x in ("escalat", "rule", "flagg", "override", "blocked")):
        color = "red"
    else:
        color = "blue"

    ts = datetime.now().strftime("%H:%M:%S")
    log_messages.append({"text": msg, "color": color, "ts": ts})

    _render_agent_bar(agent_statuses, agent_bar_container)
    _render_log(log_messages, log_container)


# ── Session state init ────────────────────────────────────────────────────────

def _init_state() -> None:
    if "task_queue" not in st.session_state:
        st.session_state.task_queue = [
            {
                "idx":      i,
                "label":    c["title"],
                "priority": c["priority"],
                "status":   "pending",
                "data":     c,
            }
            for i, c in enumerate(DEMO_CASES)
        ]
    if "active_idx" not in st.session_state:
        st.session_state.active_idx = None
    if "agent_statuses" not in st.session_state:
        st.session_state.agent_statuses = {a: "waiting" for a in AGENTS}
    if "log_messages" not in st.session_state:
        st.session_state.log_messages = []
    if "workflow_result" not in st.session_state:
        st.session_state.workflow_result = None
    if "running" not in st.session_state:
        st.session_state.running = False
    if "sidebar_open" not in st.session_state:
        st.session_state.sidebar_open = True


_init_state()

# ── New Case dialog ───────────────────────────────────────────────────────────

@st.dialog("New Case")
def _new_case_dialog() -> None:
    case_id   = st.text_input("Case ID", placeholder="CASE-XXX-000")
    case_type = st.selectbox("Type", [
        "vendor_onboarding", "claim_review", "fraud_investigation", "compliance_review"
    ])
    priority  = st.selectbox("Priority", ["critical", "high", "medium", "low"], index=2)
    urgency   = st.selectbox("Urgency", ["immediate", "urgent", "moderate", "low"], index=2)
    title     = st.text_input("Title")
    description = st.text_area("Description", height=80)
    col_a, col_b = st.columns(2)
    requester      = col_a.text_input("Requester", "analyst")
    business_domain = col_b.text_input("Business Domain", "operations")

    if st.button("Add to Queue", type="primary"):
        new_case = {
            "case_id":          case_id or f"CASE-NEW-{int(time.time())}",
            "case_type":        case_type,
            "task_type":        case_type,
            "title":            title or case_type.replace("_", " ").title(),
            "description":      description or "",
            "priority":         priority,
            "urgency":          urgency,
            "requester":        requester,
            "requester_role":   "analyst",
            "business_domain":  business_domain,
            "estimated_effort": 2.0,
        }
        new_idx = len(st.session_state.task_queue)
        st.session_state.task_queue.append({
            "idx":      new_idx,
            "label":    new_case["title"],
            "priority": new_case["priority"],
            "status":   "pending",
            "data":     new_case,
        })
        st.session_state.active_idx = new_idx
        st.session_state.agent_statuses = {a: "waiting" for a in AGENTS}
        st.session_state.log_messages   = []
        st.session_state.workflow_result = None
        st.rerun()


# ── Page selector ─────────────────────────────────────────────────────────────

if st.session_state.sidebar_open:
    col_close, _ = st.sidebar.columns([1, 3])
    if col_close.button("✕", key="close_sidebar"):
        st.session_state.sidebar_open = False
        st.rerun()

    st.sidebar.markdown("### View")
    try:
        _page = st.sidebar.pills(
            "View",
            ["Case Workspace", "SWA Observatory"],
            key="amp_page",
        )
    except AttributeError:
        _page = st.sidebar.radio(
            "View",
            ["Case Workspace", "SWA Observatory"],
            label_visibility="collapsed",
            key="amp_page",
        )

    # Workflow-context uploader: gives SWA a domain-specific backdrop so its
    # findings reference the workflow on screen instead of generic synthetic data.
    from demo import workflow_context as _wf_ctx
    _wf_ctx.render_sidebar_panel()

    # Policy uploader: feeds GPA the customer's own policies (procurement
    # rules, claim thresholds, etc.). GPA evaluates each case against these.
    from demo import policy_context as _pol_ctx
    _pol_ctx.render_sidebar_panel()

    # Roster uploader: feeds DA the customer's team. DA reads from the
    # active_roster.json file on every /predict — no DA restart needed.
    from demo import assignee_context as _asg_ctx
    _asg_ctx.render_sidebar_panel()
else:
    _page = st.session_state.get("amp_page", "Case Workspace")

if _page == "SWA Observatory":
    from demo import observatory
    observatory.render()
    st.stop()

# ── Layout ────────────────────────────────────────────────────────────────────

# Always-visible sidebar toggle — native header is hidden via CSS so this is the only toggle
_tog_col, _spacer = st.columns([0.08, 3])
with _tog_col:
    _tog_icon = "◀" if st.session_state.sidebar_open else "☰"
    if st.button(_tog_icon, key="toggle_sidebar", help="Toggle navigation panel"):
        st.session_state.sidebar_open = not st.session_state.sidebar_open
        st.rerun()

left_col, center_col, right_col = st.columns([1, 2.5, 1.5], gap="medium")

# ═══════════════════════════════════════════════════════════════
# LEFT — Priority Queue
# ═══════════════════════════════════════════════════════════════

with left_col:
    st.markdown(
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">'
        '<span style="font-size:13px;font-weight:700;color:#94A3B8;letter-spacing:1px;text-transform:uppercase;">Case Queue</span>'
        f'<span style="background:#1E293B;color:#64748B;padding:2px 8px;border-radius:12px;font-size:11px;">'
        f'{len(st.session_state.task_queue)} cases</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    if st.button("＋ NEW CASE", width='stretch'):
        _new_case_dialog()

    st.markdown('<div style="height:1px;background:#1F2937;margin:12px 0;"></div>', unsafe_allow_html=True)

    # Agent color map for case type accent
    _CASE_TYPE_COLORS = {
        "vendor_onboarding":  "#0D9488",
        "claim_review":       "#3B82F6",
        "fraud_investigation":"#EF4444",
        "compliance_review":  "#8B5CF6",
    }

    for entry in st.session_state.task_queue:
        idx       = entry["idx"]
        badge     = _priority_badge(entry["priority"])
        chip      = _status_chip(entry["status"])
        is_active = (idx == st.session_state.active_idx)
        extra_cls = " selected" if is_active else ""
        case_type = entry["data"]["case_type"]
        type_label = case_type.replace("_", " ").title()

        # Neutral enterprise styling:
        #  • Title in dark slate (#0F172A) — readable on white
        #  • Case-type chip uses the same neutral .case-type-badge as the
        #    Active Case header — no per-domain greens/blues/reds
        #  • Active card's left rule is the brand navy, not the domain colour
        active_rule = "#0F2A47" if is_active else "transparent"

        st.markdown(
            f'<div class="task-item{extra_cls}" '
            f'style="border-left:3px solid {active_rule};">'
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">'
            f'{badge} &nbsp; {chip}'
            f'<span class="case-type-badge" style="margin-left:auto;">{type_label}</span>'
            f'</div>'
            f'<div style="font-size:13px;font-weight:600;color:#0F172A;line-height:1.35;">'
            f'{entry["label"]}</div>'
            f'<div style="font-size:11px;color:#64748B;margin-top:4px;'
            f'font-family:&#39;JetBrains Mono&#39;,&#39;SF Mono&#39;,monospace;'
            f'letter-spacing:0.3px;">{entry["data"]["case_id"]}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button("Select", key=f"sel_{idx}", width='stretch'):
            st.session_state.active_idx      = idx
            st.session_state.agent_statuses  = {a: "waiting" for a in AGENTS}
            st.session_state.log_messages    = []
            st.session_state.workflow_result = None
            st.session_state.running         = False
            st.rerun()


# ═══════════════════════════════════════════════════════════════
# CENTER — Active Case Workspace
# ═══════════════════════════════════════════════════════════════

with center_col:
    st.markdown("### 🖥 ACTIVE CASE")

    active_idx = st.session_state.active_idx
    if active_idx is None:
        st.info("Select a case from the left panel to begin.")
    else:
        case = st.session_state.task_queue[active_idx]["data"]

        # Case header card
        type_badge = f'<span class="case-type-badge">{case["case_type"]}</span>'
        prio_badge = _priority_badge(case["priority"])
        st.markdown(
            f'<div class="case-card">'
            f'<div style="display:flex;align-items:center;gap:10px;">'
            f'<span style="font-weight:700;font-size:15px;color:#E5E7EB;">{case["case_id"]}</span>'
            f'{type_badge} {prio_badge}'
            f'</div>'
            f'<div style="font-size:14px;font-weight:600;margin-top:8px;color:#E5E7EB;">{case["title"]}</div>'
            f'<div class="meta-text" style="margin-top:4px;">'
            f'Requester: {case["requester"]} &nbsp;·&nbsp; Domain: {case["business_domain"]}'
            f'</div>'
            f'<div style="font-size:12px;color:#9CA3AF;margin-top:6px;">{case["description"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Agent progress bar (placeholder updated live by callback)
        st.markdown("**Live Agent Progress**")
        agent_bar = st.empty()
        _render_agent_bar(st.session_state.agent_statuses, agent_bar)

        # Self-heal: if a previous run set running=True but its st.rerun()
        # never reached the browser (websocket dropped, browser idled, etc.),
        # the page can be stuck on "Workflow in progress" forever even though
        # the result is sitting in session_state. Detect that and clear the
        # flag so the next render shows the result.
        if (
            st.session_state.running
            and st.session_state.workflow_result is not None
        ):
            st.session_state.running = False
            st.session_state.task_queue[active_idx]["status"] = "done"

        # RUN button
        if not st.session_state.running:
            run_btn = st.button("▶ RUN WORKFLOW", type="primary", width='stretch')
            # Manual escape hatch — surfaces only when result is already
            # sitting in session_state. Lets a presenter recover from a
            # frozen-spinner browser state without losing the run.
            if st.session_state.workflow_result is None:
                st.empty()
        else:
            run_btn = False
            spin_a, spin_b = st.columns([3, 1])
            with spin_a:
                st.info("⏳ Workflow in progress…")
            with spin_b:
                if st.button("Reset", help="Cancel and reset the in-progress flag",
                             width='stretch', key="reset_running_btn"):
                    st.session_state.running = False
                    st.session_state.task_queue[active_idx]["status"] = "pending"
                    st.rerun()

        if run_btn:
            # Reset state for this run
            st.session_state.agent_statuses  = {a: "waiting" for a in AGENTS}
            st.session_state.log_messages    = []
            st.session_state.workflow_result = None
            st.session_state.running         = True
            st.session_state.task_queue[active_idx]["status"] = "running"

            # Reset containers
            _render_agent_bar(st.session_state.agent_statuses, agent_bar)

            log_messages    = st.session_state.log_messages
            agent_statuses  = st.session_state.agent_statuses

            # Right-column live containers (need references before asyncio.run blocks)
            # We'll use session state to share the log; right column reads it after.
            # For true live updates we cache references via a mutable object.
            _live = {"agent_bar": agent_bar}

            # We build on_progress to close over the right-column containers.
            # right_col containers are created later in the layout pass —
            # use st.empty() slots stored in session state.
            _log_ref   = st.session_state.get("_log_container_ref")
            _sugg_ref  = st.session_state.get("_sugg_container_ref")

            def on_progress(msg: str) -> None:
                _parse_progress(
                    msg,
                    agent_statuses,
                    log_messages,
                    agent_bar,
                    _log_ref if _log_ref else st.empty(),
                )

            run_task_id  = f'{case["case_id"]}-{int(time.time())}'
            due_date_iso = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()

            try:
                result = asyncio.run(run_amp_workflow({
                    "task_id":          run_task_id,
                    "case_id":          case["case_id"],
                    "case_type":        case["case_type"],
                    "task_type":        case.get("task_type", case["case_type"]),
                    "title":            case["title"],
                    "description":      case["description"],
                    "requester":        case["requester"],
                    "requester_role":   case.get("requester_role", "analyst"),
                    "priority":         case["priority"],
                    "urgency":          case.get("urgency", "moderate"),
                    "estimated_effort": case.get("estimated_effort", 2.0),
                    "due_date":         due_date_iso,
                    "business_domain":  case["business_domain"],
                }, on_progress=on_progress))

                st.session_state.workflow_result = result
                st.session_state.running         = False
                st.session_state.task_queue[active_idx]["status"] = "done"
                if _SQLITE_AVAILABLE:
                    try:
                        upsert_state(
                            case["case_id"], "done",
                            {a: "done" for a in AGENTS},
                            result.model_dump(mode="json"),
                        )
                    except Exception:
                        pass

                # P1 auto-promotion
                needs_escalation = getattr(result, "requires_escalation", False)
                iaa_override = (
                    result.iaa_output.override_applied
                    if result.iaa_output else False
                )
                if needs_escalation or iaa_override:
                    st.session_state.task_queue[active_idx]["priority"] = "critical"
                    st.session_state.task_queue[active_idx]["status"]   = "escalated"

            except Exception as exc:
                st.session_state.running = False
                st.session_state.task_queue[active_idx]["status"] = "pending"
                st.error(f"Workflow failed: {exc}")
                st.exception(exc)

            st.rerun()

        # ── Results (shown after workflow completes) ──────────────────────────
        result = st.session_state.workflow_result
        if result is not None:
            # ── Executive Summary Banner ─────────────────────────────────────
            esc_val   = "YES" if result.requires_escalation else "NO"
            esc_color = "#EF4444" if result.requires_escalation else "#4ADE80"
            ctx_val   = (result.operating_context or "—").capitalize()
            risk_val  = (result.risk_output.overall_risk_level if result.risk_output else "—").upper()
            risk_color = {"LOW":"#4ADE80","MEDIUM":"#FBBF24","HIGH":"#EF4444","CRITICAL":"#991B1B"}.get(risk_val,"#94A3B8")
            da = result.da_output
            if da:
                # Prefer the actual person's name (selected_assignee). Fall back to
                # the owner-channel role only when no person is named.
                _assignee_raw = da.selected_assignee
                _assignee = (
                    _assignee_raw.model_dump() if hasattr(_assignee_raw, "model_dump")
                    else (_assignee_raw if isinstance(_assignee_raw, dict) else {})
                )
                _owner_raw = da.selected_owner
                _owner = (
                    _owner_raw.model_dump() if hasattr(_owner_raw, "model_dump")
                    else (_owner_raw if isinstance(_owner_raw, dict) else {})
                )
                owner_display = (
                    _assignee.get("name")
                    or _owner.get("name")
                    or _owner.get("role")
                    or da.selected_owner_type
                    or "—"
                )
                raw_conf = da.confidence_score or 0
                conf_pct = int(raw_conf if raw_conf > 1 else raw_conf * 100)
            else:
                owner_display = "—"; conf_pct = 0

            st.markdown(
                f'<div class="exec-banner">'
                f'<div class="exec-stat">'
                f'<div class="exec-stat-value" style="color:{esc_color};">{esc_val}</div>'
                f'<div class="exec-stat-label">Escalation</div></div>'
                f'<div class="exec-stat">'
                f'<div class="exec-stat-value" style="color:{risk_color};">{risk_val}</div>'
                f'<div class="exec-stat-label">Risk Level</div></div>'
                f'<div class="exec-stat">'
                f'<div class="exec-stat-value">{conf_pct}%</div>'
                f'<div class="exec-stat-label">Confidence</div></div>'
                f'<div class="exec-stat">'
                f'<div class="exec-stat-value" style="font-size:16px;">{owner_display}</div>'
                f'<div class="exec-stat-label">Assigned To</div></div>'
                f'<div class="exec-stat">'
                f'<div class="exec-stat-value" style="font-size:16px;">{ctx_val}</div>'
                f'<div class="exec-stat-label">Context</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Agent sections (vertical scroll, replaces tabs) ──────────────
            _SEC_COLORS = {
                "CSA":"#0D9488","DA":"#10B981","RRA":"#EF4444","GPA":"#8B5CF6",
                "IAA":"#3B82F6","SWA":"#F59E0B"
            }
            _SEC_ICONS = {"CSA":"🗂","DA":"👤","RRA":"⚠","GPA":"⚖","IAA":"🧠","SWA":"👁"}

            def _sec_header(agent_key, title):
                c = _SEC_COLORS.get(agent_key,"#475569")
                i = _SEC_ICONS.get(agent_key,"●")
                st.markdown(
                    f'<div class="agent-section-header" style="background:{c}18;border-left:4px solid {c};">'
                    f'<span style="font-size:16px;">{i}</span>'
                    f'<span style="color:{c};">{title}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # ── CSA Section ───────────────────────────────────────────────────
            st.markdown('<div class="agent-section">', unsafe_allow_html=True)
            _sec_header("CSA", "Context Stitching (CSA)")
            st.markdown('<div class="agent-section-body">', unsafe_allow_html=True)
            csa = result.csa_output
            if csa:
                val = csa.validation
                status = (val.status if val else "—").upper()
                _STATUS_COLORS = {
                    "COMPLETE": ("#DCFCE7", "#15803D", "#86EFAC"),
                    "PARTIAL":  ("#FEF3C7", "#B45309", "#FCD34D"),
                    "EMPTY":    ("#FEE2E2", "#B91C1C", "#FCA5A5"),
                }
                badge = _pill(status, _STATUS_COLORS.get(status, ("#F1F5F9","#475569","#E2E8F0")))
                st.markdown(f"**Context Status:** {badge}", unsafe_allow_html=True)

                # ── 5-tile metric row ─────────────────────────────────────
                ctx = csa.context
                emails_n = len(ctx.emails or []) if ctx else 0
                docs_n   = len(ctx.documents or []) if ctx else 0
                cal_n    = len(ctx.calendar_events or []) if ctx else 0
                hist_n   = len(ctx.case_history or []) if ctx else 0

                conf = int((val.confidence_score or 0) * 100) if val else 0
                total = val.total_sources if val else (emails_n + docs_n + cal_n + hist_n)

                # Document status counts
                docs_verified = docs_pending = docs_missing = 0
                if ctx and ctx.documents:
                    for d in ctx.documents:
                        d_dump = d.model_dump() if hasattr(d, "model_dump") else d
                        s = (d_dump.get("status") or "").lower()
                        if s in ("verified", "active"):
                            docs_verified += 1
                        elif s in ("pending", "pending_review", "outstanding"):
                            docs_pending += 1
                        elif s in ("missing", "absent", "not_received"):
                            docs_missing += 1

                t1, t2, t3, t4, t5 = st.columns(5)
                t1.metric("Total Sources", total)
                t2.metric("Confidence", f"{conf}%")
                t3.metric("Documents",  docs_n,
                          delta=(f"{docs_missing} missing" if docs_missing else f"{docs_verified} verified"),
                          delta_color=("inverse" if docs_missing else "off"))
                t4.metric("Emails",      emails_n)
                t5.metric("History",     hist_n,
                          delta=(f"{cal_n} cal events" if cal_n else None),
                          delta_color="off")

                # ── Source breakdown — one expander per source type ──────
                if ctx:
                    st.markdown("**Source Breakdown**")

                    if ctx.emails:
                        with st.expander(f"Emails ({len(ctx.emails)})", expanded=False):
                            for e in ctx.emails:
                                e_d = e.model_dump() if hasattr(e, "model_dump") else e
                                subj = e_d.get("subject") or "(no subject)"
                                sndr = e_d.get("sender") or "—"
                                dt   = (e_d.get("date") or "")[:16]
                                st.markdown(f"- **{subj}**  \n"
                                            f"  _{sndr} · {dt}_")

                    if ctx.documents:
                        _DOC_BADGE = {
                            "verified":       ("#DCFCE7", "#15803D", "#86EFAC"),
                            "active":         ("#DCFCE7", "#15803D", "#86EFAC"),
                            "pending":        ("#FEF3C7", "#B45309", "#FCD34D"),
                            "pending_review": ("#FEF3C7", "#B45309", "#FCD34D"),
                            "missing":        ("#FEE2E2", "#B91C1C", "#FCA5A5"),
                        }
                        with st.expander(f"Documents ({len(ctx.documents)})", expanded=False):
                            for d in ctx.documents:
                                d_d = d.model_dump() if hasattr(d, "model_dump") else d
                                fname = d_d.get("filename") or "(unnamed)"
                                stat  = (d_d.get("status") or "active").lower()
                                badge = _pill(stat.upper(), _DOC_BADGE.get(stat, ("#F1F5F9","#475569","#E2E8F0")))
                                desc  = d_d.get("description") or ""
                                st.markdown(f"- **{fname}** &nbsp; {badge}  \n  _{desc}_",
                                            unsafe_allow_html=True)

                    if ctx.calendar_events:
                        with st.expander(f"Calendar ({len(ctx.calendar_events)})", expanded=False):
                            for c in ctx.calendar_events:
                                c_d = c.model_dump() if hasattr(c, "model_dump") else c
                                title = c_d.get("title") or "(untitled)"
                                start = (c_d.get("start_time") or "")[:16]
                                stat  = c_d.get("status") or "scheduled"
                                st.markdown(f"- **{title}** — {start} _({stat})_")

                    if ctx.case_history:
                        with st.expander(f"Case History ({len(ctx.case_history)})", expanded=False):
                            for h in ctx.case_history:
                                h_d = h.model_dump() if hasattr(h, "model_dump") else h
                                evt = h_d.get("event_type") or "—"
                                actor = h_d.get("actor") or "system"
                                ts  = (h_d.get("timestamp") or "")[:16]
                                stat= h_d.get("status") or ""
                                st.markdown(f"- **{evt.replace('_',' ').title()}** by `{actor}` · {ts} _({stat})_")

                # ── Footer — provenance + warnings ───────────────────────
                _foot = []
                meta = csa.meta
                if meta:
                    if meta.retrieval_method:
                        _foot.append(f"**Retrieval:** `{meta.retrieval_method}`")
                    if meta.sql_hits is not None:
                        _foot.append(f"**SQL hits:** {meta.sql_hits}")
                    if meta.qdrant_hits is not None:
                        _foot.append(f"**Qdrant hits:** {meta.qdrant_hits}")
                    if meta.csa_version:
                        _foot.append(f"**CSA:** v{meta.csa_version}")
                if _foot:
                    st.caption(" &nbsp;·&nbsp; ".join(_foot))
                if meta and meta.keywords_used:
                    st.caption(f"Keywords: {', '.join(meta.keywords_used)}")

                if val and val.warnings:
                    for w in val.warnings:
                        st.warning(w)
            else:
                st.info("No CSA output")
            st.markdown('</div></div>', unsafe_allow_html=True)

            # ── DA Section ────────────────────────────────────────────────────
            st.markdown('<div class="agent-section">', unsafe_allow_html=True)
            _sec_header("DA", "Assignment (DA)")
            st.markdown('<div class="agent-section-body">', unsafe_allow_html=True)
            da = result.da_output
            if da:
                # Prefer the named assignee. Fall back to owner role / channel.
                _assignee_raw = da.selected_assignee
                assignee = (
                    _assignee_raw.model_dump() if hasattr(_assignee_raw, "model_dump")
                    else (_assignee_raw if isinstance(_assignee_raw, dict) else {})
                )
                _owner_raw = da.selected_owner
                owner = (
                    _owner_raw.model_dump() if hasattr(_owner_raw, "model_dump")
                    else (_owner_raw if isinstance(_owner_raw, dict) else {})
                )
                name = assignee.get("name") or owner.get("name") or "—"
                role = (
                    assignee.get("role")
                    or owner.get("role")
                    or da.selected_owner_type
                    or ""
                )
                # Sub-line shows role; the tile value shows the person.
                role_sub = f"{role}" if role and role != "—" else None
                raw = da.confidence_score or 0
                conf_pct = int(raw if raw > 1 else raw * 100)
                c1, c2 = st.columns(2)
                c1.metric("Assigned to", name, delta=role_sub, delta_color="off")
                c1.metric("Channel", da.selected_channel or "—")
                c2.metric("Confidence", f"{conf_pct}%")
                c2.metric("Escalation Required", "Yes" if da.escalation_required else "No")
                if da.reasons:
                    st.markdown("**Reasons**")
                    for r in da.reasons: st.markdown(f"- {r}")
                if da.candidate_rankings:
                    import pandas as _pd
                    st.markdown("**Candidate Rankings**")
                    rows = [{"Name":_get(c,"name"),"Role":_get(c,"role"),"Seniority":_get(c,"seniority"),
                             "Score":round(_get(c,"composite_score",0),3),"Utilization":f"{_get(c,'utilization_percent',0):.0f}%"}
                            for c in da.candidate_rankings[:5]]
                    st.dataframe(_pd.DataFrame(rows), width='stretch', hide_index=True)
            else:
                st.info("No DA output")
            st.markdown('</div></div>', unsafe_allow_html=True)

            # ── RRA Section ───────────────────────────────────────────────────
            st.markdown('<div class="agent-section">', unsafe_allow_html=True)
            _sec_header("RRA", "Risk Assessment (RRA)")
            st.markdown('<div class="agent-section-body">', unsafe_allow_html=True)
            rra = result.risk_output
            if rra:
                _sev_color = {
                    "critical": ("#FECACA", "#7F1D1D", "#F87171"),
                    "high":     ("#FEE2E2", "#B91C1C", "#FCA5A5"),
                    "medium":   ("#FEF3C7", "#B45309", "#FCD34D"),
                    "low":      ("#DCFCE7", "#15803D", "#86EFAC"),
                }
                _proceed_color = {
                    "proceed":  ("#DCFCE7", "#15803D", "#86EFAC"),
                    "caution":  ("#FEF3C7", "#B45309", "#FCD34D"),
                    "hold":     ("#FECACA", "#7F1D1D", "#F87171"),
                }

                level   = (rra.overall_risk_level or "low").lower()
                proceed = (rra.can_proceed or "proceed").lower()
                op_ctx  = (rra.operating_context or "full").lower()

                # ── Verdict banner ──────────────────────────────────────────
                # Mirror the RRA standalone dashboard's "Hold — Action Required"
                # framing — the verdict is the single most communicative thing
                # the agent produces, so it leads.
                verdict_text = {
                    "proceed": "Proceed — Clear",
                    "caution": "Caution — Review Required",
                    "hold":    "Hold — Action Required",
                }.get(proceed, f"{proceed.title()} — see details")
                verdict_accent = {
                    "proceed": "#15803D",
                    "caution": "#B45309",
                    "hold":    "#B91C1C",
                }.get(proceed, "#475569")

                pills_html = (
                    _pill(f"{level} risk".upper(),
                          _sev_color.get(level, _sev_color["low"]))
                    + " "
                    + _pill(proceed.upper(),
                            _proceed_color.get(proceed, _proceed_color["caution"]))
                    + " "
                    + _pill(f"{op_ctx} context".upper(),
                            ("#F8FAFC", "#475569", "#CBD5E1"))
                )
                escalation_line = (
                    f'<div style="font-size:13px;color:#475569;margin-top:8px;">'
                    f'Escalation: <strong>{rra.escalation_target}</strong></div>'
                    if rra.escalate_to_human and rra.escalation_target else ""
                )
                st.markdown(
                    f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
                    f'border-left:3px solid {verdict_accent};border-radius:3px;'
                    f'padding:14px 18px;margin-bottom:14px;">'
                    f'<div style="font-size:10px;letter-spacing:1.5px;'
                    f'color:#64748B;font-weight:600;text-transform:uppercase;">Verdict</div>'
                    f'<div style="font-size:20px;font-weight:700;color:#0F172A;'
                    f'margin-top:4px;letter-spacing:-0.3px;">{verdict_text}</div>'
                    f'<div style="margin-top:10px;">{pills_html}</div>'
                    f'{escalation_line}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # ── 5 metric tiles ──────────────────────────────────────────
                _items = getattr(rra, "risk_items", None) or []
                n_risks    = len(_items)
                n_blocking = sum(1 for i in _items if i.get("blocking"))

                # SLA — derived from task_intake.due_date if present
                sla_value, sla_sub = "—", ""
                ti = getattr(result, "task_intake", None)
                _due_raw = getattr(ti, "due_date", None) if ti else None
                if _due_raw:
                    try:
                        from datetime import datetime as _dt, timezone as _tz
                        _due = _dt.fromisoformat(str(_due_raw).replace("Z", "+00:00"))
                        if _due.tzinfo is None:
                            _due = _due.replace(tzinfo=_tz.utc)
                        _now = _dt.now(_tz.utc)
                        _delta = _due - _now
                        _hrs = _delta.total_seconds() / 3600
                        if _hrs < 0:
                            d, h = divmod(int(-_hrs), 24)
                            sla_value = f"BREACHED · -{d}D {h}H"
                            sla_sub   = f"Was due {_due.strftime('%Y-%m-%d %H:%M')} UTC"
                        else:
                            d, h = divmod(int(_hrs), 24)
                            sla_value = f"OK · {d}D {h}H"
                            sla_sub   = f"Due {_due.strftime('%Y-%m-%d %H:%M')} UTC"
                    except Exception:
                        pass

                # Sources — from CSA validation
                src_value, src_sub = "—", ""
                csa_out = getattr(result, "csa_output", None)
                if csa_out is not None:
                    val = getattr(csa_out, "validation", None)
                    if val is not None:
                        ts  = getattr(val, "total_sources", None)
                        cs  = getattr(val, "confidence_score", None)
                        if ts is not None:
                            src_value = str(ts)
                        if cs is not None:
                            src_sub = f"{int(round(cs * 100))}% confidence"

                # Decision engine — model + timestamp
                eng_value, eng_sub = (rra.model_used or "—"), ""
                if rra.timestamp:
                    eng_sub = str(rra.timestamp)[:19].replace("T", " ") + " UTC"

                # History events — from CSA case_history rows
                hist_count = 0
                if csa_out is not None:
                    ctx = getattr(csa_out, "context", None)
                    if ctx is not None:
                        hist = getattr(ctx, "case_history", None) or []
                        hist_count = len(hist)

                t1, t2, t3, t4, t5 = st.columns(5)
                t1.metric("Risks Detected", n_risks,
                          delta=f"{n_blocking} blocking" if n_blocking else None,
                          delta_color="inverse")
                t2.metric("Sources", src_value, delta=src_sub or None,
                          delta_color="off")
                t3.metric("SLA", sla_value, delta=sla_sub or None,
                          delta_color="inverse" if sla_value.startswith("BREACHED") else "off")
                t4.metric("Case History", hist_count,
                          delta=f"{hist_count} events" if hist_count else None,
                          delta_color="off")
                t5.metric("Decision Engine", eng_value, delta=eng_sub or None,
                          delta_color="off")

                # ── Reasoning + Severity Distribution ───────────────────────
                col_reason, col_chart = st.columns([2, 1])
                with col_reason:
                    st.markdown("**Reasoning summary**")
                    st.markdown(
                        rra.reasoning_summary or
                        "_No detailed reasoning emitted by the detector._"
                    )

                with col_chart:
                    if _items:
                        st.markdown("**Severity distribution**")
                        _order = ["critical", "high", "medium", "low"]
                        _counts = {sev: 0 for sev in _order}
                        for it in _items:
                            s = (it.get("severity") or "low").lower()
                            if s in _counts:
                                _counts[s] += 1
                        import pandas as _pd
                        _df = _pd.DataFrame(
                            {"count": [_counts[s] for s in _order]},
                            index=_order,
                        )
                        st.bar_chart(_df, height=180)

                # ── Per-item breakdown ──────────────────────────────────────
                if _items:
                    st.markdown("**Risk Items**")
                    for it in _items:
                        rtype     = (it.get("risk_type") or "unknown").replace("_", " ").title()
                        sev       = (it.get("severity") or "low").lower()
                        reason    = it.get("reason") or ""
                        blocking  = bool(it.get("blocking"))
                        sev_pill  = _pill(sev.upper(), _sev_color.get(sev, _sev_color["low"]))
                        block_bit = (
                            " " + _pill("BLOCKING", ("#FECACA", "#7F1D1D", "#F87171"))
                            if blocking else ""
                        )
                        with st.container(border=True):
                            st.markdown(
                                f"**{rtype}** &nbsp; {sev_pill}{block_bit}",
                                unsafe_allow_html=True,
                            )
                            if reason:
                                st.markdown(reason)
                elif rra.risk_flags:
                    # Legacy fallback when risk_items isn't forwarded
                    st.markdown("**Risk Flags**")
                    st.markdown(
                        " ".join(_pill(f, ("#FEE2E2", "#B91C1C", "#FCA5A5"))
                                 for f in rra.risk_flags),
                        unsafe_allow_html=True,
                    )

                # ── Footer — provenance ────────────────────────────────────
                _foot: list[str] = []
                if rra.priority:
                    _foot.append(f"**Priority:** {rra.priority}")
                if rra.workflow_state:
                    _foot.append(f"**Workflow state:** {rra.workflow_state}")
                if rra.operating_context:
                    _foot.append(f"**Operating context:** {rra.operating_context}")
                if rra.task_id:
                    _foot.append(f"**Task ID:** `{rra.task_id}`")
                if _foot:
                    st.caption(" &nbsp;·&nbsp; ".join(_foot))
            else:
                st.info("No RRA output")
            st.markdown('</div></div>', unsafe_allow_html=True)

            # ── GPA Section ───────────────────────────────────────────────────
            st.markdown('<div class="agent-section">', unsafe_allow_html=True)
            _sec_header("GPA", "Governance & Policy (GPA)")
            st.markdown('<div class="agent-section-body">', unsafe_allow_html=True)
            gpa = result.governance_output
            if gpa:
                dec   = (gpa.decision or "APPROVE").upper()
                badge = _pill(dec, _DECISION_COLORS.get(dec, ("#F1F5F9", "#475569", "#E2E8F0")))
                conf_pct = int((gpa.confidence or 0)*100)
                st.markdown(f"Decision: {badge}", unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                c1.metric("Confidence", f"{conf_pct}%")
                c1.metric("Requires Approval", "Yes" if gpa.requires_approval else "No")
                approvers = ", ".join(gpa.approvers) if gpa.approvers else "None"
                c2.metric("Approvers", approvers)
                if gpa.reason: st.caption(gpa.reason)
                if gpa.matched_rule_ids: st.markdown(f"**Matched Rules:** {gpa.matched_rule_ids}")
            else:
                st.info("No GPA output")
            st.markdown('</div></div>', unsafe_allow_html=True)

            # ── IAA Section ───────────────────────────────────────────────────
            st.markdown('<div class="agent-section">', unsafe_allow_html=True)
            _sec_header("IAA", "Intent Anticipation (IAA)")
            st.markdown('<div class="agent-section-body">', unsafe_allow_html=True)
            iaa = result.iaa_output
            if iaa:
                rec = iaa.recommended_action
                if rec:
                    conf = rec.confidence if rec.confidence is not None else 0.0
                    st.markdown(f"**Recommended:** {rec.label} `{conf:.0%}`")
                    st.caption(rec.reasoning or "")
                actions = iaa.predicted_actions or []
                if not actions and iaa.recommended_action: actions = [iaa.recommended_action]
                if actions:
                    st.markdown("**Predicted Actions**")
                    for pa in actions[:4]:
                        st.markdown(f"- **{pa.label}** `{pa.confidence:.0%}` — {pa.reasoning}")
                if iaa.workflow_timeline:
                    st.markdown("**Workflow Timeline**")
                    for step in iaa.workflow_timeline:
                        s = step.model_dump(mode="json")
                        status_icon = {"completed":"✓","current":"▶","predicted":"○"}.get(s.get("status",""),"·")
                        st.markdown(f"{status_icon} **Step {s.get('step','?')}** — {s.get('event_type','—')} ({s.get('actor') or 'system'}) [{s.get('status','')}]")
                if iaa.task_list:
                    import pandas as _pd
                    st.markdown("**Task List**")
                    rows = [{"Task ID":t.task_id,"Action":t.action,"Assigned Role":t.assigned_role or "—","Priority":t.priority} for t in iaa.task_list]
                    st.dataframe(_pd.DataFrame(rows), width='stretch', hide_index=True)
                st.caption(f"model_used: {iaa.model_used}")
            else:
                st.info("No IAA output")
            st.markdown('</div></div>', unsafe_allow_html=True)

            # ── SWA Section ───────────────────────────────────────────────────
            st.markdown('<div class="agent-section">', unsafe_allow_html=True)
            _sec_header("SWA", "Surveillance (SWA)")
            st.markdown('<div class="agent-section-body">', unsafe_allow_html=True)
            swa = result.swa_result
            if swa:
                m  = swa.metrics; wa = swa.window_analyzed
                c1, c2, c3 = st.columns(3)
                c1.metric("Patterns Detected",  m.patterns_detected  if m else 0)
                c2.metric("Escalations Raised",  m.escalations_raised if m else 0)
                c3.metric("Events Processed",    m.events_processed   if m else 0)
                st.caption(f"Window: {wa.start if wa else '—'} → {wa.end if wa else '—'}")
                findings = swa.findings or []
                st.markdown(f"**Findings** ({len(findings)})")
                if findings:
                    for f in findings:
                        fd = f.model_dump(mode="json") if hasattr(f,"model_dump") else f
                        with st.expander(f"{fd.get('pattern_type','—')} — confidence {fd.get('confidence',0):.0%}"):
                            st.markdown(fd.get("description") or fd.get("pattern_signature") or "—")
                else:
                    st.caption("No patterns detected.")
            else:
                st.info("SWA runs non-blocking — output may appear after workflow completes.")
            st.markdown('</div></div>', unsafe_allow_html=True)

            # ── Errors + Latency ──────────────────────────────────────────────
            if result.stage_errors:
                st.warning(str(result.stage_errors))

            if result.latency_log:
                st.markdown(
                    '<div style="background:#0F172A;border:1px solid #1F2937;border-radius:10px;padding:14px 18px;margin-top:8px;">'
                    '<div style="font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:10px;">Agent Latency</div>',
                    unsafe_allow_html=True,
                )
                cols = st.columns(len(result.latency_log))
                for col, (agent, ms) in zip(cols, sorted(result.latency_log.items(), key=lambda x: x[1], reverse=True)):
                    c = _SEC_COLORS.get(agent.upper(), "#475569")
                    col.markdown(
                        f'<div style="text-align:center;">'
                        f'<div style="font-size:18px;font-weight:700;color:{c};">{ms:,.0f}</div>'
                        f'<div style="font-size:10px;color:#475569;text-transform:uppercase;">{agent.upper()} ms</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# RIGHT — Orchestration Log + Suggested Next Actions
# ═══════════════════════════════════════════════════════════════

with right_col:
    # ── Collapsed status bar ────────────────────────────────────────────────
    log_msgs = st.session_state.log_messages
    last_msg = log_msgs[-1]["text"][:55] + "…" if log_msgs else "Waiting for workflow…"
    sys_color = "#4ADE80" if not any(m["color"]=="red" for m in log_msgs[-5:]) else "#EF4444"
    dot_color = sys_color

    st.markdown(
        f'<div class="status-bar" style="margin-bottom:12px;">'
        f'<span class="status-dot" style="background:{dot_color};"></span>'
        f'<span style="color:#94A3B8;font-size:11px;">System: <span style="color:{sys_color};">{"Healthy" if sys_color=="#4ADE80" else "Alert"}</span></span>'
        f'<span style="color:#334155;">|</span>'
        f'<span style="color:#475569;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:180px;">{last_msg}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Suggested Next Actions (main focus) ──────────────────────────────────
    st.markdown(
        '<div style="font-size:13px;font-weight:700;color:#94A3B8;letter-spacing:1px;'
        'text-transform:uppercase;margin-bottom:10px;">Suggested Actions</div>',
        unsafe_allow_html=True,
    )
    sugg_container = st.empty()
    st.session_state["_sugg_container_ref"] = sugg_container
    result = st.session_state.workflow_result
    _render_suggested_actions(result.iaa_output if result else None, sugg_container)

    # ── Terminal drawer ───────────────────────────────────────────────────────
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)
    with st.expander("⚙  System Logs", expanded=False):
        log_container = st.empty()
        st.session_state["_log_container_ref"] = log_container
        _render_log(st.session_state.log_messages, log_container)
        st.markdown(
            '<span style="font-size:10px;font-family:\'Courier New\',monospace;">'
            '<span style="color:#60A5FA;">●</span> INFO &nbsp;'
            '<span style="color:#4ADE80;">●</span> SUCCESS &nbsp;'
            '<span style="color:#F87171;">●</span> ERROR'
            '</span>',
            unsafe_allow_html=True,
        )
