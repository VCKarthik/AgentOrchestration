"""
Risk Radar Agent — Reasoning summary generation.

Architecture: rules decide (deterministic), LLM explains (natural language).
The Summarizer protocol lets us swap the LLM for a stub in tests.

For production, AnthropicSummarizer calls Claude to produce a plain-English
explanation of why the case received its risk classification. If the API call
fails, we fall back to the deterministic RuleBasedSummarizer so the agent
never returns an empty reasoning field.
"""

from __future__ import annotations

import os
from typing import List, Protocol

from .schema import RiskItem, Severity, ProceedDecision


class Summarizer(Protocol):
    def summarize(
        self,
        risk_items: List[RiskItem],
        overall: Severity,
        can_proceed: ProceedDecision,
        workflow_type: str,
    ) -> str: ...


class RuleBasedSummarizer:
    """Deterministic fallback — also used in tests.

    Produces a clear, structured summary from the risk items themselves.
    No external calls. Always works.
    """

    def summarize(self, risk_items, overall, can_proceed, workflow_type):
        if not risk_items:
            return "No risks detected. Workflow may proceed."

        lead = {
            Severity.LOW: "Minor issues detected.",
            Severity.MEDIUM: "Attention needed.",
            Severity.HIGH: "Significant risk detected.",
            Severity.CRITICAL: "Workflow should not proceed without intervention.",
        }[overall]

        reasons = "; ".join(item.reason for item in risk_items)
        action_clause = {
            ProceedDecision.PROCEED: "Workflow can continue.",
            ProceedDecision.CAUTION: "Workflow may continue with caution.",
            ProceedDecision.HOLD: "Workflow held pending resolution.",
        }[can_proceed]

        return f"{lead} {reasons} {action_clause}"


class GeminiSummarizer:
    """Uses Google Gemini API (free tier) to produce a natural-language summary.

    Falls back to RuleBasedSummarizer on any failure.
    Get a free key at https://aistudio.google.com/apikey
    """

    def __init__(self, model: str = "gemini-2.0-flash"):
        self.model = model
        self._fallback = RuleBasedSummarizer()

    def summarize(self, risk_items, overall, can_proceed, workflow_type):
        try:
            from google import genai
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

            risk_lines = "\n".join(
                f"- [{item.severity.value.upper()}] {item.risk_type.value}: {item.reason}"
                for item in risk_items
            ) or "None"
            prompt = (
                f"You are a concise risk-assessment assistant inside an enterprise workflow system. "
                f"Summarize why this case was classified as {overall.value.upper()} risk "
                f"and why the recommendation is to {can_proceed.value.upper()}. "
                f"Use one or two plain sentences. No preamble. No bullet points.\n\n"
                f"Workflow type: {workflow_type}\n"
                f"Detected risks:\n{risk_lines}"
            )

            response = client.models.generate_content(model=self.model, contents=prompt)
            text = response.text.strip() if response.text else ""
            return text or self._fallback.summarize(risk_items, overall, can_proceed, workflow_type)

        except Exception:
            return self._fallback.summarize(risk_items, overall, can_proceed, workflow_type)


class GroqSummarizer:
    """Uses Groq's free API (Llama 3) to produce a natural-language summary.

    Falls back to RuleBasedSummarizer on any failure.
    Get a free key at https://console.groq.com
    """

    def __init__(self, model: str = "llama-3.1-8b-instant"):
        self.model = model
        self._fallback = RuleBasedSummarizer()

    def summarize(self, risk_items, overall, can_proceed, workflow_type):
        try:
            from groq import Groq
            client = Groq(api_key=os.environ["GROQ_API_KEY"])

            risk_lines = "\n".join(
                f"- [{item.severity.value.upper()}] {item.risk_type.value}: {item.reason}"
                for item in risk_items
            ) or "None"
            prompt = (
                f"You are a concise risk-assessment assistant inside an enterprise workflow system. "
                f"Summarize why this case was classified as {overall.value.upper()} risk "
                f"and why the recommendation is to {can_proceed.value.upper()}. "
                f"Use one or two plain sentences. No preamble. No bullet points.\n\n"
                f"Workflow type: {workflow_type}\n"
                f"Detected risks:\n{risk_lines}"
            )

            response = client.chat.completions.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content.strip()
            return text or self._fallback.summarize(risk_items, overall, can_proceed, workflow_type)

        except Exception:
            return self._fallback.summarize(risk_items, overall, can_proceed, workflow_type)


class AnthropicSummarizer:
    """Uses Anthropic's Claude API to produce a natural-language summary.

    Falls back to RuleBasedSummarizer on any failure so the agent is
    robust to network issues, missing keys, or rate limits.
    """

    def __init__(self, model: str = "claude-sonnet-4-5"):
        self.model = model
        self._fallback = RuleBasedSummarizer()

    def summarize(self, risk_items, overall, can_proceed, workflow_type):
        try:
            # Lazy import so the agent runs even without the SDK installed.
            from anthropic import Anthropic
            client = Anthropic()  # reads ANTHROPIC_API_KEY from env

            risk_lines = "\n".join(
                f"- [{item.severity.value.upper()}] {item.risk_type.value}: {item.reason}"
                for item in risk_items
            )
            prompt = (
                f"You are a concise risk-assessment assistant inside an enterprise workflow system. "
                f"Summarize why this case was classified as {overall.value.upper()} risk "
                f"and why the recommendation is to {can_proceed.value.upper()}. "
                f"Use one or two plain sentences. No preamble. No bullet points.\n\n"
                f"Workflow type: {workflow_type}\n"
                f"Detected risks:\n{risk_lines}"
            )

            msg = client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                block.text for block in msg.content if hasattr(block, "text")
            ).strip()
            return text or self._fallback.summarize(risk_items, overall, can_proceed, workflow_type)

        except Exception:
            return self._fallback.summarize(risk_items, overall, can_proceed, workflow_type)


def default_summarizer() -> Summarizer:
    """Pick summarizer based on environment. Priority: Groq > Gemini > Anthropic > rules."""
    if os.environ.get("GROQ_API_KEY"):
        return GroqSummarizer()
    if os.environ.get("GEMINI_API_KEY"):
        return GeminiSummarizer()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicSummarizer()
    return RuleBasedSummarizer()
