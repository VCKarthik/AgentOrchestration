"""
Risk Radar Agent — FastAPI HTTP server.

Exposes the RiskRadarAgent over HTTP so the LangGraph orchestrator can call it
on port 8002 like any other Stage 2 agent.

Endpoints:
  GET  /health   — liveness probe
  POST /predict  — run risk evaluation; accepts csa_to_rra() payload shape
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .agent import RiskRadarAgent
from .schema import CaseInput

app = FastAPI(title="Risk Radar Agent")

_agent = RiskRadarAgent()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict")
def predict(payload: dict):
    try:
        case = CaseInput.from_dict(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid payload: {exc}") from exc

    try:
        output = _agent.evaluate(case)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Evaluation error: {exc}") from exc

    return output.to_dict()
