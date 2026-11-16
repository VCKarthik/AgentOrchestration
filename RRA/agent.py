"""
Risk Radar Agent — Main entrypoint.

The orchestrator calls `RiskRadarAgent().evaluate(case)` and receives a
fully-populated RiskRadarOutput matching the Sprint 4 schema.

Architecture:
  1. Detect operating context (full vs partial upstream data)
  2. Run each enabled rule over the case
  3. Collect RiskItems
  4. Consolidate severity / proceed / escalation (pure function)
  5. Generate reasoning summary (LLM or fallback)
  6. Assemble output
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from .packet_parser import PacketStore, parse_packet
from .rules import (DeadlineRule, MissingInputRule, DependencyRule,
                    HistoricalDelayRule, ComplianceRule, Rule)
from .schema import (
    CaseInput,
    OperatingContext,
    RiskItem,
    RiskRadarOutput,
)
from .severity import consolidate
from .summarizer import Summarizer, default_summarizer


# Fields we expect in a "full" context packet. Missing any of these
# downgrades us to "partial" — which, per the Sprint 4 spec, affects
# escalation confidence.
FULL_CONTEXT_FIELDS = (
    "workflow_type",
    "workflow_state",
    "priority",
    "required_inputs",
    "sla_deadline",
)


class RiskRadarAgent:
    def __init__(
        self,
        rules: Optional[List[Rule]] = None,
        summarizer: Optional[Summarizer] = None,
        packet_store: Optional[PacketStore] = None,
    ):
        self.rules: List[Rule] = rules if rules is not None else [
            MissingInputRule(),
            DeadlineRule(),
            DependencyRule(),
            HistoricalDelayRule(),
            ComplianceRule(),
        ]
        self.summarizer  = summarizer  if summarizer  is not None else default_summarizer()
        self.packet_store = packet_store if packet_store is not None else PacketStore()

    def evaluate_packet(self, packet: dict) -> RiskRadarOutput:
        """Public entrypoint: take a CSA-style packet, parse it, evaluate."""
        parsed = parse_packet(packet)
        parsed.pop("_filename_matches", None)
        parsed.pop("_operating_partial", None)
        return self.evaluate(CaseInput.from_dict(parsed))

    def evaluate(self, case: CaseInput) -> RiskRadarOutput:
        # AGENT AUTONOMY: if no inputs are populated and we have a case_id,
        # look up the CSA packet store and parse the upstream packet ourselves.
        if not case.received_inputs and case.task_id:
            self.packet_store.reload()
            packet = self.packet_store.get_packet(case.task_id)
            if packet:
                parsed = parse_packet(packet)
                if not case.received_inputs:
                    case.received_inputs = list(parsed.get("received_inputs", []))
                if not case.mandatory_inputs:
                    case.mandatory_inputs = list(parsed.get("mandatory_inputs", []))
                if not case.required_inputs:
                    case.required_inputs = list(parsed.get("required_inputs", []))

        operating_context = self._detect_context(case)

        # Run all applicable rules. Each rule is isolated — one rule's
        # failure should not take down the agent.
        risk_items: List[RiskItem] = []
        for rule in self.rules:
            if not rule.applies(case):
                continue
            try:
                risk_items.extend(rule.evaluate(case))
            except Exception as exc:  # pragma: no cover - defensive
                # In production we'd log this; for now, we surface it as
                # an ambiguity risk so the case gets human review.
                from .schema import RiskType as _RT, Severity as _S
                risk_items.append(RiskItem(
                    risk_type=_RT.AMBIGUITY_RISK,
                    severity=_S.MEDIUM,
                    reason=f"Rule '{rule.name}' failed to evaluate: {exc}",
                    blocking=False,
                ))

        decision = consolidate(risk_items, case, operating_context)

        reasoning = self.summarizer.summarize(
            risk_items=risk_items,
            overall=decision.overall_risk_level,
            can_proceed=decision.can_proceed,
            workflow_type=case.workflow_type,
        )

        model_used = (
            "rules-only"
            if self.summarizer.__class__.__name__ == "RuleBasedSummarizer"
            else "rules-plus-llm-summary"
        )

        return RiskRadarOutput(
            task_id=case.task_id,
            workflow_state=case.workflow_state,
            priority=case.priority,
            risk_items=risk_items,
            overall_risk_level=decision.overall_risk_level,
            can_proceed=decision.can_proceed,
            escalate_to_human=decision.escalate_to_human,
            escalation_target=decision.escalation_target,
            reasoning_summary=reasoning,
            operating_context=operating_context,
            model_used=model_used,
            timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    def _detect_context(case: CaseInput) -> OperatingContext:
        for field in FULL_CONTEXT_FIELDS:
            value = getattr(case, field, None)
            if value is None or (isinstance(value, list) and len(value) == 0):
                return OperatingContext.PARTIAL
        return OperatingContext.FULL
