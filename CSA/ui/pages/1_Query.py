import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import streamlit as st, json
from core.db_schema import init_db, get_all_case_ids
from core.qdrant_manager import index_all_records
from core.context_stitcher import stitch, stitch_structured

init_db()

if "qdrant_indexed" not in st.session_state:
    with st.spinner("Initializing search index..."):
        index_all_records()
    st.session_state["qdrant_indexed"] = True

st.set_page_config(page_title="Query — CSA", page_icon="🔍", layout="wide")
st.title("🔍 Query Context")

def _show_results(packet):
    st.success(f"✅ {packet['validation']['total_sources']} sources found")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Task ID",       packet["task_id"][-12:])
    c2.metric("Case ID",       packet.get("case_id") or "Not Found")
    c3.metric("Confidence",    f"{packet['validation']['confidence_score']*100:.0f}%")
    c4.metric("Total Sources", packet["validation"]["total_sources"])
    c5.metric("Method",        packet["meta"]["retrieval_method"])

    m = packet["meta"]
    st.info(f"SQL hits: `{m['sql_hits']}` | Qdrant hits: `{m['qdrant_hits']}` | Keywords: `{', '.join(m['keywords_used']) or 'N/A'}`")

    for w in packet["validation"]["warnings"]: st.warning(f"⚠️ {w}")

    st.markdown("---")
    t1,t2,t3,t4,t5 = st.tabs(["📧 Emails","📄 Documents","📅 Calendar","🗂️ History","📦 JSON"])

    with t1:
        items = packet["context"]["emails"]
        st.caption(f"{len(items)} email(s)")
        for e in items:
            badge = "🎯 Exact" if e.get("matched_by")=="exact" else f"🔍 {e.get('relevance_score',0):.2f}"
            with st.expander(f"📧 {e['subject']} — {e['date'][:10]}  {badge}"):
                st.markdown(f"**From:** {e['sender']}  **To:** {e['recipients']}")
                st.text(e["body"])
                if e.get("attachments"): st.markdown(f"**Attachments:** {', '.join(e['attachments'])}")
                if e.get("file_link"):   st.markdown(f"📁 [Open]({e['file_link']})")

    with t2:
        items = packet["context"]["documents"]
        st.caption(f"{len(items)} document(s)")
        for d in items:
            badge = "🎯 Exact" if d.get("matched_by")=="exact" else f"🔍 {d.get('relevance_score',0):.2f}"
            with st.expander(f"📄 {d['filename']} ({d['file_type'].upper()})  {badge}"):
                st.markdown(f"**Description:** {d.get('description','-')}")
                if d.get("file_path"): st.code(d["file_path"], language=None)
                if d.get("file_link"): st.markdown(f"📁 [Open]({d['file_link']})")

    with t3:
        items = packet["context"]["calendar_events"]
        st.caption(f"{len(items)} event(s)")
        for ev in items:
            badge = "🎯 Exact" if ev.get("matched_by")=="exact" else f"🔍 {ev.get('relevance_score',0):.2f}"
            with st.expander(f"📅 {ev['title']} — {ev['start_time'][:10]}  {badge}"):
                st.markdown(f"**Location:** {ev.get('location','-')}")
                att = ev.get("attendees",[])
                st.markdown(f"**Attendees:** {', '.join(att) if isinstance(att,list) else att}")
                if ev.get("description"): st.markdown(f"**Notes:** {ev['description']}")

    with t4:
        items = packet["context"]["case_history"]
        st.caption(f"{len(items)} history event(s)")
        for h in items:
            icon  = {"open":"🟢","pending":"🟡","escalated":"🔴","resolved":"✅"}.get(h["status"],"⚪")
            badge = "🎯 Exact" if h.get("matched_by")=="exact" else f"🔍 {h.get('relevance_score',0):.2f}"
            with st.expander(f"{icon} [{h['event_type'].upper()}] {h['timestamp'][:10]} — {h['actor']}  {badge}"):
                st.markdown(f"**Status:** `{h['status']}`")
                st.markdown(f"**Notes:** {h['notes']}")

    with t5:
        json_str = json.dumps(packet, indent=2)
        st.code(json_str, language="json")
        st.download_button("⬇️ Download JSON", json_str,
            f"{packet['task_id']}.json", "application/json", use_container_width=True)


free_tab, struct_tab = st.tabs(["💬 Free Text (UI)", "🤖 Structured (Agent Mode)"])

with free_tab:
    st.caption("Type anything. CSA auto-detects case ID and type.")
    col1, col2 = st.columns([4,1])
    with col1:
        task_text = st.text_area("Task Description",
            placeholder="e.g. review water damage claim for policy #4821\n"
                        "e.g. CASE-2002 renewal premium query\n"
                        "e.g. fraud suspicious theft pattern policy 9910",
            height=100, key="ft_input")
    with col2:
        top_k = st.number_input("Results per source", 1, 20, 5)
        st.markdown("<br>", unsafe_allow_html=True)
        ft_submit = st.button("🚀 Fetch", use_container_width=True, type="primary", key="ft_btn")

    with st.expander("💡 Examples"):
        for ex in ["review water damage claim for policy #4821",
                   "CASE-1001 adjuster documents inspection",
                   "policy 7734 renewal premium increase",
                   "fraud suspicious theft pattern 9910"]:
            if st.button(ex, key=f"ex_{ex}"):
                st.session_state["ft_ex"] = ex

    if "ft_ex" in st.session_state:
        task_text = st.session_state.pop("ft_ex")
        ft_submit = True

    if ft_submit and task_text.strip():
        with st.spinner("Searching SQLite + Qdrant..."):
            packet = stitch(task_text.strip(), top_k=int(top_k))
        _show_results(packet)
    elif ft_submit:
        st.warning("Please enter a task description.")

with struct_tab:
    st.caption("Direct lookup by case_id + case_type — used by downstream agents.")
    cases = get_all_case_ids()
    case_options = {f"{c['case_id']} ({c['case_type']})": c for c in cases}

    with st.form("struct_form"):
        col1, col2 = st.columns(2)
        with col1: selected = st.selectbox("Case", list(case_options.keys()))
        with col2: task_desc = st.text_input("Description (optional)")
        st_submit = st.form_submit_button("🚀 Fetch", use_container_width=True)

    if st_submit and selected:
        case = case_options[selected]
        with st.spinner("Fetching from SQLite..."):
            packet = stitch_structured(case["case_id"], case["case_type"], task_desc)
        _show_results(packet)

    st.markdown("---")
    st.markdown("**Equivalent API call:**")
    if selected:
        c = case_options.get(selected, {})
        st.code(f'''import requests
response = requests.post("http://localhost:8000/query", json={{
    "case_id": "{c.get("case_id","CASE-1001")}",
    "case_type": "{c.get("case_type","claim_review")}"
}})
packet = response.json()''', language="python")