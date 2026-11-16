"""
DA FastAPI service — wraps DelegationAgent on port 8005.
Does not modify DelegationAgent, Task, or AssignmentDecision.
"""
from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .agent import DelegationAgent
from .models.task import Task
from .models.outputs import AssignmentDecision

logger = logging.getLogger(__name__)

app = FastAPI(title="Delegation Agent (DA)", version="1.0.0")

# DATaskRequest = Task — the Task model is the request body directly.
DATaskRequest = Task


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "agent": "da", "version": "1.0.0"}


@app.post("/predict", response_model=AssignmentDecision)
def predict(request: DATaskRequest):
    logger.info("DA /predict: task_id=%s task_type=%s", request.task_id, request.task_type)
    try:
        decision = DelegationAgent().evaluate_task(request)
        return decision
    except Exception:
        logger.exception("DA /predict failed for task_id=%s", request.task_id)
        raise HTTPException(status_code=500, detail="DA evaluation failed — see server logs")


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8005, reload=False)
