from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.context_stitcher import stitch, stitch_structured, get_output_history, load_output
from core.qdrant_manager import index_all_records

router = APIRouter()

try:
    index_all_records()
except Exception as e:
    print(f"[warn] Qdrant indexing skipped: {e}")

class QueryRequest(BaseModel):
    # Structured mode (downstream agents)
    case_id:   Optional[str] = None
    case_type: Optional[str] = None
    # Free text mode (UI / humans)
    task_text: Optional[str] = None
    top_k:     Optional[int] = 5

@router.post("/query")
def query(request: QueryRequest):
    """
    Mode 1 — Structured: send case_id + case_type → SQLite exact match.
    Mode 2 — Free text:  send task_text → hybrid SQLite + Qdrant.
    """
    try:
        if request.case_id and request.case_type:
            return stitch_structured(case_id=request.case_id, case_type=request.case_type)
        elif request.task_text:
            return stitch(task_text=request.task_text, top_k=request.top_k)
        else:
            raise HTTPException(400, detail="Provide (case_id + case_type) or task_text.")
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, detail=str(e))

@router.get("/outputs")
def list_outputs(): return get_output_history()

@router.get("/outputs/{run_id}")
def get_output(run_id: str):
    packet = load_output(run_id)
    if not packet: raise HTTPException(404, detail=f"Not found: {run_id}")
    return packet