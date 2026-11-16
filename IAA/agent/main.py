"""
agent/main.py
ADK entry point for the Intent Anticipation Agent.
Run with: adk web
or:        adk run agent/main.py
"""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.sessions import DatabaseSessionService

# ── Tool: predict next action ────────────────────────────────────────────────
def predict_next_action(
    entity_id: str,
    current_event: str,
    current_stage: str,
    prior_actions: list[str],
    risk_severity: str = "unknown",
    risk_flags: list[str] = None,
    context_summary: str = None,
) -> dict:
    """
    Predict the next action for a workflow case given its current process state.

    Use this tool when the user asks what should happen next in a workflow,
    or provides case details and wants a recommendation.

    Returns ranked predicted actions with confidence scores, a task list
    for the delegation agent, and a chronological workflow timeline.
    """
    from datetime import datetime, timezone
    from agent.schemas import EventLogEntry, ProcessState
    from agent.iaa import run_iaa, build_process_state

    try:
        ts = datetime.now(timezone.utc)
        events = [
            EventLogEntry(
                event_id=f"{entity_id}-{i}",
                entity_id=entity_id,
                event_type=evt,
                stage=evt,
                timestamp=ts,
                metadata={}
            )
            for i, evt in enumerate(prior_actions)
        ]
        events.append(EventLogEntry(
            event_id=f"{entity_id}-current",
            entity_id=entity_id,
            event_type=current_event,
            stage=current_stage,
            timestamp=ts,
            metadata={}
        ))
        state = build_process_state(
            events,
            context_summary=context_summary,
            risk_flags=risk_flags or [],
            risk_severity=risk_severity if risk_severity != "unknown" else None,
        )
        rec = run_iaa(state)
        return {
            "recommended_action":  rec.recommended_action.action_id,
            "label":               rec.recommended_action.label,
            "confidence":          rec.recommended_action.confidence,
            "reasoning":           rec.recommended_action.reasoning,
            "escalate_to_human":   rec.escalate_to_human,
            "override_applied":    rec.override_applied,
            "override_reason":     rec.override_reason,
            "all_predictions": [
                {"action": a.action_id, "confidence": a.confidence, "reason": a.reasoning}
                for a in rec.predicted_actions
            ],
            "task_list": [
                {"task_id": t.task_id, "action": t.action, "role": t.assigned_role,
                 "priority": t.priority}
                for t in rec.task_list
            ],
            "workflow_timeline": [
                {"step": w.step, "event": w.event_type, "actor": w.actor,
                 "status": w.status}
                for w in rec.workflow_timeline
            ],
            "operating_context": rec.operating_context,
        }
    except Exception as e:
        return {"error": str(e), "recommended_action": "escalate_for_review",
                "confidence": 0.0}

# ── Tool: get case from corpus ────────────────────────────────────────────────
def get_similar_cases(query: str, n: int = 3) -> dict:
    """
    Retrieve similar historical process cases from the knowledge base.
    Use when the user asks about patterns, historical cases, or wants context
    about what typically happens in similar workflows.
    """
    from agent.retriever import IAARetriever
    from agent.schemas import ProcessState
    from datetime import datetime, timezone

    try:
        retriever = IAARetriever()
        dummy_state = ProcessState(
            entity_id="query",
            current_stage=query,
            current_event_type=query,
            timestamp=datetime.now(timezone.utc),
            metadata={}
        )
        results = retriever.retrieve(dummy_state)
        return {
            "cases": [
                {"id": r["id"], "process": r["metadata"].get("process_type"),
                 "next_action": r["metadata"].get("next_action"),
                 "source": r["metadata"].get("source"),
                 "snippet": r["document"][:200]}
                for r in results[:n]
            ]
        }
    except Exception as e:
        return {"error": str(e), "cases": []}

# ── IAA Agent definition ──────────────────────────────────────────────────────
iaa_agent = LlmAgent(
    model=os.getenv("ADK_MODEL", "gemini-2.5-flash-lite"),
    name="intent_anticipation_agent",
    description="Predicts next workflow actions from process state. Part of Project AMP.",
    instruction="""You are the Intent Anticipation Agent (IAA) for Project AMP —
an AI-powered workflow automation system.

Your job is to predict what should happen next in a business workflow given the
current case state. You have access to two tools:

1. predict_next_action — use this when a user provides case details or asks
   what should happen next. Always use this tool rather than guessing.

2. get_similar_cases — use this when a user asks about patterns or historical
   context, or when you want to ground your explanation in real examples.

When presenting results:
- Lead with the recommended action and confidence percentage
- Explain the reasoning in plain English (not technical jargon)
- Show the task list so the user knows who should do what
- Flag escalation clearly if escalate_to_human is true
- Be concise — the user is a business analyst, not a developer

Example interactions you should handle:
- "What should happen next for case X?"
- "I have a claim with these details: [details]. What do you recommend?"
- "Why did the agent recommend escalation?"
- "Show me similar cases where documentation was missing"
- "What patterns do you see in approval workflows?"
""",
    tools=[
        FunctionTool(func=predict_next_action),
        FunctionTool(func=get_similar_cases),
    ]
)

# ADK looks for root_agent when running adk web
root_agent = iaa_agent
