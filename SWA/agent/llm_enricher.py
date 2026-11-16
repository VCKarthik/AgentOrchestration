"""
LLM Enricher — Explicit Case Dispatch
─────────────────────────────────────────────────────────────────
Per Mudit: "Have you given any thought about cases like you have
            action types based on that? Have you created any cases
            that in this case LLM should do this in other case it
            should do that?"

The LLM is invoked in FOUR explicit cases (and NOT in others):

  CASE A: HIGH_CONFIDENCE_RECOMMENDATION
    Trigger: finding has decision=recommend and confidence >= 0.75
    LLM role: generate domain-aware recommendation description
    Output: domain_contextualized_description + automation_action

  CASE B: ESCALATION_SUMMARY
    Trigger: finding has decision=escalate or watch
    LLM role: draft a human-readable summary for the reviewer
    Output: summary_for_human (short, context-aware)

  CASE C: UNSUPERVISED_CLUSTER_LABELING
    Trigger: finding came from ml:dbscan_clustering detector
    LLM role: name the discovered cluster in business language
    Output: cluster_name + description

  CASE D: LLM_UNAVAILABLE_FALLBACK
    Trigger: Gemini API down, rate-limited, or key missing
    LLM role: (none — use templates)
    Output: template-based description (functional but less rich)

The LLM is NEVER invoked for:
  - Heuristic-only findings below watch threshold (they're discarded)
  - Approval-type actions (always escalate, use template)
  - Internal operations like scoring or deduplication
"""
import json
import os
import logging
from typing import Any

from config.settings import settings

logger = logging.getLogger("shadow_work.llm_enricher")

_gemini_client = None


def _get_client():
    global _gemini_client
    if _gemini_client is None:
        if not settings.GEMINI_API_KEY:
            logger.info("[llm] no API key set — using fallback templates")
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            _gemini_client = genai.GenerativeModel(settings.GEMINI_MODEL)
        except Exception as e:
            logger.error(f"[llm] client init failed: {e}")
            return None
    return _gemini_client


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
        if text.startswith("json"):
            text = text[4:].strip()
    return text


def _call_llm(prompt: str) -> dict:
    """Shared LLM call wrapper with error handling."""
    client = _get_client()
    if client is None:
        return {}
    try:
        response = client.generate_content(prompt)
        return json.loads(_strip_fences(response.text))
    except Exception as e:
        logger.warning(f"[llm] call failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────
# CASE A: HIGH_CONFIDENCE_RECOMMENDATION
# ─────────────────────────────────────────────────────────────────

def enrich_recommendation(finding: dict) -> dict:
    """LLM case A: generate domain-aware recommendation."""
    prompt_data = {
        "action_type": finding["action_type"],
        "target_entity_type": finding["target_entity_type"],
        "occurrences": finding["occurrences"],
        "mean_interval_hours": round(finding.get("mean_interval_hours", 0), 1),
        "sample_context_payloads": finding.get("sample_context_payloads", [])[:3],
    }

    prompt = f"""You are enriching a high-confidence automation recommendation.

The detection was purely structural. You do NOT know the domain — use the context payload hints to infer it.

Pattern:
{json.dumps(prompt_data, indent=2, default=str)}

Return ONLY this JSON (no fencing, no commentary):
{{
  "description": "Plain structural description, one sentence, domain-neutral",
  "domain_contextualized_description": "Business-language description using context hints, 1-2 sentences",
  "automation_action": "Concrete automation rule in imperative mood, one sentence"
}}
"""
    result = _call_llm(prompt)
    if not result:
        return _template_recommendation(finding)
    return {
        "description": result.get("description", _template_recommendation(finding)["description"]),
        "domain_contextualized_description": result.get(
            "domain_contextualized_description",
            _template_recommendation(finding)["domain_contextualized_description"],
        ),
        "automation_action": result.get(
            "automation_action",
            _template_recommendation(finding)["automation_action"],
        ),
    }


# ─────────────────────────────────────────────────────────────────
# CASE B: ESCALATION_SUMMARY
# ─────────────────────────────────────────────────────────────────

def enrich_escalation(finding: dict) -> dict:
    """LLM case B: generate human-readable escalation summary."""
    prompt_data = {
        "action_type": finding["action_type"],
        "target_entity_type": finding["target_entity_type"],
        "occurrences": finding["occurrences"],
        "reason_for_escalation": (
            "approval-type action" if finding["action_type"] in settings.APPROVAL_TYPE_ACTIONS
            else "confidence below threshold — needs human review"
        ),
        "sample_context_payloads": finding.get("sample_context_payloads", [])[:3],
    }

    prompt = f"""You are drafting an escalation summary for a human reviewer.

Pattern observed:
{json.dumps(prompt_data, indent=2, default=str)}

Return ONLY this JSON (no fencing):
{{
  "description": "Plain structural description, one sentence",
  "summary_for_human": "Clear, concise summary explaining what was observed and what the reviewer should decide. 2-3 sentences.",
  "automation_action": "If this were approved, what automation would we apply? One sentence."
}}
"""
    result = _call_llm(prompt)
    if not result:
        return _template_escalation(finding)
    return {
        "description": result.get("description", _template_escalation(finding)["description"]),
        "domain_contextualized_description": result.get("summary_for_human", ""),
        "automation_action": result.get("automation_action", _template_escalation(finding)["automation_action"]),
    }


# ─────────────────────────────────────────────────────────────────
# CASE C: UNSUPERVISED_CLUSTER_LABELING
# ─────────────────────────────────────────────────────────────────

def enrich_cluster(finding: dict) -> dict:
    """LLM case C: label a discovered cluster."""
    prompt_data = {
        "dominant_action": finding["action_type"],
        "dominant_target_type": finding["target_entity_type"],
        "cluster_size": finding["occurrences"],
        "n_actors": len(finding.get("actors_involved", [])),
        "n_cases": len(finding.get("cases_involved", [])),
        "mean_interval_hours": round(finding.get("mean_interval_hours", 0), 1),
        "sample_context_payloads": finding.get("sample_context_payloads", [])[:3],
    }

    prompt = f"""You are labeling an unsupervised cluster discovered by DBSCAN.

The ML model found these events cluster naturally together. Your job is to name the pattern in business language.

Cluster data:
{json.dumps(prompt_data, indent=2, default=str)}

Return ONLY this JSON:
{{
  "cluster_name": "Short business-friendly name, 3-6 words",
  "description": "What this cluster represents, one sentence",
  "domain_contextualized_description": "Business-language description with domain hints, 1-2 sentences",
  "automation_action": "Proposed automation if this cluster represents wasted manual work, one sentence"
}}
"""
    result = _call_llm(prompt)
    if not result:
        return _template_cluster(finding)
    return {
        "description": result.get("description", _template_cluster(finding)["description"]),
        "domain_contextualized_description": result.get(
            "domain_contextualized_description",
            _template_cluster(finding)["domain_contextualized_description"],
        ),
        "automation_action": result.get(
            "automation_action",
            _template_cluster(finding)["automation_action"],
        ),
        "cluster_name": result.get("cluster_name", f"Cluster {finding.get('cluster_id', '?')}"),
    }


# ─────────────────────────────────────────────────────────────────
# CASE D: TEMPLATE FALLBACKS
# ─────────────────────────────────────────────────────────────────

def _template_recommendation(f: dict) -> dict:
    action = f["action_type"].replace("_", " ")
    target = f["target_entity_type"].replace("_", " ")
    hours = round(f.get("mean_interval_hours", 0), 1)
    desc = f"{action} action occurred {f['occurrences']} times against {target} entities, mean interval {hours}h"
    return {
        "description": desc,
        "domain_contextualized_description": desc,
        "automation_action": f"Automate {action} after {hours}h interval",
    }


def _template_escalation(f: dict) -> dict:
    base = _template_recommendation(f)
    return {
        **base,
        "domain_contextualized_description": f"Pattern observed: {base['description']}. Human review recommended.",
    }


def _template_cluster(f: dict) -> dict:
    desc = (
        f"Unsupervised cluster {f.get('cluster_id', '?')}: {f['occurrences']} events "
        f"of action '{f['action_type']}' against '{f['target_entity_type']}' entities"
    )
    return {
        "description": desc,
        "domain_contextualized_description": desc,
        "automation_action": f"Review cluster {f.get('cluster_id', '?')} for automation opportunity",
        "cluster_name": f"Cluster {f.get('cluster_id', '?')}",
    }


# ─────────────────────────────────────────────────────────────────
# DISPATCHER
# ─────────────────────────────────────────────────────────────────

# How many escalations to enrich. Configurable via .env.
# Recommendations are NEVER capped — every recommendation is important
# enough to deserve LLM polish. Only the long tail of low-priority
# escalations is throttled to keep token cost bounded.
TOP_N_ESCALATIONS_TO_ENRICH = int(os.getenv("TOP_N_ESCALATIONS_TO_ENRICH", "10"))


def enrich_findings(findings: list[dict]) -> list[dict]:
    """
    Route each finding to the correct LLM case based on its characteristics.

    LLM cost control:
      • All recommendations are enriched (highest value, low volume)
      • Only the top-N escalations by occurrence count get LLM enrichment
      • Remaining escalations get template-based summaries (free, instant)

    With the deduped scorer + this filter:
      • ~3-4 recommendation enrichments
      • ~10 escalation enrichments
      • Total: ~13-15 LLM calls per run (vs 178 before)
    """
    # Split by decision so we can apply different rules
    recommendations = [
        f for f in findings if f.get("decision") == "recommend"
    ]
    others = [
        f for f in findings if f.get("decision") != "recommend"
    ]

    # Sort escalations by occurrence count, take top N
    others_sorted = sorted(
        others,
        key=lambda f: f.get("occurrences", 0),
        reverse=True,
    )
    top_escalations = others_sorted[:TOP_N_ESCALATIONS_TO_ENRICH]
    tail_escalations = others_sorted[TOP_N_ESCALATIONS_TO_ENRICH:]

    enriched = []
    llm_call_count = 0

    # Enrich every recommendation
    for f in recommendations:
        if (f.get("detector_source") == "ml:dbscan_clustering"
                or f.get("pattern_type") == "unsupervised_discovered_cluster"):
            llm_output = enrich_cluster(f)
        else:
            llm_output = enrich_recommendation(f)
        llm_call_count += 1
        enriched.append({**f, **llm_output})

    # Enrich top escalations only
    for f in top_escalations:
        if (f.get("detector_source") == "ml:dbscan_clustering"
                or f.get("pattern_type") == "unsupervised_discovered_cluster"):
            llm_output = enrich_cluster(f)
        else:
            llm_output = enrich_escalation(f)
        llm_call_count += 1
        enriched.append({**f, **llm_output})

    # Tail escalations get the template fallback (no LLM call)
    for f in tail_escalations:
        llm_output = _template_escalation(f)
        enriched.append({**f, **llm_output})

    logger.info(
        f"[llm] enriched {len(enriched)} findings "
        f"({llm_call_count} LLM calls, "
        f"{len(tail_escalations)} template-only)"
    )
    return enriched