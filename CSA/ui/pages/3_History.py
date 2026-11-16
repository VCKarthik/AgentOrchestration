import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import streamlit as st, json
from core.context_stitcher import get_output_history, load_output
from core.db_schema import get_connection

st.set_page_config(page_title="History — CSA", page_icon="📋", layout="wide")
st.title("📋 Output History")

def delete_run(run_id, output_path):
    try:
        if output_path and os.path.exists(output_path):
            os.remove(output_path)
        conn = get_connection()
        conn.execute("DELETE FROM query_runs WHERE run_id=?", (run_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False

runs = get_output_history()

if not runs:
    st.info("No runs yet. Go to 🔍 Query to generate your first context packet.")
else:
    st.success(f"{len(runs)} run(s) found")

    if "selected_runs" not in st.session_state:
        st.session_state["selected_runs"] = []

    col1, col2, col3 = st.columns([2, 2, 4])
    with col1:
        if st.button("☑️ Select All"):
            st.session_state["selected_runs"] = [r["run_id"] for r in runs]
            st.rerun()
    with col2:
        if st.button("⬜ Deselect All"):
            st.session_state["selected_runs"] = []
            st.rerun()
    with col3:
        selected_count = len(st.session_state["selected_runs"])
        if st.button(f"🗑️ Delete Selected ({selected_count})",
                     type="primary",
                     disabled=selected_count == 0,
                     use_container_width=True):
            deleted = 0
            for r in runs:
                if r["run_id"] in st.session_state["selected_runs"]:
                    if delete_run(r["run_id"], r.get("output_path")):
                        deleted += 1
            st.session_state["selected_runs"] = []
            st.success(f"Deleted {deleted} run(s).")
            st.rerun()

    st.markdown("---")

    for r in runs:
        conf = r.get("confidence") or 0
        is_selected = r["run_id"] in st.session_state["selected_runs"]

        col1, col2 = st.columns([0.3, 9.7])
        with col1:
            checked = st.checkbox("", value=is_selected, key=f"chk_{r['run_id']}")
            if checked and r["run_id"] not in st.session_state["selected_runs"]:
                st.session_state["selected_runs"].append(r["run_id"])
            elif not checked and r["run_id"] in st.session_state["selected_runs"]:
                st.session_state["selected_runs"].remove(r["run_id"])

        with col2:
            with st.expander(f"🗂️ `{r['run_id']}` — {r.get('case_id') or 'None'} — {r['timestamp'][:19]}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Sources",    r.get("total_sources", 0))
                c2.metric("Confidence", f"{conf*100:.0f}%")
                c3.markdown(f"**Query:** {r.get('task_query') or '-'}")

                packet = load_output(r["run_id"])
                if packet:
                    json_str = json.dumps(packet, indent=2)
                    ca, cb = st.columns(2)
                    ca.download_button("⬇️ Download JSON", json_str,
                        f"{r['run_id']}.json", "application/json",
                        key=f"dl_{r['run_id']}")
                    if cb.button("👁️ Preview", key=f"pv_{r['run_id']}"):
                        st.code(json_str[:3000], language="json")
                else:
                    st.warning("File not found on disk.")