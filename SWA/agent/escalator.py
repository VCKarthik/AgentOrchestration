"""Escalation formatting. Split enriched findings into recommendations vs escalations."""
import uuid
from typing import Any


def to_escalation(f: dict[str, Any]) -> dict[str, Any]:
    reason_map = {
        "escalate": "pattern involves approval-type action or low confidence",
        "watch": "pattern observed but below confidence threshold; continue monitoring",
    }
    role_map = {"high": "compliance_lead", "medium": "workflow_owner", "low": "operations_coordinator"}

    return {
        "escalation_id": f"sw_e_{uuid.uuid4().hex[:8]}",
        "reason": reason_map.get(f["decision"], "uncategorized"),
        "pattern_signature": (
            f"action:{f['action_type']} → target_type:{f['target_entity_type']}"
        ),
        "occurrences": f["occurrences"],
        "recommended_human_role": role_map.get(f["risk_level"], "workflow_owner"),
        "summary_for_human": f.get(
            "domain_contextualized_description",
            f.get("description", "Pattern detected; human review recommended.")
        ),
        "evidence_event_ids": f.get("event_ids", [])[:10],
    }


def split_findings(enriched: list[dict]) -> tuple[list[dict], list[dict]]:
    recommendations = [f for f in enriched if f["decision"] == "recommend"]
    escalations = [to_escalation(f) for f in enriched if f["decision"] in ("watch", "escalate")]
    return recommendations, escalations
