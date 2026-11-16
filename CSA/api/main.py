import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import query, ingest, records
from core.db_schema import init_db

init_db()

app = FastAPI(title="Context Stitching Agent (CSA)", version="2.0.0", docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(query.router,   tags=["Query"])
app.include_router(ingest.router,  tags=["Ingest"])
app.include_router(records.router, tags=["Records"])

@app.get("/")
def root():
    return {"name":"CSA","version":"2.0.0","docs":"/docs","main":"POST /query"}