"""
api.py
FastAPI REST interface for the IAA.

Endpoints:
  POST /predict   — run the IAA on a ProcessState, return ActionRecommendation
  POST /ingest    — add documents to the corpus at runtime
  POST /workflow  — run the full orchestrator pipeline, return SharedWorkflowState
  GET  /health    — liveness check
  GET  /corpus    — corpus stats
  GET  /demo      — sample request body

Run locally:
  uvicorn agent.api:app --reload --port 8000
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import os, json, time

from .schemas import ProcessState, ActionRecommendation, EventLogEntry
from .iaa import run_iaa, build_process_state

app = FastAPI(
    title="Intent Anticipation Agent (IAA)",
    description="Predicts next process actions from current workflow state. Part of Project AMP.",
    version="0.2.0",
)


# ── Request / Response models ─────────────────────────────────────────────────

class PredictRequest(BaseModel):
    """
    Two ways to call the IAA:
    1. Pass a pre-built process_state directly (for LangGraph / agent-to-agent)
    2. Pass raw events and let the IAA build the state (for direct API callers)
    """
    process_state: Optional[ProcessState] = None
    events: Optional[list[EventLogEntry]] = None
    context_summary:    Optional[str]       = None
    risk_flags:         Optional[list[str]] = None
    risk_severity:      Optional[str]       = None
    policy_constraints: Optional[list[str]] = None
    assigned_owner:     Optional[str]       = None
    domain_filter:      Optional[str]       = None
    process_type_filter:Optional[str]       = None

    class Config:
        json_schema_extra = {
            "example": {
                "events": [
                    {
                        "event_id":  "e1",
                        "entity_id": "CASE-001",
                        "event_type":"document_submitted",
                        "stage":     "intake",
                        "timestamp": "2026-04-01T09:00:00Z",
                        "metadata":  {}
                    },
                    {
                        "event_id":  "e2",
                        "entity_id": "CASE-001",
                        "event_type":"documentation_incomplete",
                        "stage":     "verification",
                        "timestamp": "2026-04-01T09:15:00Z",
                        "metadata":  {"amount": 15000}
                    }
                ],
                "risk_flags":   ["missing_required_attachment"],
                "risk_severity":"medium"
            }
        }


class PredictResponse(BaseModel):
    recommendation: ActionRecommendation
    latency_ms: float
    corpus_size: Optional[int] = None


class IngestRequest(BaseModel):
    documents: list[str]
    metadatas: list[dict]
    source:       str = "runtime"
    domain:       str = "generic"
    process_type: str = "generic_workflow"


class CorpusStats(BaseModel):
    document_count: int
    persist_dir: str
    collection_name: str


class WorkflowRequest(BaseModel):
    """Request body for POST /workflow — full orchestrator pipeline."""
    events: list[EventLogEntry]
    entity_id: str

    class Config:
        json_schema_extra = {
            "example": {
                "entity_id": "CASE-001",
                "events": [
                    {
                        "event_id":  "e1",
                        "entity_id": "CASE-001",
                        "event_type":"document_submitted",
                        "stage":     "intake",
                        "timestamp": "2026-04-01T09:00:00Z",
                        "metadata":  {}
                    },
                    {
                        "event_id":  "e2",
                        "entity_id": "CASE-001",
                        "event_type":"documentation_incomplete",
                        "stage":     "verification",
                        "timestamp": "2026-04-01T09:15:00Z",
                        "metadata":  {}
                    }
                ]
            }
        }


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Pre-warm the LLM and retriever on startup to reduce first-call latency."""
    import agent.iaa as iaa_module
    try:
        from .retriever import IAARetriever
        from .chain import get_llm
        iaa_module._retriever = IAARetriever()
        iaa_module._llm       = get_llm()
        print("[api] IAA warmed up successfully")
    except Exception as e:
        print(f"[api] Warm-up warning: {e} — will lazy-init on first request")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status":    "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider":  os.getenv("LLM_PROVIDER", "gemini"),
    }


@app.get("/corpus", response_model=CorpusStats)
def corpus_stats():
    """Return stats about the current Qdrant corpus."""
    try:
        from .ingest import get_qdrant_client, ensure_collection, COLLECTION, QDRANT_PATH
        client = get_qdrant_client()
        ensure_collection(client)
        count = client.count(collection_name=COLLECTION).count
        return CorpusStats(
            document_count=count,
            persist_dir=QDRANT_PATH,
            collection_name=COLLECTION,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Corpus unavailable: {e}")


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    """
    Run the IAA and return a ranked action recommendation.
    Accepts either a pre-built ProcessState or a raw list of EventLogEntry objects.
    Response includes task_list and workflow_timeline in the recommendation body.
    """
    t0 = time.time()

    if req.process_state is not None:
        state = req.process_state
    elif req.events is not None and len(req.events) > 0:
        try:
            state = build_process_state(
                req.events,
                context_summary=req.context_summary,
                risk_flags=req.risk_flags,
                risk_severity=req.risk_severity,
                policy_constraints=req.policy_constraints,
                assigned_owner=req.assigned_owner,
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not build ProcessState: {e}")
    else:
        raise HTTPException(
            status_code=422,
            detail="Must provide either 'process_state' or 'events' in request body"
        )

    try:
        recommendation = run_iaa(
            state,
            domain_filter=req.domain_filter,
            process_type_filter=req.process_type_filter,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"IAA chain failed: {e}")

    latency_ms = (time.time() - t0) * 1000

    corpus_size = None
    try:
        from .ingest import get_qdrant_client, ensure_collection, COLLECTION
        client = get_qdrant_client()
        ensure_collection(client)
        corpus_size = client.count(collection_name=COLLECTION).count
    except Exception:
        pass

    return PredictResponse(
        recommendation=recommendation,
        latency_ms=round(latency_ms, 1),
        corpus_size=corpus_size,
    )


@app.post("/ingest")
def ingest_documents(req: IngestRequest, background_tasks: BackgroundTasks):
    """
    Add documents to the IAA corpus at runtime.
    Runs embedding in the background so the response is immediate.
    """
    def _do_ingest():
        try:
            from .ingest import get_qdrant_client, ensure_collection, _batch_add, _make_id
            client = get_qdrant_client()
            ensure_collection(client)
            ids  = [_make_id(d, req.source) for d in req.documents]
            meta = []
            for m in req.metadatas:
                base = {"source": req.source, "domain": req.domain, "process_type": req.process_type}
                base.update(m)
                meta.append(base)
            _batch_add(client, req.documents, ids, meta)
            print(f"[api] Background ingest complete: {len(req.documents)} docs")
        except Exception as e:
            print(f"[api] Background ingest failed: {e}")

    background_tasks.add_task(_do_ingest)
    return {
        "status":     "accepted",
        "n_documents": len(req.documents),
        "message":    "Embedding in background — documents will be available shortly"
    }


@app.post("/workflow")
def run_workflow_endpoint(req: WorkflowRequest):
    """
    Run the full multi-agent orchestrator pipeline.

    Pipeline: CSA → RRA → IAA → Delegation (unless escalated to human)

    Returns the complete SharedWorkflowState as JSON, including all agent outputs,
    the IAA recommendation (with task_list and workflow_timeline), and delegation results.
    """
    try:
        from orchestrator.orchestrator import run_workflow
        result = run_workflow(req.events, req.entity_id)

        # Serialise: convert Pydantic models to dicts for JSON response
        def _serialise(obj):
            if hasattr(obj, "model_dump"):
                return obj.model_dump(mode="json")
            if isinstance(obj, list):
                return [_serialise(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _serialise(v) for k, v in obj.items()}
            return obj

        return _serialise(dict(result))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow pipeline failed: {e}")


# ── Demo helper ───────────────────────────────────────────────────────────────

@app.get("/demo")
def demo_request():
    """Returns a sample request body you can copy-paste into /predict or /workflow."""
    sample_events = [
        {
            "event_id":  "e1",
            "entity_id": "DEMO-CASE-001",
            "event_type":"document_submitted",
            "stage":     "intake",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata":  {}
        },
        {
            "event_id":  "e2",
            "entity_id": "DEMO-CASE-001",
            "event_type":"documentation_incomplete",
            "stage":     "verification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata":  {"amount": 15000}
        }
    ]
    return {
        "hint": "POST the predict_body to /predict or workflow_body to /workflow",
        "predict_body": {
            "events":        sample_events,
            "risk_flags":    ["missing_required_attachment"],
            "risk_severity": "medium"
        },
        "workflow_body": {
            "entity_id": "DEMO-CASE-001",
            "events":    sample_events,
        }
    }
