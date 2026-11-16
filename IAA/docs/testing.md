# Testing — IAA

## Overview

75 unit tests in `test_iaa.py`. Zero API calls in default runs.
All tests pass without a `GOOGLE_API_KEY` or `OPENAI_API_KEY`.

## How the LLM Mock Works

`conftest.py` registers an `autouse=True` fixture (`mock_llm_globally`) that fires
for every test that is not marked `@pytest.mark.integration`.

The fixture patches `agent.chain.get_llm` to return a `MagicMock` that cycles
through three pre-baked JSON strings matching the three chain steps:

- Step 1 (Contextualize): plain-text process summary
- Step 2 (Anticipate): JSON with `predicted_actions`, `task_list`, `workflow_timeline`
- Step 3 (Recommend): JSON with `action_id`, `label`, `confidence`, `justification`

Mock responses defined at `conftest.py:14–44`.
Patch applied at `conftest.py:63`: `patch("agent.chain.get_llm", ...)`.

The retriever is NOT mocked by default — it runs against the real Qdrant store
(or returns `[]` gracefully if the store is empty).

## Running Tests

```bash
# All unit tests (default — no API key needed)
pytest test_iaa.py -v

# Single test by name
pytest test_iaa.py -v -k "test_run_iaa"

# Integration tests only (requires GOOGLE_API_KEY)
pytest test_iaa.py -v -m integration

# Skip integration tests explicitly
pytest test_iaa.py -v -m "not integration"
```

## Test Structure

Tests cover:
- `build_process_state()` — event list → ProcessState construction
- `run_iaa()` — full pipeline with mocked LLM
- Rule overrides — high risk forces escalation, low confidence flags escalate
- `iaa_node()` — LangGraph wrapper, missing state fallback, upstream supplement
- `IAARetriever` — injected mock client, query construction, format_for_prompt
- `agent/api.py` — FastAPI endpoints via `TestClient`
- Schema validation — Pydantic models, field constraints

## Adding Tests

Mark integration tests that need a real API key:

```python
@pytest.mark.integration
def test_real_llm_call():
    ...
```

Integration tests are skipped in default `pytest` runs and in CI.
Inject a mock retriever via `run_iaa(state, retriever=mock_retriever)` to isolate
chain logic from vector store state.
