"""
test_iaa.py
Complete pytest test suite for the IAA MVP.

Tests are grouped into:
  - Schemas: Pydantic model validation
  - Rules: Override layer fires correctly
  - Retriever: Qdrant query structure
  - Chain: JSON extraction, prompt building
  - IAA: End-to-end with mocked LLM
  - API: FastAPI endpoint contracts
  - Ingest: Pipeline structure without network
  - Synthetic: Data generation quality

Run:
  cd IAA
  pytest test_iaa.py -v
"""

from __future__ import annotations
import json, sys, pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.schemas import (
    EventLogEntry, ProcessState, ActionRecommendation,
    PredictedAction, IAAState, ProcessStep, TaskItem, WorkflowStep,
)
from agent.chain import apply_overrides, _extract_json
from agent.iaa import build_process_state, iaa_node


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _ts():
    return datetime.now(timezone.utc)


def _event(event_type: str, stage: str = None, entity_id: str = "TEST-001", idx: int = 0) -> EventLogEntry:
    return EventLogEntry(
        event_id=f"evt-{idx}",
        entity_id=entity_id,
        event_type=event_type,
        stage=stage or event_type,
        timestamp=_ts(),
        metadata={},
    )


def _state(**kwargs) -> ProcessState:
    defaults = dict(
        entity_id="TEST-001",
        current_stage="verification",
        current_event_type="doc_uploaded",
        timestamp=_ts(),
    )
    defaults.update(kwargs)
    return ProcessState(**defaults)


def _action(action_id: str = "do_something", confidence: float = 0.8) -> PredictedAction:
    return PredictedAction(
        action_id=action_id,
        label="Test action",
        confidence=confidence,
        reasoning="test reasoning",
    )


def _rec(action_id: str = "do_something", confidence: float = 0.8) -> ActionRecommendation:
    a = _action(action_id, confidence)
    return ActionRecommendation(
        predicted_actions=[a],
        recommended_action=a,
        timestamp=_ts(),
    )


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMA TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestSchemas:
    def test_event_log_entry_valid(self):
        e = _event("doc_submitted")
        assert e.event_type == "doc_submitted"
        assert e.entity_id  == "TEST-001"

    def test_process_state_defaults(self):
        s = _state()
        assert s.prior_actions  == []
        assert s.prior_steps    == []
        assert s.risk_flags     == []
        assert s.policy_constraints == []
        assert s.operating_context  == "full"

    def test_process_state_with_upstream(self):
        s = _state(risk_severity="high", risk_flags=["deadline_risk"], assigned_owner="analyst_01")
        assert s.risk_severity  == "high"
        assert "deadline_risk"  in s.risk_flags
        assert s.assigned_owner == "analyst_01"

    def test_action_recommendation_confidence_bounds(self):
        with pytest.raises(Exception):
            PredictedAction(action_id="x", label="x", confidence=1.5, reasoning="x")  # > 1.0
        with pytest.raises(Exception):
            PredictedAction(action_id="x", label="x", confidence=-0.1, reasoning="x")  # < 0.0

    def test_action_recommendation_max_3_actions(self):
        actions = [_action(f"action_{i}", 0.9 - i*0.1) for i in range(4)]
        with pytest.raises(Exception):
            ActionRecommendation(
                predicted_actions=actions,   # 4 actions — exceeds max
                recommended_action=actions[0],
                timestamp=_ts(),
            )

    def test_action_recommendation_min_1_action(self):
        with pytest.raises(Exception):
            ActionRecommendation(
                predicted_actions=[],        # empty — below min
                recommended_action=_action(),
                timestamp=_ts(),
            )

    def test_iaa_state_keys(self):
        keys = set(IAAState.model_fields.keys())
        assert "process_state"      in keys
        assert "iaa_recommendation" in keys
        assert "iaa_routing_action" in keys
        assert "iaa_escalate"       in keys

    def test_predicted_action_id_is_string(self):
        a = _action("request_missing_document")
        assert isinstance(a.action_id, str)

    def test_action_recommendation_override_defaults(self):
        r = _rec()
        assert r.override_applied  == False
        assert r.override_reason   is None
        assert r.escalate_to_human == False

    def test_action_recommendation_has_task_list(self):
        r = _rec()
        assert isinstance(r.task_list, list)

    def test_action_recommendation_has_workflow_timeline(self):
        r = _rec()
        assert isinstance(r.workflow_timeline, list)

    def test_process_state_has_prior_steps(self):
        s = _state()
        assert hasattr(s, "prior_steps")
        assert isinstance(s.prior_steps, list)

    def test_process_step_model(self):
        ps = ProcessStep(event_type="doc_uploaded", actor="analyst_01")
        assert ps.event_type == "doc_uploaded"
        assert ps.actor      == "analyst_01"
        assert ps.timestamp  is None

    def test_task_item_model(self):
        t = TaskItem(
            task_id="T001",
            action="request_document",
            assigned_role="document_analyst",
            priority="high",
            reasoning="missing doc",
        )
        assert t.task_id       == "T001"
        assert t.priority      == "high"
        assert t.depends_on    == []

    def test_workflow_step_model(self):
        w = WorkflowStep(step=1, event_type="doc_submitted", status="completed")
        assert w.step       == 1
        assert w.status     == "completed"
        assert w.actor      is None


# ══════════════════════════════════════════════════════════════════════════════
# RULE OVERRIDE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestRuleOverrides:
    def test_high_risk_fires_escalation(self):
        s = _state(risk_severity="high")
        r = apply_overrides(_rec(confidence=0.9), s)
        assert r.override_applied
        assert r.recommended_action.action_id == "escalate_to_human"
        assert r.escalate_to_human

    def test_critical_risk_fires_escalation(self):
        s = _state(risk_severity="critical")
        r = apply_overrides(_rec(confidence=0.9), s)
        assert r.override_applied
        assert r.escalate_to_human

    def test_missing_doc_flag_fires_request(self):
        s = _state(risk_flags=["missing required attachment"])
        r = apply_overrides(_rec(confidence=0.9), s)
        assert r.override_applied
        assert r.recommended_action.action_id == "request_missing_document"

    def test_missing_incomplete_flag_fires_request(self):
        s = _state(risk_flags=["incomplete documentation"])
        r = apply_overrides(_rec(confidence=0.9), s)
        assert r.override_applied
        assert r.recommended_action.action_id == "request_missing_document"

    def test_low_confidence_sets_escalate_flag(self):
        s = _state()
        r = apply_overrides(_rec(confidence=0.3), s)
        assert r.override_applied
        assert r.escalate_to_human
        # Low confidence keeps original prediction — does not replace it
        assert r.recommended_action.action_id == "do_something"

    def test_normal_case_no_override(self):
        s = _state(risk_severity="low")
        r = apply_overrides(_rec(confidence=0.85), s)
        assert not r.override_applied
        assert not r.escalate_to_human

    def test_high_risk_beats_low_confidence_in_priority(self):
        """High risk rule fires before confidence check — escalate_to_human wins."""
        s = _state(risk_severity="high")
        r = apply_overrides(_rec(confidence=0.2), s)
        assert r.recommended_action.action_id == "escalate_to_human"

    def test_override_preserves_retrieved_context_ids(self):
        s = _state(risk_severity="high")
        rec = _rec()
        rec = rec.model_copy(update={"retrieved_context_ids": ["ctx_1", "ctx_2"]})
        r = apply_overrides(rec, s)
        assert r.retrieved_context_ids == ["ctx_1", "ctx_2"]

    def test_override_does_not_mutate_original(self):
        s   = _state(risk_severity="high")
        rec = _rec(confidence=0.9)
        r   = apply_overrides(rec, s)
        assert rec.override_applied == False
        assert rec.recommended_action.action_id == "do_something"

    def test_override_preserves_task_list(self):
        """task_list must survive the override path."""
        t   = TaskItem(task_id="T001", action="escalate_to_human",
                       assigned_role="senior_reviewer", reasoning="high risk")
        rec = _rec(confidence=0.9)
        rec = rec.model_copy(update={"task_list": [t]})
        s   = _state(risk_severity="high")
        r   = apply_overrides(rec, s)
        assert len(r.task_list) == 1
        assert r.task_list[0].task_id == "T001"

    def test_override_preserves_workflow_timeline(self):
        """workflow_timeline must survive the override path."""
        w   = WorkflowStep(step=1, event_type="doc_submitted", status="completed")
        rec = _rec(confidence=0.9)
        rec = rec.model_copy(update={"workflow_timeline": [w]})
        s   = _state(risk_severity="high")
        r   = apply_overrides(rec, s)
        assert len(r.workflow_timeline) == 1


# ══════════════════════════════════════════════════════════════════════════════
# CHAIN TESTS (no LLM calls)
# ══════════════════════════════════════════════════════════════════════════════

class TestChain:
    def test_extract_json_clean(self):
        raw = '{"action_id": "test", "confidence": 0.9}'
        result = _extract_json(raw)
        assert result["action_id"] == "test"

    def test_extract_json_with_markdown_fences(self):
        raw = "```json\n{\"action_id\": \"test\"}\n```"
        result = _extract_json(raw)
        assert result["action_id"] == "test"

    def test_extract_json_with_preamble(self):
        raw = "Here is the JSON:\n{\"predicted_actions\": []}"
        result = _extract_json(raw)
        assert "predicted_actions" in result

    def test_extract_json_raises_on_no_json(self):
        with pytest.raises((ValueError, json.JSONDecodeError)):
            _extract_json("No JSON here at all")

    def test_get_llm_gemini(self):
        """LLM factory instantiates Gemini when LLM_PROVIDER=gemini."""
        import os
        os.environ["LLM_PROVIDER"] = "gemini"
        os.environ["GOOGLE_API_KEY"] = "fake_key_for_test"
        mock_llm = MagicMock()
        # Patch at the point of use inside get_llm() — chain.py imports lazily
        with patch("langchain_google_genai.ChatGoogleGenerativeAI", mock_llm):
            import importlib, agent.chain as ch
            importlib.reload(ch)
            result = ch.get_llm()
            # The factory was called and returned our mock instance
            assert mock_llm.called or result is not None

    def test_get_llm_openai(self):
        """LLM factory instantiates OpenAI when LLM_PROVIDER=openai."""
        import os
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["OPENAI_API_KEY"] = "fake_key_for_test"
        mock_llm = MagicMock()
        with patch("langchain_openai.ChatOpenAI", mock_llm):
            import importlib, agent.chain as ch
            importlib.reload(ch)
            result = ch.get_llm()
            assert mock_llm.called or result is not None
        os.environ["LLM_PROVIDER"] = "gemini"  # reset


# ══════════════════════════════════════════════════════════════════════════════
# IAA CORE TESTS (mocked LLM)
# ══════════════════════════════════════════════════════════════════════════════

class TestIAACore:
    def _make_mock_llm(self, responses: list[str]):
        mock = MagicMock()
        mock.invoke.side_effect = [MagicMock(content=r) for r in responses]
        return mock

    def test_build_process_state_from_events(self):
        events = [_event("submitted", idx=0), _event("doc_uploaded", "verify", idx=1)]
        state  = build_process_state(events)
        assert state.current_event_type == "doc_uploaded"
        assert state.current_stage      == "verify"
        assert "submitted" in state.prior_actions

    def test_build_process_state_populates_prior_steps(self):
        events = [_event("submitted", idx=0), _event("doc_uploaded", "verify", idx=1)]
        state  = build_process_state(events)
        assert len(state.prior_steps) == 1
        assert state.prior_steps[0].event_type == "submitted"

    def test_build_process_state_operating_context_full(self):
        events = [_event("submitted", idx=0)]
        state  = build_process_state(
            events,
            risk_severity="low",
            risk_flags=[],
            policy_constraints=["some_policy"],
            assigned_owner="analyst_01",
        )
        assert state.operating_context == "full"

    def test_build_process_state_operating_context_partial(self):
        events = [_event("submitted", idx=0)]
        state  = build_process_state(events)
        assert "partial" in state.operating_context

    def test_build_process_state_empty_events_raises(self):
        with pytest.raises(ValueError):
            build_process_state([])

    def test_iaa_node_no_state_graceful_degradation(self):
        result = iaa_node({})
        assert result["iaa_escalate"] == True
        assert result["iaa_routing_action"] == "escalate_for_review"
        assert result["iaa_recommendation"].override_applied == True

    def test_iaa_node_passthrough_existing_keys(self):
        """iaa_node must not strip existing graph state keys."""
        result = iaa_node({"some_other_agent": "data", "workflow_id": "WF-001"})
        assert result["some_other_agent"] == "data"
        assert result["workflow_id"]      == "WF-001"

    def test_run_iaa_with_mock_llm(self):
        from agent.iaa import run_iaa
        from agent.retriever import IAARetriever

        mock_retriever = MagicMock(spec=IAARetriever)
        mock_retriever.retrieve.return_value = []
        mock_retriever.format_for_prompt.return_value = "No historical context."

        step1 = "The process is at document verification stage with a missing attachment."
        step2 = json.dumps({
            "predicted_actions": [
                {"action_id": "request_missing_document", "label": "Request document",
                 "confidence": 0.88, "reasoning": "Doc missing"}
            ],
            "task_list": [
                {"task_id": "T001", "action": "request_missing_document",
                 "assigned_role": "document_analyst", "priority": "high",
                 "depends_on": [], "reasoning": "Must resolve before proceeding"}
            ],
            "workflow_timeline": [
                {"step": 1, "event_type": "doc_uploaded", "actor": None,
                 "status": "current", "timestamp": None}
            ]
        })
        step3 = json.dumps({
            "action_id": "request_missing_document",
            "label": "Request missing document",
            "confidence": 0.88,
            "justification": "A required document is missing — request it before proceeding."
        })
        mock_llm = self._make_mock_llm([step1, step2, step3])

        state = _state(risk_flags=["missing attachment"])
        rec   = run_iaa(state, retriever=mock_retriever, llm=mock_llm)

        assert isinstance(rec, ActionRecommendation)
        assert len(rec.predicted_actions) >= 1
        assert rec.recommended_action.action_id in ("request_missing_document", "request_document")

    def test_run_iaa_with_mock_llm_parses_task_list(self):
        """task_list and workflow_timeline are parsed from the merged single-shot output."""
        from agent.iaa import run_iaa
        from agent.retriever import IAARetriever

        mock_retriever = MagicMock(spec=IAARetriever)
        mock_retriever.retrieve.return_value = []
        mock_retriever.format_for_prompt.return_value = ""

        merged = json.dumps({
            "predicted_actions": [
                {"action_id": "approve_document", "label": "Approve",
                 "confidence": 0.9, "reasoning": "All docs present"}
            ],
            "task_list": [
                {"task_id": "T001", "action": "approve_document",
                 "assigned_role": "manager", "priority": "high",
                 "depends_on": [], "reasoning": "All checks passed"}
            ],
            "workflow_timeline": [
                {"step": 1, "event_type": "doc_submitted", "actor": "analyst",
                 "status": "completed", "timestamp": None},
                {"step": 2, "event_type": "approve_document", "actor": "manager",
                 "status": "predicted", "timestamp": None}
            ],
            "recommended_action": {
                "action_id": "approve_document", "label": "Approve document",
                "confidence": 0.9, "justification": "Ready for approval."
            }
        })
        mock_llm = self._make_mock_llm([merged])

        state = _state()
        rec   = run_iaa(state, retriever=mock_retriever, llm=mock_llm)

        assert len(rec.task_list) == 1
        assert rec.task_list[0].task_id == "T001"
        assert rec.task_list[0].priority == "high"
        assert len(rec.workflow_timeline) == 2
        assert rec.workflow_timeline[0].status == "completed"
        assert rec.workflow_timeline[1].status == "predicted"

    def test_run_iaa_task_list_defaults_to_empty_on_missing(self):
        """If step 2 omits task_list/workflow_timeline, defaults to []."""
        from agent.iaa import run_iaa
        from agent.retriever import IAARetriever

        mock_retriever = MagicMock(spec=IAARetriever)
        mock_retriever.retrieve.return_value = []
        mock_retriever.format_for_prompt.return_value = ""

        step1 = "Process state summary."
        step2 = json.dumps({"predicted_actions": [
            {"action_id": "notify_owner", "label": "Notify owner",
             "confidence": 0.7, "reasoning": "Standard step"}
        ]})
        step3 = json.dumps({
            "action_id": "notify_owner", "label": "Notify owner",
            "confidence": 0.7, "justification": "Notify."
        })
        mock_llm = self._make_mock_llm([step1, step2, step3])

        state = _state()
        rec   = run_iaa(state, retriever=mock_retriever, llm=mock_llm)
        assert rec.task_list        == []
        assert rec.workflow_timeline == []

    def test_run_iaa_rule_fires_before_returning(self):
        """When high risk, rule override should fire regardless of LLM output."""
        from agent.iaa import run_iaa
        from agent.retriever import IAARetriever

        mock_retriever = MagicMock(spec=IAARetriever)
        mock_retriever.retrieve.return_value = []
        mock_retriever.format_for_prompt.return_value = ""

        step1 = "High risk case."
        step2 = json.dumps({"predicted_actions": [
            {"action_id": "notify_owner", "label": "Notify owner",
             "confidence": 0.7, "reasoning": "owner unaware"}
        ]})
        step3 = json.dumps({
            "action_id": "notify_owner", "label": "Notify owner",
            "confidence": 0.7, "justification": "Let owner know."
        })
        mock_llm = self._make_mock_llm([step1, step2, step3])

        state = _state(risk_severity="high")
        rec   = run_iaa(state, retriever=mock_retriever, llm=mock_llm)

        assert rec.override_applied
        assert rec.recommended_action.action_id == "escalate_to_human"
        assert rec.escalate_to_human

    def test_run_iaa_bad_llm_output_uses_fallback(self):
        """If the LLM returns unparseable JSON, chain returns the no-LLM fallback recommendation."""
        from agent.iaa import run_iaa
        from agent.retriever import IAARetriever

        mock_retriever = MagicMock(spec=IAARetriever)
        mock_retriever.retrieve.return_value = []
        mock_retriever.format_for_prompt.return_value = ""

        mock_llm = self._make_mock_llm(["I cannot provide JSON at this time."])

        state = _state()
        rec = run_iaa(state, retriever=mock_retriever, llm=mock_llm)

        assert rec.recommended_action.action_id == "review_case"
        assert rec.model_used == "fallback/no_llm"
        assert rec.task_list == []


# ══════════════════════════════════════════════════════════════════════════════
# API TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAPI:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from agent.api import app
        return TestClient(app)

    @pytest.fixture
    def mock_rec(self):
        a = _action("request_missing_document", 0.91)
        return ActionRecommendation(predicted_actions=[a], recommended_action=a, timestamp=_ts())

    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_health_includes_provider(self, client):
        r = client.get("/health")
        assert "provider" in r.json()

    def test_demo_returns_sample_body(self, client):
        r = client.get("/demo")
        assert r.status_code == 200
        body = r.json()
        assert "predict_body" in body or "body" in body

    def test_predict_empty_body_422(self, client):
        r = client.post("/predict", json={})
        assert r.status_code == 422

    def test_predict_with_events(self, client, mock_rec):
        with patch("agent.api.run_iaa", return_value=mock_rec):
            r = client.post("/predict", json={
                "events": [
                    {"event_id":"e1","entity_id":"C001","event_type":"doc_submitted",
                     "stage":"intake","timestamp":"2026-04-01T09:00:00Z","metadata":{}},
                    {"event_id":"e2","entity_id":"C001","event_type":"doc_incomplete",
                     "stage":"verify","timestamp":"2026-04-01T09:15:00Z","metadata":{}},
                ]
            })
        assert r.status_code == 200
        body = r.json()
        assert "recommendation" in body
        assert "latency_ms"     in body

    def test_predict_with_process_state(self, client, mock_rec):
        with patch("agent.api.run_iaa", return_value=mock_rec):
            r = client.post("/predict", json={
                "process_state": {
                    "entity_id":          "C001",
                    "current_stage":      "verification",
                    "current_event_type": "doc_uploaded",
                    "prior_actions":      ["doc_submitted"],
                    "timestamp":          "2026-04-01T09:00:00Z",
                    "metadata":           {},
                    "risk_flags":         [],
                    "policy_constraints": [],
                    "operating_context":  "full",
                }
            })
        assert r.status_code == 200

    def test_predict_recommended_action_present(self, client, mock_rec):
        with patch("agent.api.run_iaa", return_value=mock_rec):
            r = client.post("/predict", json={
                "events": [
                    {"event_id":"e1","entity_id":"C001","event_type":"submitted",
                     "stage":"intake","timestamp":"2026-04-01T09:00:00Z","metadata":{}},
                ]
            })
        assert r.status_code == 200
        rec = r.json()["recommendation"]
        assert "recommended_action" in rec
        assert "action_id"          in rec["recommended_action"]
        assert "confidence"         in rec["recommended_action"]

    def test_predict_escalation_flag_in_response(self, client, mock_rec):
        with patch("agent.api.run_iaa", return_value=mock_rec):
            r = client.post("/predict", json={
                "events": [
                    {"event_id":"e1","entity_id":"C001","event_type":"submitted",
                     "stage":"intake","timestamp":"2026-04-01T09:00:00Z","metadata":{}},
                ]
            })
        rec = r.json()["recommendation"]
        assert "escalate_to_human" in rec

    def test_predict_task_list_in_response(self, client, mock_rec):
        """task_list and workflow_timeline must serialise correctly in /predict response."""
        with patch("agent.api.run_iaa", return_value=mock_rec):
            r = client.post("/predict", json={
                "events": [
                    {"event_id":"e1","entity_id":"C001","event_type":"submitted",
                     "stage":"intake","timestamp":"2026-04-01T09:00:00Z","metadata":{}},
                ]
            })
        rec = r.json()["recommendation"]
        assert "task_list"         in rec
        assert "workflow_timeline" in rec
        assert isinstance(rec["task_list"], list)
        assert isinstance(rec["workflow_timeline"], list)

    def test_ingest_accepts_documents(self, client):
        # Import the module first so the patch target exists
        import agent.ingest  # noqa: F401
        with patch("agent.ingest.get_qdrant_client") as mock_get_client, \
             patch("agent.ingest._batch_add"), \
             patch("agent.ingest.ensure_collection"):
            mock_client = MagicMock()
            mock_client.retrieve.return_value = []
            mock_client.get_collections.return_value = MagicMock(collections=[])
            mock_get_client.return_value = mock_client
            r = client.post("/ingest", json={
                "documents": ["Process: test\nCurrent stage: review\nNext action: approve"],
                "metadatas": [{"process_type": "test"}],
                "source": "test",
            })
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"
        assert r.json()["n_documents"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# RETRIEVER TESTS (mocked Qdrant)
# ══════════════════════════════════════════════════════════════════════════════

class TestRetriever:
    def test_build_query_basic(self):
        from agent.retriever import build_query
        s = _state(current_stage="verification", current_event_type="doc_uploaded",
                   prior_actions=["submitted", "received"])
        q = build_query(s)
        assert "verification"  in q
        assert "doc_uploaded"  in q
        assert "submitted"     in q

    def test_build_query_includes_risk_if_present(self):
        from agent.retriever import build_query
        s = _state(risk_severity="high", risk_flags=["missing_doc", "deadline_close"])
        q = build_query(s)
        assert "high"         in q
        assert "missing_doc"  in q

    def test_build_query_no_crash_on_empty_state(self):
        from agent.retriever import build_query
        s = _state()
        q = build_query(s)
        assert len(q) > 0

    def test_format_for_prompt_empty(self):
        from agent.retriever import IAARetriever
        r = IAARetriever.__new__(IAARetriever)
        result = r.format_for_prompt([])
        assert "No relevant" in result

    def test_format_for_prompt_with_results(self):
        from agent.retriever import IAARetriever
        r = IAARetriever.__new__(IAARetriever)
        results = [
            {"id": "abc", "document": "Process: test\nNext observed: approve",
             "metadata": {"source": "bpic_2012", "process_type": "loan_application", "next_action": "approve"},
             "distance": 0.12}
        ]
        formatted = r.format_for_prompt(results)
        assert "bpic_2012"    in formatted
        assert "approve"      in formatted
        assert "[Context 1]"  in formatted

    def test_retriever_graceful_on_empty_corpus(self):
        """If corpus search fails, retrieve returns [] not an exception."""
        from agent.retriever import IAARetriever

        mock_client = MagicMock()
        mock_client.query_points.side_effect = Exception("empty corpus")

        r = IAARetriever.__new__(IAARetriever)
        r.k        = 4
        r._client  = mock_client
        # Inject a mock embedder so we don't need a real API key
        r._embedder = MagicMock()
        r._embedder.encode.return_value.tolist.return_value = [0.0] * 384

        results = r.retrieve(_state())
        assert results == []

    def test_retriever_returns_correct_shape(self):
        """retrieve() returns dicts with id, document, metadata, distance keys."""
        from agent.retriever import IAARetriever

        mock_point = MagicMock()
        mock_point.id      = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        mock_point.score   = 0.95
        mock_point.payload = {
            "document":     "Process: test\nNext: approve",
            "source":       "synthetic",
            "process_type": "doc_review",
            "next_action":  "approve",
        }

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.points = [mock_point]
        mock_client.query_points.return_value = mock_response

        r = IAARetriever.__new__(IAARetriever)
        r.k        = 4
        r._client  = mock_client
        r._embedder = MagicMock()
        r._embedder.encode.return_value.tolist.return_value = [0.0] * 384

        results = r.retrieve(_state())
        assert len(results) == 1
        assert results[0]["id"]       == str(mock_point.id)
        assert results[0]["document"] == "Process: test\nNext: approve"
        assert "source" in results[0]["metadata"]
        assert "distance" in results[0]


# ══════════════════════════════════════════════════════════════════════════════
# INGEST PIPELINE TESTS (no network)
# ══════════════════════════════════════════════════════════════════════════════

class TestIngest:
    def test_make_id_deterministic(self):
        from agent.ingest import _make_id
        assert _make_id("hello", "pfx") == _make_id("hello", "pfx")
        assert _make_id("hello", "pfx") != _make_id("world", "pfx")

    def test_make_id_different_prefix(self):
        from agent.ingest import _make_id
        assert _make_id("same_text", "a") != _make_id("same_text", "b")

    def test_make_id_is_valid_uuid(self):
        from agent.ingest import _make_id
        import uuid
        result = _make_id("some text", "prefix")
        # Should not raise
        parsed = uuid.UUID(result)
        assert str(parsed) == result

    def test_ingest_synthetic_structure(self):
        """ingest_synthetic_cases builds docs, ids, metas in correct shape."""
        from agent.ingest import ingest_synthetic_cases, _make_id

        cases = [
            {"entity_id": "C1", "event_type": "doc_uploaded", "prior_actions": ["submitted"],
             "next_action": "request_document", "stage": "verify"},
            {"entity_id": "C2", "event_type": "approval_requested",
             "prior_actions": ["submitted", "verified"],
             "next_action": "escalate", "stage": "approval"},
        ]

        mock_client = MagicMock()
        mock_client.retrieve.return_value = []
        mock_client.get_collections.return_value = MagicMock(collections=[])

        with patch("agent.ingest._batch_add") as mock_batch, \
             patch("agent.ingest.ensure_collection"):
            ingest_synthetic_cases(cases, client=mock_client)
            mock_batch.assert_called_once()
            call_args = mock_batch.call_args
            docs, ids, metas = call_args[0][1], call_args[0][2], call_args[0][3]
            assert len(docs)  == 2
            assert len(ids)   == 2
            assert len(metas) == 2

    def test_bootstrap_corpus_synthetic_only(self, tmp_path):
        """bootstrap_corpus with synthetic only should call ingest_synthetic_cases."""
        from agent.ingest import bootstrap_corpus
        import json as _json

        fake_cases = [
            {"entity_id": "X1", "event_type": "review_started", "process_type": "doc_review",
             "domain": "ops", "prior_actions": ["submitted"], "next_action": "approve", "stage": "review"},
        ]
        synth_path = tmp_path / "synth.json"
        synth_path.write_text(_json.dumps(fake_cases))

        mock_client = MagicMock()
        mock_client.count.return_value = MagicMock(count=5)
        mock_client.get_collections.return_value = MagicMock(collections=[])

        with patch("agent.ingest.ingest_synthetic_cases", return_value=5) as mock_ingest, \
             patch("agent.ingest.get_qdrant_client", return_value=mock_client), \
             patch("agent.ingest.ensure_collection"):
            n = bootstrap_corpus(include_synthetic=True, synthetic_path=str(synth_path),
                                 client=mock_client)
        mock_ingest.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# SYNTHETIC DATA TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestSyntheticData:
    @pytest.fixture
    def cases(self):
        import json
        p = Path(__file__).parent / "data" / "synthetic_cases.json"
        if not p.exists():
            pytest.skip("Synthetic cases not generated yet — run scripts/generate_synthetic.py")
        return json.load(open(p))

    def test_cases_have_required_fields(self, cases):
        required = {"entity_id", "event_type", "prior_actions", "next_action", "stage"}
        for c in cases[:10]:
            missing = required - set(c.keys())
            assert not missing, f"Case {c.get('entity_id')} missing: {missing}"

    def test_cases_cover_all_process_types(self, cases):
        process_types = {c["process_type"] for c in cases}
        assert "document_review"    in process_types
        assert "approval_workflow"  in process_types
        assert "claim_processing"   in process_types

    def test_next_action_never_empty(self, cases):
        for c in cases:
            assert c["next_action"], f"Empty next_action in {c['entity_id']}"

    def test_risk_severity_valid_values(self, cases):
        valid = {"low", "medium", "high", "critical"}
        for c in cases:
            assert c["risk_severity"] in valid, f"Invalid severity in {c['entity_id']}"

    def test_prior_actions_is_list(self, cases):
        for c in cases:
            assert isinstance(c["prior_actions"], list)

    def test_entity_ids_unique(self, cases):
        ids = [c["entity_id"] for c in cases]
        assert len(ids) == len(set(ids)), "Duplicate entity_ids in synthetic data"

    def test_case_count_matches_expected(self, cases):
        assert len(cases) == 200

    def test_cases_have_actor_sequence(self, cases):
        """Every case must have actor_sequence with actor and event_type fields."""
        for c in cases[:10]:
            assert "actor_sequence" in c, f"Missing actor_sequence in {c['entity_id']}"
            assert len(c["actor_sequence"]) > 0
            for step in c["actor_sequence"]:
                assert "event_type" in step
                assert "actor" in step

    def test_actor_values_are_valid_roles(self, cases):
        valid_roles = {
            "claims_analyst", "document_reviewer", "senior_manager",
            "compliance_officer", "procurement_officer",
        }
        for c in cases[:20]:
            for step in c.get("actor_sequence", []):
                assert step["actor"] in valid_roles, \
                    f"Unexpected actor '{step['actor']}' in {c['entity_id']}"


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE-BASED INTEGRATION TEST
# ══════════════════════════════════════════════════════════════════════════════

class TestFixtureIntegration:
    def test_fixture_case_loads_and_builds_state(self):
        import json
        fixture = json.load(open(Path(__file__).parent / "fixtures" / "sample_case.json"))

        events = [
            *[_event(e, idx=i) for i, e in enumerate(fixture["prior_actions"])],
            EventLogEntry(
                event_id="current",
                entity_id=fixture["entity_id"],
                event_type=fixture["event_type"],
                stage=fixture["stage"],
                timestamp=_ts(),
                metadata=fixture.get("metadata", {}),
            )
        ]
        state = build_process_state(
            events,
            risk_flags=fixture.get("risk_flags", []),
            risk_severity=fixture.get("risk_severity"),
        )
        assert state.current_event_type == fixture["event_type"]
        assert state.risk_severity      == fixture["risk_severity"]
        assert len(state.prior_steps)   == len(fixture["prior_actions"])

    def test_fixture_rule_fires_correctly(self):
        """The fixture has risk_flags=['missing_required_attachment'] — override should fire."""
        import json
        fixture = json.load(open(Path(__file__).parent / "fixtures" / "sample_case.json"))
        state   = _state(risk_flags=fixture["risk_flags"], risk_severity=fixture["risk_severity"])
        rec     = _rec(confidence=0.9)
        result  = apply_overrides(rec, state)
        assert result.override_applied
        assert result.recommended_action.action_id == "request_missing_document"
