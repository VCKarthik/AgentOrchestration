"""
Risk Radar — Streamlit UI
Run: streamlit run app.py

Input shape: a CSA (Context Stitching Agent) packet — the upstream agent's
output. The Risk Radar agent parses the packet, maps filenames to document
types, derives case fields, and evaluates risk autonomously.
"""

import json
import sys
from pathlib import Path

import streamlit as st

_here = Path(__file__).resolve().parent
_root = _here.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_here))

try:
    from risk_radar.agent import RiskRadarAgent
    from risk_radar.schema import CaseInput
    from risk_radar.packet_parser import PacketStore, parse_packet
except ModuleNotFoundError:
    from agent import RiskRadarAgent              # type: ignore
    from schema import CaseInput                  # type: ignore
    from packet_parser import PacketStore, parse_packet  # type: ignore

PACKETS = PacketStore()

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Risk Radar", page_icon="🔍", layout="wide")

st.markdown("""
<style>
.risk-badge { display:inline-block; padding:4px 14px; border-radius:20px;
              font-weight:700; font-size:0.9rem; letter-spacing:0.04em; }
.badge-low      { background:#d4edda; color:#155724; }
.badge-medium   { background:#fff3cd; color:#856404; }
.badge-high     { background:#ffe0b2; color:#7f3e00; }
.badge-critical { background:#f8d7da; color:#721c24; }
.badge-proceed  { background:#d4edda; color:#155724; }
.badge-caution  { background:#fff3cd; color:#856404; }
.badge-hold     { background:#f8d7da; color:#721c24; }
.risk-card { border-left:4px solid #dee2e6; padding:10px 14px;
             margin-bottom:10px; border-radius:0 6px 6px 0; background:#f8f9fa; }
.risk-card.critical { border-color:#dc3545; }
.risk-card.high     { border-color:#fd7e14; }
.risk-card.medium   { border-color:#ffc107; }
.risk-card.low      { border-color:#28a745; }
section[data-testid="stSidebar"] { width: 380px !important; }
</style>
""", unsafe_allow_html=True)

REGISTRY_PATH = Path(__file__).parent / "workflow_registry.json"
REGISTRY = json.loads(REGISTRY_PATH.read_text())["workflows"]

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
RISK_TYPE_LABELS = {
    "missing_input":    "📄 Missing Input",
    "deadline_risk":    "⏰ Deadline / SLA",
    "dependency_risk":  "🔗 Dependency",
    "historical_delay": "📊 Historical Delay",
    "compliance_risk":  "⚖️ Compliance",
    "coordination_risk":"👥 Coordination",
    "ambiguity_risk":   "❓ Ambiguity",
}

def severity_badge(level: str) -> str:
    return f'<span class="risk-badge badge-{level.lower()}">{level.upper()}</span>'

def proceed_badge(decision: str) -> str:
    icons = {"proceed": "✅", "caution": "⚠️", "hold": "🛑"}
    return f'<span class="risk-badge badge-{decision.lower()}">{icons.get(decision.lower(),"")} {decision.upper()}</span>'

# ── Sidebar: Packet Picker ────────────────────────────────────────────────────

with st.sidebar:
    st.title("🔍 Risk Radar")
    st.caption("Consumes a Context Stitching Agent (CSA) packet. The Risk Radar agent parses it autonomously.")
    st.divider()

    case_ids = PACKETS.list_case_ids()
    selected_id = st.selectbox("CSA Packet", case_ids,
        format_func=lambda cid: f"{cid} — {(PACKETS.get_packet(cid) or {}).get('case_type','')}")
    packet = PACKETS.get_packet(selected_id) or {}

    st.divider()
    st.markdown("**Packet Header**")
    st.write(f"task_id: `{packet.get('task_id','—')}`")
    st.write(f"case_id: `{packet.get('case_id','—')}`")
    st.write(f"case_type: `{packet.get('case_type','—')}`")
    val = packet.get("validation", {})
    st.write(f"validation: `{val.get('status','—')}` ({val.get('confidence_score','—')})")
    st.write(f"chunks: `{val.get('total_chunks','—')}`")

    st.divider()
    run_clicked = st.button("▶ Evaluate", type="primary", use_container_width=True)

# ── Main: parsed view + risk evaluation ───────────────────────────────────────

st.title("Risk Assessment")
st.caption("Phase 1 demo — sample CSA packets are synthetic; filename→document-type matching is heuristic.")

parsed = parse_packet(packet) if packet else {}

# ── Document identification (doctype-level only; raw filenames stay hidden) ──
wf_type   = parsed.get("workflow_type", "")
mandatory = set(parsed.get("mandatory_inputs", []))
received  = set(parsed.get("received_inputs", []))
got       = sorted(mandatory & received)
missing   = sorted(mandatory - received)

st.markdown("### 📁 Document Identification")
st.caption(f"Workflow `{wf_type}`. The agent identified received documents from the upstream packet.")

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(f"**Mandatory** ({len(mandatory)})")
    for d in sorted(mandatory):
        icon = "✅" if d in received else "🔴"
        st.write(f"{icon} `{d}`")
with c2:
    st.markdown(f"**Received (mandatory)** ({len(got)})")
    for d in got: st.write(f"✅ `{d}`")
    if not got: st.write("_none_")
with c3:
    st.markdown(f"**Missing Mandatory** ({len(missing)})")
    if missing:
        for d in missing: st.write(f"🔴 `{d}`")
    else:
        st.success("All mandatory received.")

st.divider()

# ── Run agent ──

if run_clicked and packet:
    with st.spinner("Agent evaluating…"):
        try:
            result = RiskRadarAgent().evaluate_packet(packet).to_dict()
            st.session_state["last_result"] = result
        except Exception as e:
            st.error(f"Agent error: {e}")
            st.session_state.pop("last_result", None)

if "last_result" in st.session_state:
    r = st.session_state["last_result"]

    col_risk, col_proceed, col_escalate, col_model = st.columns(4)
    with col_risk:
        st.markdown("**Overall Risk**")
        st.markdown(severity_badge(r["overall_risk_level"]), unsafe_allow_html=True)
    with col_proceed:
        st.markdown("**Decision**")
        st.markdown(proceed_badge(r["can_proceed"]), unsafe_allow_html=True)
    with col_escalate:
        st.markdown("**Escalate?**")
        if r["escalate_to_human"]:
            st.markdown(f"🚨 **Yes** — `{r.get('escalation_target','unknown')}`")
        else:
            st.markdown("✅ No")
    with col_model:
        st.markdown("**Context**")
        ctx = r.get("operating_context","—")
        st.markdown(f"{'🟡' if ctx == 'partial' else '🟢'} `{ctx}`")

    st.divider()
    st.markdown("**Reasoning Summary**")
    st.info(r.get("reasoning_summary", "—"))

    items = r.get("risk_items", [])
    st.markdown(f"### Risk Items ({len(items)} detected)")
    if not items:
        st.success("No risks detected — safe to proceed.")
    else:
        items_sorted = sorted(items, key=lambda x: SEVERITY_ORDER.get(x["severity"], 0), reverse=True)
        for item in items_sorted:
            sev = item["severity"]
            label = RISK_TYPE_LABELS.get(item["risk_type"], item["risk_type"].replace("_", " ").title())
            blocking = " &nbsp;🔴 **BLOCKING**" if item.get("blocking") else ""
            st.markdown(f"""
<div class="risk-card {sev}">
<strong>{label}</strong> &nbsp; {severity_badge(sev)}{blocking}<br/>
<small style="color:#555">{item['reason']}</small>
</div>""", unsafe_allow_html=True)

    if items:
        st.markdown("### Risk Breakdown")
        sev_counts = {}
        for item in items:
            sev_counts[item["severity"]] = sev_counts.get(item["severity"], 0) + 1
        ordered = {k: sev_counts[k] for k in ["critical","high","medium","low"] if k in sev_counts}
        st.bar_chart(ordered)

    with st.expander("🗂 Raw output JSON"):
        st.json(r)
else:
    st.markdown("""
<div style="color:#888; margin-top:30px; text-align:center;">
    <p style="font-size:2.5rem;">🔍</p>
    <p style="font-size:1.05rem;">Pick a CSA packet and click <strong>Evaluate</strong>.<br/>
    The Risk Radar agent will parse the upstream packet and surface risks.</p>
</div>
""", unsafe_allow_html=True)
