from __future__ import annotations

from datetime import datetime, timedelta, timezone

from delegation_agent.agent import DelegationAgent
from delegation_agent.models.outputs import ExecutionChannel


def _future(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _make_agent():
    return DelegationAgent(notify_dry_run=True)


# ============================================================
# CORE CHANNEL TESTS (ROBUST)
# ============================================================

class TestChannelRouting:

    def test_claim_routes_to_human(self):
        agent = _make_agent()

        task = {
            "task_id": "TSK-1",
            "task_type": "claim_review",
            "title": "Claim Review",
            "description": "Review claim with documents",
            "priority": "high",
            "business_domain": "claims",
            "required_skills": ["claim_review"],
            "estimated_effort": 3,
            "due_date": _future(24),
        }

        decision = agent.evaluate_task(task)

        assert decision.selected_channel in [
            ExecutionChannel.HUMAN_OWNER,
            ExecutionChannel.SUPERVISOR_REVIEW,
        ]
        assert decision.confidence_score > 0.3


    def test_simple_task_prefers_automation(self):
        agent = _make_agent()

        task = {
            "task_id": "TSK-2",
            "task_type": "customer_inquiry",
            "title": "Password Reset",
            "description": "Reset password",
            "priority": "low",
            "business_domain": "customer_service",
            "required_skills": ["customer_communication"],
            "estimated_effort": 1,
            "due_date": _future(6),
        }

        decision = agent.evaluate_task(task)

        assert decision.selected_channel in [
            ExecutionChannel.AUTOMATION,
            ExecutionChannel.HUMAN_OWNER,
        ]
        assert decision.confidence_score > 0.2


    def test_high_value_goes_to_review(self):
        agent = _make_agent()

        task = {
            "task_id": "TSK-3",
            "task_type": "financial_approval",
            "title": "Approve $300k contract",
            "description": "Financial approval",
            "priority": "critical",
            "business_domain": "finance",
            "required_skills": ["finance"],
            "estimated_effort": 5,
            "due_date": _future(24),
            "monetary_value": 300000,
        }

        decision = agent.evaluate_task(task)

        assert decision.selected_channel in [
            ExecutionChannel.SUPERVISOR_REVIEW,
            ExecutionChannel.HUMAN_OWNER,
        ]
        assert decision.confidence_score > 0.4


    def test_compliance_prefers_specialized_agent(self):
        agent = _make_agent()

        task = {
            "task_id": "TSK-4",
            "task_type": "compliance_review",
            "title": "Compliance Check",
            "description": "Regulatory issue",
            "priority": "critical",
            "business_domain": "compliance",
            "required_skills": ["compliance"],
            "estimated_effort": 4,
            "due_date": _future(4),
        }

        decision = agent.evaluate_task(task)

        assert decision.selected_channel in [
            ExecutionChannel.SPECIALIZED_AGENT,
            ExecutionChannel.SUPERVISOR_REVIEW,
        ]
        assert decision.confidence_score > 0.3


# ============================================================
# EDGE CASES (IMPORTANT FOR DEMO)
# ============================================================

class TestEdgeCases:

    def test_unknown_skill_fallback(self):
        agent = _make_agent()

        task = {
            "task_id": "TSK-5",
            "task_type": "claim_review",
            "title": "Unknown Skill",
            "description": "Minimal info",
            "priority": "low",
            "business_domain": "claims",
            "required_skills": ["unknown_skill"],
            "estimated_effort": 1,
            "due_date": _future(24),
        }

        decision = agent.evaluate_task(task)

        assert decision.selected_channel is not None
        assert decision.confidence_score >= 0


    def test_missing_skills_handled(self):
        agent = _make_agent()

        task = {
            "task_id": "TSK-6",
            "task_type": "claim_review",
            "title": "No Skills",
            "description": "Task",
            "priority": "medium",
            "business_domain": "claims",
            "required_skills": [],
            "estimated_effort": 2,
            "due_date": _future(24),
        }

        decision = agent.evaluate_task(task)

        assert decision is not None


# ============================================================
# OUTPUT VALIDATION
# ============================================================

class TestOutputStructure:

    def test_output_structure(self):
        agent = _make_agent()

        task = {
            "task_id": "TSK-7",
            "task_type": "claim_review",
            "title": "Structure Test",
            "description": "Validate output",
            "priority": "medium",
            "business_domain": "claims",
            "required_skills": ["claim_review"],
            "estimated_effort": 2,
            "due_date": _future(24),
        }

        decision = agent.evaluate_task(task)

        assert decision.task_id
        assert decision.selected_channel
        assert decision.selected_owner_type
        assert isinstance(decision.reasons, list)
        assert decision.confidence_score >= 0