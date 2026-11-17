"""
services/llm_service.py
-----------------------
LLM reasoning using Gemini with:
- fast fallback
- channel-aware explanations
- confidence explanation
- no provider-failure text in user-facing output
"""

from __future__ import annotations

import logging
import os
from typing import Any

from google import genai

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self) -> None:
        self.api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        # Fail fast on Gemini quota / network issues — without this, the SDK
        # retries with exponential backoff for ~10 s on every 429, blocking
        # the workflow. attempts=1 disables retries; timeout=5 s caps the
        # single request. The deterministic fallback in _fallback() kicks
        # in immediately on any error.
        if self.api_key:
            from google.genai import types
            self.client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=5000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        else:
            self.client = None
        self.model_name = "gemini-2.5-flash"

    def generate_reasoning(self, task: Any, decision: Any) -> str:
        prompt = self._build_prompt(task, decision)

        if self.client:
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                text = getattr(response, "text", None)
                if text and text.strip():
                    return text.strip()
            except Exception as exc:
                logger.debug(
                    "[LLMService] Gemini reasoning unavailable, using deterministic explanation: %s",
                    exc.__class__.__name__,
                )

        return self._fallback(task, decision)

    def _build_prompt(self, task: Any, decision: Any) -> str:
        selected_assignee = decision.selected_assignee or {}
        selected_owner = decision.selected_owner or {}

        channel = (
            decision.selected_channel
            if isinstance(decision.selected_channel, str)
            else decision.selected_channel.value
        )
        status = (
            decision.status
            if isinstance(decision.status, str)
            else decision.status.value
        )

        return f"""
You are explaining an enterprise delegation decision.

Task:
- Title: {task.title}
- Description: {task.description}
- Domain: {task.business_domain}
- Priority: {task.priority}
- Estimated Effort: {task.estimated_effort}
- Due Date: {task.due_date}

Decision:
- Status: {status}
- Channel: {channel}
- Confidence Score: {decision.confidence_score}
- Escalation Required: {decision.escalation_required}
- Escalation Reason: {decision.escalation_reason}
- Selected Assignee: {selected_assignee.get("name", "N/A")}
- Selected Assignee Role: {selected_assignee.get("role", "N/A")}
- Selected Owner: {selected_owner.get("name", "N/A")}
- Decision Reasons: {decision.reasons}

Write exactly 2 sentences:
1. Explain why this channel/owner was selected.
2. Explain what drove the confidence score.

Rules:
- Be channel-aware.
- Do not mention API failures, fallbacks, or missing assignees for non-human channels.
- For automation, explain repeatability/low risk.
- For supervisor review, explain risk/value/policy review.
- For specialized agent, explain domain specialization.
- For confidence, mention the strongest factors such as skill match, domain fit, utilization, ranking quality, or review safeguards.
""".strip()

    def _fallback(self, task: Any, decision: Any) -> str:
        channel = (
            decision.selected_channel
            if isinstance(decision.selected_channel, str)
            else decision.selected_channel.value
        )

        selected_assignee = decision.selected_assignee or {}
        selected_owner = decision.selected_owner or {}

        assignee_name = selected_assignee.get("name", "the selected human owner")
        assignee_role = selected_assignee.get("role", "assigned specialist")
        owner_name = selected_owner.get("name", "the selected owner")

        confidence_reason = self._confidence_explanation(task, decision)

        if decision.escalation_required:
            return (
                f"This task requires escalation because "
                f"{decision.escalation_reason or 'review conditions were triggered based on policy or risk signals'}. "
                f"{confidence_reason}"
            )

        if channel == "human_owner":
            return (
                f"This task was routed to {assignee_name} ({assignee_role}) because the task requires human judgment and this assignee had the strongest overall fit for skills, domain, and availability. "
                f"{confidence_reason}"
            )

        if channel == "automation":
            return (
                f"This task was routed to automation because it appears repetitive, low-risk, and suitable for system execution without requiring specialist review. "
                f"{confidence_reason}"
            )

        if channel == "supervisor_review":
            return (
                f"This task was routed to {owner_name} because its value, risk, or approval context requires supervisory review before execution. "
                f"{confidence_reason}"
            )

        if channel == "specialized_agent":
            return (
                f"This task was routed to {owner_name} because it requires specialized domain handling that is better suited to an expert agent workflow. "
                f"{confidence_reason}"
            )

        return (
            f"This task was routed through the selected decision path based on task context and routing rules. "
            f"{confidence_reason}"
        )

    def _confidence_explanation(self, task: Any, decision: Any) -> str:
        score = float(getattr(decision, "confidence_score", 0.0))
        reasons = [str(r).lower() for r in (decision.reasons or [])]

        if score >= 90:
            level_text = f"The confidence score is high at {score:.1f}%"
        elif score >= 75:
            level_text = f"The confidence score is strong at {score:.1f}%"
        elif score >= 60:
            level_text = f"The confidence score is moderate at {score:.1f}%"
        else:
            level_text = f"The confidence score is cautious at {score:.1f}%"

        factor_bits: list[str] = []
        joined = " ".join(reasons)

        if "skill" in joined:
            factor_bits.append("strong skill alignment")
        if "domain" in joined or "specialized" in joined:
            factor_bits.append("domain fit")
        if "availability" in joined or "util" in joined:
            factor_bits.append("available capacity")
        if "supervisor" in joined or "review" in joined:
            factor_bits.append("review safeguards")
        if "automation" in joined:
            factor_bits.append("clear automation suitability")
        if "assigned to" in joined:
            factor_bits.append("a clear top-ranked match")

        if not factor_bits:
            channel = (
                decision.selected_channel
                if isinstance(decision.selected_channel, str)
                else decision.selected_channel.value
            )

            if channel == "human_owner":
                factor_bits = ["candidate ranking strength", "skill fit", "availability"]
            elif channel == "automation":
                factor_bits = ["task repeatability", "low execution risk"]
            elif channel == "supervisor_review":
                factor_bits = ["review controls", "policy-sensitive routing"]
            elif channel == "specialized_agent":
                factor_bits = ["specialized domain match", "routing suitability"]
            else:
                factor_bits = ["the overall routing signal quality"]

        if len(factor_bits) == 1:
            factors_text = factor_bits[0]
        elif len(factor_bits) == 2:
            factors_text = f"{factor_bits[0]} and {factor_bits[1]}"
        else:
            factors_text = ", ".join(factor_bits[:-1]) + f", and {factor_bits[-1]}"

        return f"{level_text}, driven mainly by {factors_text}."