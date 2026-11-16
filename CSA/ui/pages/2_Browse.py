import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import streamlit as st, pandas as pd
from core.db_schema import init_db
from core.retrieval_engine import get_all_records

init_db()
st.set_page_config(page_title="Browse DB — CSA", page_icon="🗄️", layout="wide")
st.title("🗄️ Browse Database")
if st.button("🔄 Refresh"): st.rerun()

t1,t2,t3,t4 = st.tabs(["📧 Emails","📄 Documents","📅 Calendar","🗂️ History"])

with t1:
    rows = get_all_records("emails")
    if rows:
        fc = st.selectbox("Filter Case",["All"]+sorted(set(r["case_id"] for r in rows)))
        if fc != "All": rows = [r for r in rows if r["case_id"]==fc]
        df = pd.DataFrame([{
            "ID":          r["id"],
            "Case":        r["case_id"],
            "Type":        r["case_type"],
            "Subject":     r["subject"],
            "From":        r["sender"],
            "To":          r["recipients"],
            "Date":        r["date"],
            "Attachments": r.get("attachments",""),
            "Thread":      r.get("thread_id",""),
        } for r in rows])
        st.dataframe(df, use_container_width=True)
        for r in rows:
            with st.expander(f"📧 {r['subject']} | {r['case_id']}"):
                st.markdown(f"**Body:** {r['body']}")
                if r.get("file_link"): st.markdown(f"📁 [Open]({r['file_link']})")
    else:
        st.info("No emails.")

with t2:
    rows = get_all_records("documents")
    if rows:
        c1,c2 = st.columns(2)
        fc = c1.selectbox("Filter Case",["All"]+sorted(set(r["case_id"] for r in rows)),key="df")
        ft = c2.selectbox("Filter Type",["All"]+sorted(set(r["file_type"] for r in rows)),key="dt")
        if fc!="All": rows=[r for r in rows if r["case_id"]==fc]
        if ft!="All": rows=[r for r in rows if r["file_type"]==ft]
        df = pd.DataFrame([{
            "ID":          r["id"],
            "Case":        r["case_id"],
            "Type":        r["case_type"],
            "Filename":    r["filename"],
            "File Type":   r["file_type"],
            "Description": r.get("description",""),
            "Tags":        r.get("tags",""),
            "Date":        r.get("created_at",""),
        } for r in rows])
        st.dataframe(df, use_container_width=True)
        for r in rows:
            with st.expander(f"📄 {r['filename']} | {r['case_id']}"):
                st.markdown(f"**Description:** {r.get('description','-')}")
                if r.get("file_path"): st.code(r["file_path"], language=None)
                if r.get("file_link"): st.markdown(f"📁 [Open]({r['file_link']})")
    else:
        st.info("No documents.")

with t3:
    rows = get_all_records("calendar_events")
    if rows:
        fc = st.selectbox("Filter Case",["All"]+sorted(set(r["case_id"] for r in rows)),key="cf")
        if fc!="All": rows=[r for r in rows if r["case_id"]==fc]
        df = pd.DataFrame([{
            "ID":        r["id"],
            "Case":      r["case_id"],
            "Type":      r["case_type"],
            "Title":     r["title"],
            "Start":     r["start_time"],
            "End":       r["end_time"],
            "Location":  r.get("location",""),
            "Status":    r["status"],
        } for r in rows])
        st.dataframe(df, use_container_width=True)
        for r in rows:
            with st.expander(f"📅 {r['title']} | {r['case_id']}"):
                st.markdown(f"**Start:** {r['start_time']}  **End:** {r['end_time']}")
                st.markdown(f"**Location:** {r.get('location','-')}")
                st.markdown(f"**Status:** `{r['status']}`")
                att = r.get("attendees","")
                if att: st.markdown(f"**Attendees:** {att}")
                if r.get("description"): st.markdown(f"**Notes:** {r['description']}")
    else:
        st.info("No calendar events.")

with t4:
    rows = get_all_records("case_history")
    if rows:
        c1,c2 = st.columns(2)
        fc = c1.selectbox("Filter Case",["All"]+sorted(set(r["case_id"] for r in rows)),key="hf")
        fs = c2.selectbox("Filter Status",["All"]+sorted(set(r["status"] for r in rows)),key="hs")
        if fc!="All": rows=[r for r in rows if r["case_id"]==fc]
        if fs!="All": rows=[r for r in rows if r["status"]==fs]
        df = pd.DataFrame([{
            "ID":        r["id"],
            "Case":      r["case_id"],
            "Type":      r["case_type"],
            "Event":     r["event_type"],
            "Actor":     r["actor"],
            "Timestamp": r["timestamp"],
            "Status":    r["status"],
        } for r in rows])
        st.dataframe(df, use_container_width=True)
        for r in rows:
            icon = {"open":"🟢","pending":"🟡","escalated":"🔴","resolved":"✅"}.get(r["status"],"⚪")
            with st.expander(f"{icon} [{r['event_type'].upper()}] {r['timestamp'][:10]} | {r['case_id']}"):
                st.markdown(f"**Actor:** {r['actor']}")
                st.markdown(f"**Status:** `{r['status']}`")
                st.markdown(f"**Notes:** {r['notes']}")
    else:
        st.info("No case history.")