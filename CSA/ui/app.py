import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import streamlit as st

st.set_page_config(page_title="CSA", page_icon="🧩", layout="wide")
st.sidebar.title("🧩 CSA")
st.sidebar.caption("Context Stitching Agent v2.0")
st.sidebar.markdown("---")
st.sidebar.page_link("app.py",             label="🏠 Home")
st.sidebar.page_link("pages/1_Query.py",   label="🔍 Query")
st.sidebar.page_link("pages/2_Browse.py",  label="🗄️ Browse DB")
st.sidebar.page_link("pages/3_History.py", label="📋 History")
st.sidebar.markdown("---")
st.sidebar.caption("API: http://localhost:8000")
st.sidebar.caption("Docs: http://localhost:8000/docs")

st.title("🧩 Context Stitching Agent")
col1, col2, col3 = st.columns(3)
with col1: st.info("**🔍 Query**\nFree text or structured case lookup")
with col2: st.info("**🗄️ Browse DB**\nView all records with file links")
with col3: st.info("**📋 History**\nRe-download past JSON packets")

st.markdown("### Downstream Agent — One Call")
st.code('''# Structured mode
import requests
response = requests.post("http://localhost:8000/query", json={
    "case_id": "CASE-1001",
    "case_type": "claim_review"
})
packet = response.json()

# Free text mode
response = requests.post("http://localhost:8000/query", json={
    "task_text": "review water damage claim for policy #4821"
})
packet = response.json()''', language="python")