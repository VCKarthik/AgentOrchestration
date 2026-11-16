"""
Root conftest.py — auto-mocks the LLM for every test.

Any test that needs real API access must mark itself with:
    @pytest.mark.integration

and will be skipped from default runs with `-m "not integration"`.
"""
import json
import pytest
from unittest.mock import MagicMock, patch


MOCK_STEP1 = (
    "The process is at documentation stage with medium risk. "
    "Missing documentation flag detected."
)

MOCK_STEP2 = json.dumps({
    "predicted_actions": [
        {"action_id": "request_missing_document", "label": "Request missing document",
         "confidence": 0.88, "reasoning": "Documentation gap detected"},
        {"action_id": "escalate_for_approval", "label": "Escalate for approval",
         "confidence": 0.72, "reasoning": "Medium risk requires review"},
    ],
    "task_list": [
        {"task_id": "T001", "action": "request_missing_document",
         "assigned_role": "document_analyst", "priority": "high",
         "depends_on": [], "reasoning": "Required before proceeding"},
    ],
    "workflow_timeline": [
        {"step": 1, "event_type": "claim_submitted", "actor": "customer",
         "status": "completed", "timestamp": None},
        {"step": 2, "event_type": "documentation_incomplete", "actor": "analyst",
         "status": "current", "timestamp": None},
    ],
})

MOCK_STEP3 = json.dumps({
    "action_id": "request_missing_document",
    "label": "Request missing document",
    "confidence": 0.88,
    "justification": "A required document is missing. Request it before proceeding.",
})


@pytest.fixture(autouse=True)
def mock_llm_globally(request):
    if request.node.get_closest_marker("integration"):
        yield
        return

    mock_llm = MagicMock()
    responses = [MOCK_STEP1, MOCK_STEP2, MOCK_STEP3]
    call_count = [0]

    def side_effect(prompt):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        return MagicMock(content=responses[idx])

    mock_llm.invoke.side_effect = side_effect
    with patch("agent.chain.get_llm", return_value=mock_llm):
        yield mock_llm
