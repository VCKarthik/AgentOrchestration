"""
orchestrator/intake_parser.py

Natural language -> TaskIntake field extractor.
Sends a single Gemini JSON-mode call and returns a dict compatible with
run_amp_workflow(task_input). Auto-generates task_id / case_id / timestamps
after parsing so the caller gets a ready-to-use payload.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a case intake parser for an enterprise workflow system.
Given a natural-language description of a case, extract structured fields.
Return ONLY a valid JSON object -- no markdown, no explanation.

Field definitions and allowed values:

case_type       : one of vendor_onboarding | claim_review | fraud_investigation |
                  compliance_review | financial_approval | hr_escalation | general
task_type       : same options as case_type (default: same as case_type)
priority        : one of critical | high | medium | low  (default: medium)
urgency         : one of immediate | urgent | moderate | low  (default: moderate)
title           : short human-readable title (5-10 words). Infer from description.
description     : the original description text verbatim
requester       : person or role who submitted the case (string). Use "analyst" if unknown.
requester_role  : job role of the requester (string or null)
business_domain : department or domain, e.g. procurement | finance | compliance |
                  operations | hr | legal | general  (default: general)
monetary_value  : numeric USD amount if mentioned (float or null)
estimated_effort: estimated hours to resolve (float, default: 2.0)
required_skills : list of relevant skills, e.g. ["fraud_analysis", "legal"] (may be [])

Inference rules:
- "urgent" / "asap" / "immediate" -> urgency: urgent or immediate
- "$" amounts -> monetary_value (strip commas, convert "k" suffix: $150k -> 150000)
- "fraud" / "suspicious" -> case_type: fraud_investigation, priority: high if not stated
- "vendor" / "supplier" / "onboarding" -> case_type: vendor_onboarding
- "claim" / "insurance" -> case_type: claim_review
- "compliance" / "regulatory" / "audit" -> case_type: compliance_review
- "financial" / "budget" / "payment" / "invoice" -> case_type: financial_approval
- "HR" / "employee" / "termination" / "leave" -> case_type: hr_escalation
- Use "general" when nothing matches

Examples:
Input: "Vendor ABC needs onboarding, $150k contract, urgent, submitted by Alice from procurement"
Output: {"case_type":"vendor_onboarding","task_type":"vendor_onboarding","title":"Vendor ABC Onboarding","description":"Vendor ABC needs onboarding, $150k contract, urgent, submitted by Alice from procurement","requester":"Alice","requester_role":"procurement","business_domain":"procurement","priority":"medium","urgency":"urgent","monetary_value":150000.0,"estimated_effort":2.0,"required_skills":[]}

Input: "Suspicious $12,000 transaction, needs immediate fraud review, compliance team"
Output: {"case_type":"fraud_investigation","task_type":"fraud_investigation","title":"Suspicious Transaction Fraud Review","description":"Suspicious $12,000 transaction, needs immediate fraud review, compliance team","requester":"compliance team","requester_role":"compliance","business_domain":"compliance","priority":"high","urgency":"immediate","monetary_value":12000.0,"estimated_effort":2.0,"required_skills":["fraud_analysis"]}
"""


class IntakeParseError(Exception):
    pass


def _parse_monetary(text: str) -> float | None:
    """Best-effort monetary extraction as a fallback if LLM misses it."""
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s*(k|m)?", text, re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    suffix = (m.group(2) or "").lower()
    if suffix == "k":
        val *= 1_000
    elif suffix == "m":
        val *= 1_000_000
    return val


async def parse_natural_language_intake(text: str) -> dict:
    """
    Parse a free-text case description into a TaskIntake-compatible dict.

    Auto-populates task_id, case_id, timestamp, due_date after LLM extraction.
    Raises IntakeParseError if the API call fails completely.
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise IntakeParseError(
            "No GOOGLE_API_KEY or GEMINI_API_KEY set -- cannot parse natural language input."
        )

    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        raise IntakeParseError(
            "google-generativeai package not installed. Run: pip install google-generativeai"
        )

    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
        system_instruction=_SYSTEM_PROMPT,
    )

    try:
        response = await model.generate_content_async(text)
        raw = response.text.strip()
    except Exception as exc:
        raise IntakeParseError(f"Gemini API call failed: {exc}") from exc

    try:
        parsed: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IntakeParseError(f"LLM returned non-JSON: {raw[:200]}") from exc

    # Fallback: if LLM missed monetary_value, try regex
    if parsed.get("monetary_value") is None:
        parsed["monetary_value"] = _parse_monetary(text)

    # Ensure description is always the original text
    parsed["description"] = parsed.get("description") or text

    # Auto-generate time/id fields (same logic as demo UI)
    now = datetime.now(timezone.utc)
    due = (now + timedelta(hours=48)).isoformat()

    uid = uuid.uuid4().hex[:6].upper()
    case_type_abbr = {
        "vendor_onboarding":   "VND",
        "claim_review":        "CLM",
        "fraud_investigation": "FRD",
        "compliance_review":   "CMP",
        "financial_approval":  "FIN",
        "hr_escalation":       "HR",
    }.get(parsed.get("case_type", "general"), "GEN")

    case_id = f"CASE-{case_type_abbr}-{uid}"
    task_id = f"{case_id}-{now.strftime('%H%M%S')}"

    parsed.update({
        "task_id":   task_id,
        "case_id":   case_id,
        "timestamp": now.isoformat(),
        "due_date":  due,
    })

    log.info("intake_parser: parsed '%s...' -> case_type=%s priority=%s",
             text[:60], parsed.get("case_type"), parsed.get("priority"))
    return parsed
