# 🚀 CSA — Getting Started Guide

This guide is for a new developer setting up the Context Stitching Agent (CSA) on their machine from scratch.

---

## What You Need Before Starting

| Requirement | Version | How to check |
|---|---|---|
| Python | 3.10 or higher | `python3 --version` |
| pip | Latest | `pip --version` |
| VS Code | Any | Download from code.visualstudio.com |
| Git | Any | `git --version` |

---

## Step 1 — Get the Code

If you received the project as a ZIP file:
```bash
unzip AMP-CSA.zip
cd AMP-CSA
```

If cloning from a repo:
```bash
git clone <repo-url>
cd AMP-CSA
```

---

## Step 2 — Check Your Folder Structure

Open the project in VS Code:
```bash
code .
```

You should see this structure:
```
AMP-CSA/
├── api/
│   ├── main.py
│   └── routes/
│       ├── query.py
│       ├── ingest.py
│       └── records.py
├── core/
│   ├── db_schema.py
│   ├── retrieval_engine.py
│   ├── metadata_extractor.py
│   ├── embedding_engine.py
│   ├── qdrant_manager.py
│   ├── hybrid_retriever.py
│   └── context_stitcher.py
├── ui/
│   ├── app.py
│   └── pages/
│       ├── 1_Query.py
│       ├── 2_Browse.py
│       ├── 3_History.py
│       └── 4_DB_Tables.py
├── data/               ← may not exist yet, create it below
├── requirements.txt
└── README.md
```

---

## Step 3 — Create Data Folders

These folders are needed for the database and file storage:
```bash
mkdir -p data/files/documents data/files/emails data/files/attachments data/outputs
```

---

## Step 4 — Install Dependencies

```bash
pip install -r requirements.txt
```

This installs everything — FastAPI, Streamlit, Qdrant, sentence-transformers, and more.

> **Note:** The sentence-transformers model (`all-MiniLM-L6-v2`, 22MB) downloads automatically the first time you run the server. You need internet for the first run only. After that it's cached locally.

---

## Step 5 — Start the API Server

Open a terminal in VS Code (`Ctrl + `` ` ``) and run:

```bash
uvicorn api.main:app --reload --port 8000
```

You should see output like this:
```
[DB] Seed data inserted.
[DB] Initialized at .../data/csa.db
[Qdrant] Client ready (in-memory).
[Qdrant] Collections ready.
[Embedding] Loading model...
[Embedding] Model ready.
[Qdrant] Indexed 6 emails.
[Qdrant] Indexed 8 documents.
[Qdrant] Indexed 4 calendar_events.
[Qdrant] Indexed 8 case_history.
[Qdrant] Total: 26 records indexed.
INFO: Uvicorn running on http://127.0.0.1:8000
```

> If you see all of the above — the server is running correctly.

---

## Step 6 — Start the Streamlit UI

Open a **second terminal** (keep the first one running) and run:

```bash
streamlit run ui/app.py
```

Your browser should open automatically at `http://localhost:8501`.

---

## Step 7 — Verify Everything Works

Open your browser and check these URLs:

| URL | What you should see |
|---|---|
| http://localhost:8000/health | `{"status":"ok","db_records":{...}}` |
| http://localhost:8000/docs | Interactive API documentation |
| http://localhost:8501 | Streamlit UI home page |

---

## Step 8 — Run Your First Query

### Option A — Via Streamlit UI
1. Go to http://localhost:8501
2. Click **🔍 Query** in the sidebar
3. Click the **🤖 Structured (Agent Mode)** tab
4. Select `CASE-1001 (claim_review)` from the dropdown
5. Click **🚀 Fetch**
6. You should see 13 sources returned across Emails, Documents, Calendar, History tabs

### Option B — Via API Docs
1. Go to http://localhost:8000/docs
2. Click **POST /query**
3. Click **Try it out**
4. Paste this in the request body:
```json
{
  "case_id": "CASE-1001",
  "case_type": "claim_review"
}
```
5. Click **Execute**
6. Scroll down — you should see a full JSON context packet

### Option C — Via Terminal
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"case_id":"CASE-1001","case_type":"claim_review"}'
```

---

## Step 9 — View the Database (Optional)

Install the **SQLite Viewer** extension in VS Code:
1. Press `Cmd+Shift+X` (Mac) or `Ctrl+Shift+X` (Windows)
2. Search `SQLite Viewer`
3. Install the one by **Florian Klampfer**
4. Open `data/csa.db` in VS Code — it will show all tables visually

---

## Three Pre-loaded Test Cases

The database is automatically seeded with these cases on first startup:

| Case ID | Type | Scenario |
|---|---|---|
| `CASE-1001` | `claim_review` | Water damage to property — policy #4821 |
| `CASE-2002` | `policy_renewal` | Premium increase query — policy #7734 |
| `CASE-3003` | `fraud_investigation` | 3 theft claims in 6 months — policy #9910 |

---

## Quick Test Queries

Try these in the API docs or Streamlit UI:

```json
// Claim review
{"case_id": "CASE-1001", "case_type": "claim_review"}

// Policy renewal
{"case_id": "CASE-2002", "case_type": "policy_renewal"}

// Fraud investigation
{"case_id": "CASE-3003", "case_type": "fraud_investigation"}

// Free text — auto detects case
{"task_text": "review water damage claim for policy #4821"}

// Free text — fraud keywords
{"task_text": "suspicious theft pattern policy 9910"}
```

---

## Common Errors & Fixes

| Error | Cause | Fix |
|---|---|---|
| `unable to open database file` | `data/` folder missing | Run `mkdir -p data/files/documents data/files/emails data/files/attachments data/outputs` |
| `Connection refused` on Qdrant | Old code trying to connect to Docker | Change client to `QdrantClient(":memory:")` in `core/qdrant_manager.py` |
| `ModuleNotFoundError` | Dependencies not installed | Run `pip install -r requirements.txt` |
| `Port 8000 already in use` | Another process using the port | Run `lsof -i :8000` then `kill -9 <PID>` |
| `StreamlitPageNotFoundError` | Wrong page_link paths in app.py | Use relative paths e.g. `"pages/1_Query.py"` not `"ui/pages/1_Query.py"` |
| Embedding model download fails | No internet on first run | Connect to internet once for model download — cached after that |

---

## How to Add Your Own Test Data

**Via API Docs** (http://localhost:8000/docs):
- `POST /ingest/email` — add an email
- `POST /ingest/document` — add a document record
- `POST /ingest/calendar` — add a calendar event
- `POST /ingest/case` — add a case history entry
- `POST /ingest/upload/{case_id}/{case_type}` — upload an actual file

**Via DB Browser for SQLite** (https://sqlitebrowser.org):
- Open `data/csa.db`
- Browse Data → select table → Insert row → Write Changes

---

## Project Ports

| Service | Port | URL |
|---|---|---|
| FastAPI | 8000 | http://localhost:8000 |
| Streamlit | 8501 | http://localhost:8501 |

---

## What NOT to Change

These files are critical — changing them will break the system:

| File | Why critical |
|---|---|
| `core/db_schema.py` | Defines all table schemas — changing breaks existing DB |
| `api/routes/query.py` | Main endpoint — downstream agents depend on this |
| `core/context_stitcher.py` | Assembles the output packet — schema must stay consistent |

---

## To Stop the Servers

```bash
# Stop API server
Ctrl + C   (in Terminal 1)

# Stop Streamlit
Ctrl + C   (in Terminal 2)
```

---

## Need Help?

1. Check the full technical documentation in `CSA_Project_Book.docx`
2. Check input/output specs in `CSA_IO_Specification_With_Sample.docx`
3. Check the API docs at http://localhost:8000/docs