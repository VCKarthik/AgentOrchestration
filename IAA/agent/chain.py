"""
chain.py — Single-shot IAA prompt chain: one LLM call returns all fields at once.

Merged from the original 3-step chain (Contextualize → Anticipate → Recommend) to
eliminate 2 unnecessary round-trips. Rule overrides fire after LLM output unchanged.
Provider-swappable: Gemini (default) or GPT-4o-mini via LLM_PROVIDER env var.
"""
from __future__ import annotations
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

PROVIDER     = os.getenv("LLM_PROVIDER", "gemini")   # "gemini" | "openai"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")  # override for speed vs quality
GOOGLE_KEY   = os.getenv("GOOGLE_API_KEY", "")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "")


def _model_name(llm) -> str:
    """Best-effort extraction of the underlying model name for audit logging."""
    for attr in ("model", "model_name"):
        val = getattr(llm, attr, None)
        if val:
            return str(val)
    return "unknown"


# ── LLM provider factory ──────────────────────────────────────────────────────

def get_llm(temperature: float = 0.1):
    """Return a LangChain chat model. Swap provider via LLM_PROVIDER env var."""
    if PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o-mini",
            temperature=temperature,
            api_key=OPENAI_KEY,
        )
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            temperature=temperature,
            google_api_key=GOOGLE_KEY,
        )


# ── Merged prompt template ────────────────────────────────────────────────────

MERGED_SYSTEM = """You are an intelligent process automation advisor. Given a workflow case state
and historical context, you will in one pass: (1) summarize the situation, (2) predict the next
1-3 most likely actions, and (3) recommend the single best action with a plain-English justification.

You MUST respond with valid JSON only. No markdown, no explanation outside the JSON."""

MERGED_USER = """CURRENT PROCESS STATE:
- Stage: {current_stage}
- Most recent event: {current_event_type}
- Prior actions (most recent first): {prior_actions}
- Actor: {actor}
- Risk level: {risk_severity}
- Risk flags: {risk_flags}
- Policy constraints: {policy_constraints}
- Assigned owner: {assigned_owner}

RETRIEVED HISTORICAL CONTEXT (similar past cases):
{retrieved_context}

Return a single JSON object with this exact schema:
{{
  "state_summary": "<2-3 sentence summary of what is happening and what factors matter most>",
  "predicted_actions": [
    {{"action_id": "snake_case_id", "label": "Human readable label", "confidence": 0.0, "reasoning": "Why this action"}}
  ],
  "task_list": [
    {{"task_id": "T001", "action": "snake_case_action", "assigned_role": "role or null",
      "priority": "high|medium|low", "depends_on": [], "reasoning": "why this task"}}
  ],
  "workflow_timeline": [
    {{"step": 1, "event_type": "event_name", "actor": "role or null",
      "status": "completed|current|predicted", "timestamp": null}}
  ],
  "recommended_action": {{
    "action_id": "snake_case_id",
    "label": "Human readable label",
    "confidence": 0.0,
    "justification": "Plain English explanation for a business user"
  }}
}}

Rules:
- action_id must be snake_case and generic (e.g. "request_document" not "request_insurance_doc")
- confidence between 0.0 and 1.0; rank predicted_actions by confidence descending
- maximum 3 predicted_actions; if confidence < 0.3 include "escalate_for_review" as the last action
- task_list: one task per predicted action; assigned_role reflects who does the work
- workflow_timeline: prior steps as "completed", current event as "current", future as "predicted"
- recommended_action must match one of the predicted_actions action_ids
- recommended_action.justification is written for a business user, not a developer"""


# ── JSON extraction helper ────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response — handles markdown fences and stray text."""
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found in LLM response: {text[:200]}")


# ── Single-shot merged chain ──────────────────────────────────────────────────

from .schemas import ProcessState, ActionRecommendation, PredictedAction, TaskItem, WorkflowStep


def _fast_path(state: ProcessState, retrieved_ids: list[str]) -> "ActionRecommendation | None":
    """
    Skip the LLM entirely when a deterministic rule override is guaranteed.

    Mirrors the two hard rules in HARD_RULES (high_risk_escalation,
    missing_critical_input). Because the result has override_applied=True,
    apply_overrides() in iaa.py becomes a no-op when called on it.

    Returns None if no fast path applies — caller must use the LLM.
    Saves ~15-20 s of Gemini inference for ~40-60 % of production cases.
    """
    # ── Rule 1: high_risk_escalation ─────────────────────────────────────────
    if state.risk_severity in ("high", "critical"):
        action = PredictedAction(
            action_id="escalate_to_human",
            label="Escalate to human — high risk",
            confidence=0.99,
            reasoning=(
                f"Fast path: risk_severity={state.risk_severity} triggers mandatory escalation "
                "per policy — LLM bypassed."
            ),
        )
        return ActionRecommendation(
            predicted_actions=[action],
            recommended_action=action,
            override_applied=True,
            override_reason="fast_path:high_risk_escalation",
            retrieved_context_ids=retrieved_ids,
            escalate_to_human=True,
            operating_context=state.operating_context,
            model_used="fast_path/no_llm",
            timestamp=datetime.now(timezone.utc),
            task_list=[],
            workflow_timeline=[],
        )

    # ── Rule 2: missing_critical_input ────────────────────────────────────────
    flags_str = " ".join(state.risk_flags or []).lower()
    if state.risk_flags and any(kw in flags_str for kw in ("missing", "incomplete", "required")):
        action = PredictedAction(
            action_id="request_missing_document",
            label="Request missing document",
            confidence=0.95,
            reasoning="Fast path: risk_flags indicate missing required inputs — LLM bypassed.",
        )
        return ActionRecommendation(
            predicted_actions=[action],
            recommended_action=action,
            override_applied=True,
            override_reason="fast_path:missing_critical_input",
            retrieved_context_ids=retrieved_ids,
            escalate_to_human=False,
            operating_context=state.operating_context,
            model_used="fast_path/no_llm",
            timestamp=datetime.now(timezone.utc),
            task_list=[],
            workflow_timeline=[],
        )

    return None  # No fast path — caller must invoke the LLM


def run_chain(
    state: ProcessState,
    retrieved_context: str,
    retrieved_ids: list[str],
    llm=None,
) -> ActionRecommendation:
    """
    Execute the IAA chain as a single LLM call.

    One prompt replaces the original 3-step chain (Contextualize → Anticipate → Recommend),
    cutting 2 round-trips and reducing latency from ~26s to ~8-10s.
    Returns an ActionRecommendation (before rule override is applied).
    """
    # ── Fast path: skip LLM when a hard rule override is guaranteed ───────────
    fast = _fast_path(state, retrieved_ids)
    if fast is not None:
        logger.info(
            "run_chain: fast path fired — action=%s (no LLM call)",
            fast.recommended_action.action_id,
        )
        return fast

    if llm is None:
        llm = get_llm()

    from langchain_core.messages import SystemMessage, HumanMessage

    merged_prompt = [
        SystemMessage(content=MERGED_SYSTEM),
        HumanMessage(content=MERGED_USER.format(
            current_stage=state.current_stage,
            current_event_type=state.current_event_type,
            prior_actions=", ".join(state.prior_actions[-5:]) if state.prior_actions else "none",
            actor=state.actor or "unknown",
            risk_severity=state.risk_severity or "unknown",
            risk_flags=", ".join(state.risk_flags) if state.risk_flags else "none",
            policy_constraints=", ".join(state.policy_constraints) if state.policy_constraints else "none",
            assigned_owner=state.assigned_owner or "not assigned",
            retrieved_context=retrieved_context,
        ))
    ]

    # Production-mode safety: degrade gracefully if no LLM key is set or the
    # provider rejects the request. Demo presenters often run without a real
    # GOOGLE_API_KEY — this path returns a sensible "review the case" stub
    # instead of bubbling a 500 up to the orchestrator, so the rest of the
    # pipeline (RRA, GPA, DA) still completes.
    try:
        raw = llm.invoke(merged_prompt).content
        data = _extract_json(raw)
    except Exception as exc:
        logger.warning(
            "run_chain: LLM call failed (%s) — returning no-LLM fallback recommendation",
            exc.__class__.__name__,
        )
        action = PredictedAction(
            action_id="review_case",
            label="Review case manually",
            confidence=0.40,
            reasoning=(
                "LLM unavailable (no API key or provider error). "
                "Defaulting to manual review until a key is configured."
            ),
        )
        return ActionRecommendation(
            predicted_actions=[action],
            recommended_action=action,
            override_applied=False,
            override_reason=None,
            retrieved_context_ids=retrieved_ids,
            escalate_to_human=False,
            operating_context=state.operating_context,
            model_used="fallback/no_llm",
            timestamp=datetime.now(timezone.utc),
            task_list=[],
            workflow_timeline=[],
        )

    # ── Parse predicted_actions ───────────────────────────────────────────────
    predicted_actions: list[PredictedAction] = []
    for a in data.get("predicted_actions", [])[:3]:
        try:
            predicted_actions.append(PredictedAction(
                action_id=str(a.get("action_id", "unknown_action")).lower().replace(" ", "_"),
                label=str(a.get("label", a.get("action_id", "Unknown"))),
                confidence=float(a.get("confidence", 0.5)),
                reasoning=str(a.get("reasoning", "")),
            ))
        except Exception:
            logger.warning("run_chain: skipping malformed predicted_action: %s", a, exc_info=True)

    if not predicted_actions:
        predicted_actions = [PredictedAction(
            action_id="escalate_for_review",
            label="Escalate for review",
            confidence=0.3,
            reasoning="Unable to predict next action with confidence — insufficient context",
        )]

    predicted_actions.sort(key=lambda x: x.confidence, reverse=True)

    # ── Parse task_list ───────────────────────────────────────────────────────
    task_list: list[TaskItem] = []
    for t in data.get("task_list", []):
        try:
            task_list.append(TaskItem(
                task_id=str(t.get("task_id", f"T{len(task_list)+1:03d}")),
                action=str(t.get("action", "unknown_action")).lower().replace(" ", "_"),
                assigned_role=t.get("assigned_role") or None,
                priority=str(t.get("priority", "medium")),
                depends_on=[str(x) for x in t.get("depends_on", [])],
                reasoning=str(t.get("reasoning", "")),
            ))
        except Exception:
            logger.warning("run_chain: skipping malformed task_list item: %s", t, exc_info=True)

    # ── Parse workflow_timeline ───────────────────────────────────────────────
    workflow_timeline: list[WorkflowStep] = []
    for w in data.get("workflow_timeline", []):
        try:
            ts = w.get("timestamp")
            workflow_timeline.append(WorkflowStep(
                step=int(w.get("step", len(workflow_timeline) + 1)),
                event_type=str(w.get("event_type", "unknown")),
                actor=w.get("actor") or None,
                status=str(w.get("status", "predicted")),
                timestamp=ts if ts else None,
            ))
        except Exception:
            logger.warning("run_chain: skipping malformed workflow_timeline item: %s", w, exc_info=True)

    # ── Parse recommended_action ──────────────────────────────────────────────
    rec_raw = data.get("recommended_action") or {}
    recommended = PredictedAction(
        action_id=str(rec_raw.get("action_id", predicted_actions[0].action_id)),
        label=str(rec_raw.get("label", predicted_actions[0].label)),
        confidence=float(rec_raw.get("confidence", predicted_actions[0].confidence)),
        reasoning=str(rec_raw.get("justification", predicted_actions[0].reasoning)),
    )

    return ActionRecommendation(
        predicted_actions=predicted_actions,
        recommended_action=recommended,
        retrieved_context_ids=retrieved_ids,
        escalate_to_human=recommended.action_id in ("escalate_for_review", "escalate_to_human"),
        operating_context=state.operating_context,
        model_used=f"{PROVIDER}/{_model_name(llm)}",
        timestamp=datetime.now(timezone.utc),
        task_list=task_list,
        workflow_timeline=workflow_timeline,
    )


# ── Rule override module ──────────────────────────────────────────────────────

HARD_RULES = [
    {
        "name": "high_risk_escalation",
        "condition": lambda s: s.risk_severity in ("high", "critical"),
        "action_id": "escalate_to_human",
        "label": "Escalate to human — high risk",
        "reason": "Risk severity is high or critical — autonomous action blocked by policy",
        "confidence": 0.99,
        "escalate": True,
    },
    {
        "name": "missing_critical_input",
        "condition": lambda s: bool(s.risk_flags) and any(
            kw in " ".join(s.risk_flags).lower() for kw in ["missing", "incomplete", "required"]
        ),
        "action_id": "request_missing_document",
        "label": "Request missing document",
        "reason": "Required inputs are flagged as missing — cannot proceed until resolved",
        "confidence": 0.95,
        "escalate": False,
    },
    {
        "name": "low_confidence_escalation",
        "condition": lambda s: False,  # evaluated against recommendation confidence, not state
        "action_id": "escalate_for_review",
        "label": "Escalate — low confidence",
        "reason": "Predicted confidence below threshold — human review required",
        "confidence": 0.99,
        "escalate": True,
    },
]

CONFIDENCE_THRESHOLD = 0.45  # below this, soft escalation fires


def apply_overrides(
    recommendation: ActionRecommendation,
    state: ProcessState,
) -> ActionRecommendation:
    """
    Apply hard rule overrides to an ActionRecommendation.

    Hard rules (high risk, missing inputs) replace the top recommendation entirely.
    Low confidence triggers soft escalation — recommendation is kept but escalate flag set.

    task_list and workflow_timeline are preserved through all override paths.
    Returns a new ActionRecommendation (original is never mutated).
    """
    # Check hard rules
    for rule in HARD_RULES:
        if rule["name"] == "low_confidence_escalation":
            continue  # handled separately below
        if rule["condition"](state):
            override_action = PredictedAction(
                action_id=rule["action_id"],
                label=rule["label"],
                confidence=rule["confidence"],
                reasoning=rule["reason"],
            )
            return ActionRecommendation(
                predicted_actions=[override_action] + recommendation.predicted_actions[:2],
                recommended_action=override_action,
                override_applied=True,
                override_reason=f"Rule '{rule['name']}' fired: {rule['reason']}",
                retrieved_context_ids=recommendation.retrieved_context_ids,
                escalate_to_human=rule["escalate"],
                operating_context=recommendation.operating_context,
                model_used=recommendation.model_used,
                timestamp=recommendation.timestamp,
                task_list=recommendation.task_list,
                workflow_timeline=recommendation.workflow_timeline,
            )

    # Check confidence threshold (soft escalation — keeps prediction, sets flag)
    if recommendation.recommended_action.confidence < CONFIDENCE_THRESHOLD:
        return ActionRecommendation(
            predicted_actions=recommendation.predicted_actions,
            recommended_action=recommendation.recommended_action,
            override_applied=True,
            override_reason=f"Confidence {recommendation.recommended_action.confidence:.2f} below threshold {CONFIDENCE_THRESHOLD} — escalation flag set",
            retrieved_context_ids=recommendation.retrieved_context_ids,
            escalate_to_human=True,
            operating_context=recommendation.operating_context,
            model_used=recommendation.model_used,
            timestamp=recommendation.timestamp,
            task_list=recommendation.task_list,
            workflow_timeline=recommendation.workflow_timeline,
        )

    return recommendation
