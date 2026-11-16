"""
Scorer: assigns confidence, risk, and decision to each raw finding.
Also deduplicates findings that the same pattern produced from multiple
detectors and from multiple time-interval slices.

DEDUPLICATION CHANGES (v3.1):
  Old behavior: same pattern at different intervals (87h, 24h, 12h...)
                produced separate recommendations → 31 duplicates of
                "sent_followup → external_contact"

  New behavior: dedup key uses (action_type, target_entity_TYPE) so all
                interval slices of the same pattern collapse into one
                consolidated recommendation with combined occurrences,
                cases_involved, actors_involved, and evidence.

TOP-N FILTER:
  Default: keep only the top 8 recommendations by confidence + occurrences.
  Watches and escalations are NOT capped — they all pass through.
  Configurable via .env: TOP_N_RECOMMENDATIONS=8
"""
import logging
import math
import os
import re
from typing import Any

from config.settings import settings

logger = logging.getLogger("shadow_work.scorer")

TOP_N_RECOMMENDATIONS = int(os.getenv("TOP_N_RECOMMENDATIONS", "8"))


# ──────────────────────────────────────────────────────────────────
# SCORING
# ──────────────────────────────────────────────────────────────────

def _sample_size_factor(n: int) -> float:
    return min(0.95, 1.0 - math.exp(-n / 6.0))


def _case_diversity_factor(n_cases: int) -> float:
    if n_cases >= 3:
        return 1.0
    if n_cases == 2:
        return 0.85
    return 0.7


def score_finding(raw: dict[str, Any]) -> dict[str, Any]:
    size_factor = _sample_size_factor(raw["occurrences"])
    diversity_factor = _case_diversity_factor(len(raw.get("cases_involved", [])))
    regularity = raw.get("regularity_score", 0.7)

    # ML-detected clusters get a default regularity of 0.75
    if raw.get("detector_source") == "ml:dbscan_clustering":
        regularity = max(regularity, 0.75)

    confidence = round(
        size_factor * 0.5 + regularity * 0.3 + diversity_factor * 0.2, 3
    )

    # Risk assessment
    if raw["action_type"] in settings.APPROVAL_TYPE_ACTIONS:
        risk_level = "high"
    elif len(raw["actors_involved"]) >= 3:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Decision
    if raw["action_type"] in settings.APPROVAL_TYPE_ACTIONS:
        decision = "escalate"
        requires_human_approval = True
    elif confidence >= settings.CONFIDENCE_THRESHOLD:
        decision = "recommend"
        requires_human_approval = False
    elif confidence >= 0.50:
        decision = "watch"
        requires_human_approval = True
    else:
        decision = "escalate"
        requires_human_approval = True

    return {
        **raw,
        "confidence": confidence,
        "risk_level": risk_level,
        "decision": decision,
        "requires_human_approval": requires_human_approval,
    }


# ──────────────────────────────────────────────────────────────────
# DEDUPLICATION — the new logic
# ──────────────────────────────────────────────────────────────────

def _extract_target_type(finding: dict) -> str:
    """
    Extract target_entity_type. Try a few fields since detectors emit
    slightly different shapes.
    """
    # Direct field (cross_case detector)
    if finding.get("target_entity_type"):
        return finding["target_entity_type"]

    # Parse from pattern_signature (repetition, ML cluster detectors)
    sig = finding.get("pattern_signature", "")
    m = re.search(r"target_type:(\w+)", sig)
    if m:
        return m.group(1)

    # Fallback to target_entity (worst case — gives instance not class)
    return finding.get("target_entity", "")


def _dedup_key(finding: dict) -> tuple:
    """
    Key that identifies 'the same pattern' across detectors AND interval slices.

    Uses (action, target_TYPE) — NOT (action, target_instance).
    So all 'sent_followup' targeting any 'external_contact' collapse together
    even if specific contacts (claimant_001 vs claimant_002) differ.
    """
    return (
        finding.get("action_type", ""),
        _extract_target_type(finding),
    )


def deduplicate_findings(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge findings sharing the same (action, target_type).
    Combine occurrences, cases, actors, and evidence into one finding.
    """
    by_key: dict[tuple, dict] = {}

    for f in scored:
        key = _dedup_key(f)

        if key not in by_key:
            f["detector_sources"] = [f.get("detector_source", "unknown")]
            f["dedup_count"] = 1
            by_key[key] = dict(f)  # copy so we don't mutate the input
        else:
            existing = by_key[key]

            # Combine quantitative fields
            existing["occurrences"] = (
                existing.get("occurrences", 0) + f.get("occurrences", 0)
            )

            # Union of cases, actors, evidence
            for field in ("cases_involved", "actors_involved",
                          "evidence_event_ids"):
                merged = set(existing.get(field, []))
                merged.update(f.get(field, []))
                existing[field] = sorted(merged)

            # Cap evidence_event_ids to keep output reasonable
            existing["evidence_event_ids"] = existing.get(
                "evidence_event_ids", []
            )[:30]

            # Track all detectors that found this pattern
            existing["detector_sources"].append(
                f.get("detector_source", "unknown")
            )
            existing["dedup_count"] = existing.get("dedup_count", 1) + 1

            # Keep the highest confidence
            if f["confidence"] > existing["confidence"]:
                existing["confidence"] = f["confidence"]

            # Use longest description (more informative)
            if (len(f.get("description", ""))
                    > len(existing.get("description", ""))):
                existing["description"] = f.get("description", "")
                existing["domain_contextualized_description"] = f.get(
                    "domain_contextualized_description",
                    existing.get("domain_contextualized_description", ""),
                )

    deduped = list(by_key.values())
    if len(deduped) < len(scored):
        logger.info(
            f"[scorer] dedup: {len(scored)} → {len(deduped)} unique patterns"
        )
    return deduped


# ──────────────────────────────────────────────────────────────────
# TOP-N FILTER — only cap recommendations, never escalations
# ──────────────────────────────────────────────────────────────────

def top_n_filter(deduped: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """
    Keep only the top-N recommendations (by confidence + occurrences).
    Watches and escalations always pass through unchanged.
    """
    recs = [f for f in deduped if f.get("decision") == "recommend"]
    others = [f for f in deduped if f.get("decision") != "recommend"]

    recs_sorted = sorted(
        recs,
        key=lambda f: (f.get("confidence", 0), f.get("occurrences", 0)),
        reverse=True,
    )
    top_recs = recs_sorted[:n]

    if len(top_recs) < len(recs):
        logger.info(
            f"[scorer] top-{n} filter: {len(recs)} recommendations → "
            f"{len(top_recs)} top (others stay as escalations)"
        )

    return top_recs + others


# ──────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────────

def score_all(raw_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score → dedupe → keep top-N recommendations."""
    scored = [score_finding(r) for r in raw_findings]
    deduped = deduplicate_findings(scored)
    filtered = top_n_filter(deduped, n=TOP_N_RECOMMENDATIONS)
    return filtered