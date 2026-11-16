from __future__ import annotations

from pathlib import Path

import yaml


class DecisionExporter:
    """
    Exports delegation decisions into structured YAML.
    Produces a cleaner client-facing YAML output while the full decision object
    remains available internally for debugging.
    """

    def __init__(self, output_dir: str = "outputs") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_yaml(self, decision, filename: str) -> Path:
        path = self.output_dir / filename

        clean_output = {
            "assignment_id": decision.assignment_id,
            "task_id": decision.task_id,
            "status": decision.status,
            "selected_channel": decision.selected_channel,
            "selected_owner_type": decision.selected_owner_type,
            "selected_owner": decision.selected_owner,
            "selected_assignee": decision.selected_assignee,
            "confidence_score": round(decision.confidence_score, 2),
            "reasons": decision.reasons[:3],
            "top_candidates": [
                {
                    "assignee_id": c.assignee_id,
                    "name": c.name,
                    "role": c.role,
                    "composite_score": round(c.composite_score, 2),
                    "hard_rule_passed": c.hard_rule_passed,
                }
                for c in (decision.candidate_rankings or [])[:3]
            ],
            "escalation_required": decision.escalation_required,
            "escalation_reason": decision.escalation_reason,
            "audit_log_id": decision.audit_log_id,
            "orchestrator_action": decision.orchestrator_action,
            "timestamp": (
                decision.timestamp.isoformat()
                if getattr(decision, "timestamp", None)
                else None
            ),
        }

        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                clean_output,
                f,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            )

        return path