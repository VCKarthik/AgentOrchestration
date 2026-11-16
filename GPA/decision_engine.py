from typing import Dict, Any, List
from sqlalchemy.orm import Session
from .models import PolicyDocument, PolicyRule


def run_governance_decision(db: Session, task_payload: Dict[str, Any]) -> Dict[str, Any]:
    metadata = task_payload.get("metadata", {})
    policy_doc_ids = task_payload.get("policy_document_ids", [])

    if not policy_doc_ids:
        # Fall back to policy_type lookup (policy_type == case_type from orchestrator shim)
        policy_type = task_payload.get("policy_type") or task_payload.get("task_type")
        if policy_type:
            matched_docs = (
                db.query(PolicyDocument)
                .filter(PolicyDocument.policy_type == policy_type)
                .all()
            )
            policy_doc_ids = [d.id for d in matched_docs]

        if not policy_doc_ids:
            return {
                "task_id": task_payload.get("task_id"),
                "decision": "APPROVE",
                "reason": "No policy documents provided for evaluation",
                "confidence": 0.65,
                "requires_approval": False,
                "next_agent": "delegation_agent",
                "matched_rule_ids": [],
                "matched_chunk_ids": []
            }

    rules: List[PolicyRule] = (
        db.query(PolicyRule)
        .filter(PolicyRule.document_id.in_(policy_doc_ids))
        .all()
    )

    decision = "APPROVE"
    reasons = []
    matched_rules = []
    matched_chunks = []

    approvers = set() 

    def get_value(subject: str):
        return metadata.get(subject)

    for rule in rules:
        subject_value = get_value(rule.subject)

        if subject_value is None:
            continue

        triggered = False

        # Numeric comparisons
        if isinstance(subject_value, (int, float)):
            try:
                rule_value = float(rule.value) if rule.value is not None else None
            except (TypeError, ValueError):
                rule_value = None

            if rule_value is not None:
                if rule.operator == ">=" and subject_value >= rule_value:
                    triggered = True
                elif rule.operator == ">" and subject_value > rule_value:
                    triggered = True
                elif rule.operator == "<=" and subject_value <= rule_value:
                    triggered = True
                elif rule.operator == "<" and subject_value < rule_value:
                    triggered = True
                elif rule.operator == "==" and subject_value == rule_value:
                    triggered = True

        # Boolean comparisons
        elif isinstance(subject_value, bool):
            if str(subject_value).lower() == str(rule.value).lower():
                triggered = True

        # String comparisons
        elif isinstance(subject_value, str):
            if rule.operator == "==" and subject_value.lower() == str(rule.value).lower():
                triggered = True

        if triggered:
            decision = "ESCALATE" if rule.action == "ESCALATE" else rule.action
            import re

            text = rule.condition_text
            # remove a., b., c.
            text = re.sub(r"\b[a-z]\.\s*", "", text)
            # take only main sentence before ;
            text = text.split(";")[0]
            clean_reason = text.strip()
            reasons.append(clean_reason)
            matched_rules.append(rule.id)
            matched_chunks.append(rule.chunk_id)

            if rule.approver:
                approvers.add(rule.approver)

    confidence = 0.9 if decision == "ESCALATE" else 0.7

    matched_chunks = list(set(matched_chunks))
    clean_reasons = list(dict.fromkeys(reasons)) 
    return {
        "task_id": task_payload.get("task_id"),
        "decision": decision,
        "reason": " | ".join(clean_reasons),   
        "reason_list": clean_reasons,          
        "confidence": confidence,
        "requires_approval": decision == "ESCALATE",
        "approvers": list(approvers),
        "next_agent": "human_review_agent" if decision == "ESCALATE" else "delegation_agent",
        "matched_rule_ids": matched_rules,
        "matched_chunk_ids": list(set(matched_chunks))
    }