"""
Scorer: assigns confidence, risk, and decision to each raw finding.
Also deduplicates findings that the same pattern produced from multiple detectors.

Deduplication fix: if two different detectors produce findings with the same
(action_type, target_entity, actors) — we merge them and keep the highest
confidence version.
"""
import math
from typing import Any

from config.settings import settings


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

    # ML-detected clusters get a default regularity of 0.75 (they were clustered,
    # so they're similar by definition — but we don't have a true interval measure)
    if raw.get("detector_source") == "ml:dbscan_clustering":
        regularity = max(regularity, 0.75)

    confidence = round(size_factor * 0.5 + regularity * 0.3 + diversity_factor * 0.2, 3)

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
    elif confidence >= settings.CONFIDENCE_THRESHOLD and raw["action_type"] in settings.AUTOMATABLE_ACTIONS:
        decision = "recommend"
        requires_human_approval = False
    elif confidence >= 0.5:
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


def _dedup_key(finding: dict) -> tuple:
    """Key that identifies 'the same pattern' across detectors."""
    return (
        finding["action_type"],
        finding.get("target_entity", ""),
        tuple(sorted(finding.get("actors_involved", []))),
    )


def deduplicate_findings(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge duplicate findings. When the same pattern is caught by multiple
    detectors, keep the one with highest confidence and record all sources.

    FIX FROM V1: the status_check pattern was appearing multiple times.
    """
    by_key: dict[tuple, dict] = {}
    for f in scored:
        key = _dedup_key(f)
        if key not in by_key:
            f["detector_sources"] = [f["detector_source"]]
            by_key[key] = f
        else:
            existing = by_key[key]
            existing["detector_sources"].append(f["detector_source"])
            # Keep the higher-confidence version
            if f["confidence"] > existing["confidence"]:
                f["detector_sources"] = existing["detector_sources"]
                by_key[key] = f

    return list(by_key.values())


def score_all(raw_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored = [score_finding(r) for r in raw_findings]
    deduped = deduplicate_findings(scored)
    return deduped
