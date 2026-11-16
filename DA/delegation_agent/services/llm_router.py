"""
services/llm_router.py
----------------------
LLM routing with:
- single Gemini call
- quiet fallback on rate limit / API failure
- stable JSON parsing
"""

from __future__ import annotations

import json
import logging
import os

from google import genai

logger = logging.getLogger(__name__)


class LLMRouter:
    def __init__(self) -> None:
        self.api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.model_name = "gemini-2.5-flash"

    def recommend_assignee(self, task, candidate_rankings) -> dict:
        top_candidates = candidate_rankings[:3]

        if not top_candidates:
            return {
                "recommended_assignee_id": None,
                "confidence": 0.0,
                "escalation_suggested": True,
                "reason": "No candidates available.",
            }

        if not self.client:
            return self._fallback(top_candidates, "No API key")

        candidate_text = [
            {
                "assignee_id": c.assignee_id,
                "name": c.name,
                "role": c.role,
                "score": c.composite_score,
                "utilization": c.utilization_percent,
                "seniority": getattr(c, "seniority", "unknown"),
            }
            for c in top_candidates
        ]

        prompt = f"""
You are assisting with enterprise task delegation.

Task:
- Title: {task.title}
- Description: {task.description}
- Domain: {task.business_domain}
- Priority: {task.priority}

Candidates:
{json.dumps(candidate_text, indent=2)}

Select the best candidate from the list.

Return valid JSON only:
{{
  "recommended_assignee_id": "candidate-id",
  "confidence": 0,
  "reason": "brief explanation"
}}
""".strip()

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )

            text = getattr(response, "text", "") or ""
            text = self._clean_response_text(text)

            parsed = json.loads(text)
            recommended_id = parsed.get("recommended_assignee_id")
            confidence = float(parsed.get("confidence", 0.0))
            reason = parsed.get("reason", "").strip()

            valid_ids = {c.assignee_id for c in top_candidates}
            if recommended_id not in valid_ids:
                return self._fallback(top_candidates, "Invalid Gemini candidate")

            return {
                "recommended_assignee_id": recommended_id,
                "confidence": max(0.0, min(confidence, 100.0)),
                "escalation_suggested": False,
                "reason": reason or "LLM selected best candidate.",
            }

        except Exception as exc:
            logger.debug(
                "[LLMRouter] Gemini routing unavailable, using fallback: %s",
                exc.__class__.__name__,
            )
            return self._fallback(top_candidates, "Gemini unavailable")

    def _clean_response_text(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        return text

    def _fallback(self, candidates, reason: str) -> dict:
        best = max(candidates, key=lambda c: c.composite_score)

        return {
            "recommended_assignee_id": best.assignee_id,
            "confidence": float(best.composite_score),
            "escalation_suggested": False,
            "reason": f"Fallback used ({reason}).",
        }