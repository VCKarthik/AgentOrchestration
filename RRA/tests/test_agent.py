"""
Risk Radar Agent — End-to-end tests.

Proves the three promised outcomes from the Sprint 4 spec:
  - proceed (clean case)
  - hold   (risks present, not escalating)
  - escalate (critical / compliance / blocking)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the package importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from risk_radar.agent import RiskRadarAgent
from risk_radar.schema import (
    OperatingContext,
    ProceedDecision,
    RiskType,
    Severity,
)
from risk_radar.summarizer import RuleBasedSummarizer
from risk_radar.tests.fixture_builders import (
    clean_case,
    escalate_case,
    hold_case,
    partial_context_case,
)


def make_agent() -> RiskRadarAgent:
    # Force deterministic summarizer in tests — no API calls.
    return RiskRadarAgent(summarizer=RuleBasedSummarizer())


# ---------- Tests ----------

def test_clean_case_proceeds():
    out = make_agent().evaluate(clean_case())

    assert out.risk_items == [], f"expected no risks, got {out.risk_items}"
    assert out.overall_risk_level == Severity.LOW
    assert out.can_proceed == ProceedDecision.PROCEED
    assert out.escalate_to_human is False
    assert out.escalation_target is None
    assert out.operating_context == OperatingContext.FULL
    assert out.task_id == "T1001"
    print("  [PASS] clean case proceeds")


def test_hold_case():
    """Non-mandatory missing + SLA in medium window -> caution or hold."""
    out = make_agent().evaluate(hold_case())

    risk_types = {item.risk_type for item in out.risk_items}
    assert RiskType.MISSING_INPUT in risk_types, f"expected missing_input, got {risk_types}"
    assert RiskType.DEADLINE_RISK in risk_types, f"expected deadline_risk, got {risk_types}"

    # Non-mandatory miss -> MEDIUM, non-blocking
    missing = [i for i in out.risk_items if i.risk_type == RiskType.MISSING_INPUT][0]
    assert missing.severity == Severity.MEDIUM
    assert missing.blocking is False

    assert out.overall_risk_level.rank >= Severity.MEDIUM.rank
    assert out.can_proceed in {ProceedDecision.HOLD, ProceedDecision.CAUTION}
    assert out.operating_context == OperatingContext.FULL
    print(f"  [PASS] hold case: overall={out.overall_risk_level.value}, "
          f"proceed={out.can_proceed.value}, escalate={out.escalate_to_human}")


def test_escalate_case():
    """Mandatory compliance doc missing + policy_flag + breached SLA -> critical, escalate."""
    out = make_agent().evaluate(escalate_case())

    # Mandatory doc missing + policy_flag -> CRITICAL blocking
    mandatory_miss = [
        i for i in out.risk_items
        if i.risk_type == RiskType.MISSING_INPUT and i.blocking
    ]
    assert len(mandatory_miss) == 1, f"expected 1 blocking missing_input, got {len(mandatory_miss)}"
    assert mandatory_miss[0].severity == Severity.CRITICAL

    # SLA breached -> CRITICAL blocking
    sla_items = [i for i in out.risk_items if i.risk_type == RiskType.DEADLINE_RISK]
    assert len(sla_items) == 1
    assert sla_items[0].severity == Severity.CRITICAL
    assert sla_items[0].blocking is True

    assert out.overall_risk_level == Severity.CRITICAL
    assert out.can_proceed == ProceedDecision.HOLD
    assert out.escalate_to_human is True
    assert out.escalation_target is not None
    print(f"  [PASS] escalate case: target={out.escalation_target}")


def test_schema_stable_under_partial_context():
    """Even with minimal context, all Sprint 4 fields must be present."""
    out = make_agent().evaluate(partial_context_case())

    d = out.to_dict()
    required_fields = [
        "task_id", "workflow_state", "priority", "risk_items",
        "overall_risk_level", "can_proceed", "escalate_to_human",
        "escalation_target", "reasoning_summary", "operating_context",
        "model_used", "timestamp",
    ]
    for fname in required_fields:
        assert fname in d, f"missing field: {fname}"

    assert out.operating_context == OperatingContext.PARTIAL
    print("  [PASS] schema stable under partial context")


def test_reasoning_summary_always_populated():
    agent = make_agent()
    for name, builder in [
        ("clean", clean_case), ("hold", hold_case), ("escalate", escalate_case),
    ]:
        out = agent.evaluate(builder())
        assert out.reasoning_summary, f"empty summary for {name}"
    print("  [PASS] reasoning summary always populated")


def test_output_serializes_to_json():
    """Sprint 4 promised JSON output; prove it round-trips."""
    import json
    out = make_agent().evaluate(escalate_case())
    s = out.to_json()
    parsed = json.loads(s)
    assert parsed["task_id"] == "T1003"
    assert parsed["overall_risk_level"] == "critical"
    assert parsed["escalate_to_human"] is True
    print("  [PASS] output serializes to JSON")


if __name__ == "__main__":
    print("\nRunning Risk Radar Agent tests...\n")
    test_clean_case_proceeds()
    test_hold_case()
    test_escalate_case()
    test_schema_stable_under_partial_context()
    test_reasoning_summary_always_populated()
    test_output_serializes_to_json()
    print("\nAll tests passed.\n")
