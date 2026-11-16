# Project AMP — ADK → LangGraph + Studio Migration Plan

## Context

**Why this change:** Google ADK's automatic function calling generates JSON schemas that Gemini
rejects for any non-primitive parameter type (`datetime`, `dict`, nested Pydantic). Two separate
bugs were hit and patched (ToolContext workaround), but the root mismatch remains: ADK expects
LLM-driven dynamic routing with simple schemas; AMP has deterministic routing with complex state.

**What we're moving to:** LangGraph StateGraph replaces ADK as the execution engine.
LangGraph Studio (free, local) replaces `adk web` as the interactive UI. The existing
`flow.py` routing logic and `tools.py` HTTP calls are reused almost entirely — this is
a rewiring, not a rewrite.

**What stays completely unchanged:**
- All 6 agent servers (CSA, RRA, GPA, IAA, DA, SWA) — zero agent code changes
- `orchestrator/schemas.py` — AmpState and all sub-models
- `orchestrator/shims.py` — all field-mapping logic
- `orchestrator/exceptions.py` — StagePartialFailureError
- All HTTP call logic in `tools.py` (_impl functions)

---

## Model + Session Strategy

**Session 1 (this session or next): Use Opus 4.7, low thinking**
- Architectural work: state.py, nodes.py, graph.py, flow.py rewrite
- Low thinking (not medium) — saves tokens, Opus reasoning still beats Sonnet for graph design

**Session 2: Use Sonnet 4.6, no thinking**
- Mechanical: delete agent.py, update requirements, langgraph.json, .env, test commands
- Sonnet is fast and cheap for file edits and verification

**Estimated with Claude Code:** 1.5–2 sessions of 5 hours. Not 2–3 days.
The IAA LangGraph reference already exists — we're adapting it, not inventing from scratch.

---

## Current File Inventory

```
orchestrator/
├── agent.py          ← DELETE (ADK root_agent — replaced by graph.py)
├── exceptions.py     ← KEEP unchanged
├── flow.py           ← REWRITE (back by LangGraph graph.ainvoke instead of asyncio calls)
├── requirements.txt  ← UPDATE (remove google-adk, add langgraph pin)
├── schemas.py        ← KEEP unchanged
├── shims.py          ← KEEP unchanged
├── tools.py          ← SIMPLIFY (keep _impl functions, delete ADK call_* wrappers)
IAA/orchestrator/
└── orchestrator.py   ← REFERENCE ONLY (SharedWorkflowState TypedDict, node patterns)
```

**New files to create:**
```
orchestrator/
├── state.py          ← NEW: AmpGraphState TypedDict for LangGraph
├── nodes.py          ← NEW: LangGraph node functions (wrap _impl calls)
└── graph.py          ← NEW: StateGraph construction + compile()
langgraph.json        ← NEW: LangGraph Studio config (project root)
```

---

## Phase 1 — state.py

**File:** `orchestrator/state.py`

LangGraph requires a TypedDict (or Pydantic v1 model) as graph state.
Map every AmpState field to a TypedDict key. All optional, None default.

```python
from __future__ import annotations
from typing import Optional, TypedDict
from .schemas import (
    TaskIntake, CsaOutput, RiskOutput, GovernanceOutput,
    IaaOutput, DaOutput, SwaOutput,
)

class AmpGraphState(TypedDict, total=False):
    # Input
    task_intake: Optional[TaskIntake]
    # Stage outputs
    csa_output: Optional[CsaOutput]
    risk_output: Optional[RiskOutput]
    governance_output: Optional[GovernanceOutput]
    iaa_output: Optional[IaaOutput]
    da_output: Optional[DaOutput]
    swa_result: Optional[SwaOutput]
    # Orchestrator-computed
    latency_log: dict[str, float]
    stage_errors: dict[str, str]
    requires_escalation: bool
    operating_context: str
```

**Why TypedDict not AmpState directly:** LangGraph merges node return dicts into state;
Pydantic models don't support partial dict merge cleanly. TypedDict with `total=False`
allows nodes to return only the fields they updated.

---

## Phase 2 — nodes.py

**File:** `orchestrator/nodes.py`

Each node receives `AmpGraphState`, builds an `AmpState` from it, calls the `_impl`
function, returns a dict of only the fields that changed.

Pattern (repeat for each agent):
```python
from .state import AmpGraphState
from .schemas import AmpState
from .tools import _call_csa_impl, _call_rra_impl, _call_gpa_impl, _call_iaa_impl, _call_da_impl, _run_swa_background
from .shims import compute_operating_context, compute_requires_escalation
import asyncio

def _build_amp_state(state: AmpGraphState) -> AmpState:
    """Reconstruct AmpState from LangGraph TypedDict state."""
    return AmpState(
        task_intake=state.get("task_intake"),
        csa_output=state.get("csa_output"),
        risk_output=state.get("risk_output"),
        governance_output=state.get("governance_output"),
        iaa_output=state.get("iaa_output"),
        da_output=state.get("da_output"),
        swa_result=state.get("swa_result"),
        latency_log=state.get("latency_log") or {},
        stage_errors=state.get("stage_errors") or {},
        requires_escalation=state.get("requires_escalation", False),
        operating_context=state.get("operating_context", "full"),
    )

async def csa_node(state: AmpGraphState) -> dict:
    s = _build_amp_state(state)
    await _call_csa_impl(s)
    # Fire SWA background immediately after CSA
    asyncio.create_task(_run_swa_background(s))
    return {
        "csa_output": s.csa_output,
        "latency_log": s.latency_log,
        "stage_errors": s.stage_errors,
    }

async def rra_node(state: AmpGraphState) -> dict:
    s = _build_amp_state(state)
    try:
        await _call_rra_impl(s)
    except Exception as exc:
        s.stage_errors["rra"] = type(exc).__name__
    return {"risk_output": s.risk_output, "latency_log": s.latency_log, "stage_errors": s.stage_errors}

async def gpa_node(state: AmpGraphState) -> dict:
    s = _build_amp_state(state)
    try:
        await _call_gpa_impl(s)
    except Exception as exc:
        s.stage_errors["gpa"] = type(exc).__name__
    return {"governance_output": s.governance_output, "latency_log": s.latency_log, "stage_errors": s.stage_errors}

async def iaa_node(state: AmpGraphState) -> dict:
    s = _build_amp_state(state)
    try:
        await _call_iaa_impl(s)
    except Exception as exc:
        s.stage_errors["iaa"] = type(exc).__name__
    return {"iaa_output": s.iaa_output, "latency_log": s.latency_log, "stage_errors": s.stage_errors}

async def da_node(state: AmpGraphState) -> dict:
    s = _build_amp_state(state)
    await _call_da_impl(s)
    return {
        "da_output": s.da_output,
        "requires_escalation": s.requires_escalation,
        "latency_log": s.latency_log,
        "stage_errors": s.stage_errors,
    }

async def stage2_node(state: AmpGraphState) -> dict:
    """
    Fan-out node: runs needed Stage 2 agents concurrently (asyncio.gather).
    Replicates flow.py _resolve_stage2 + asyncio.gather logic.
    Returns merged updates from all agents that ran.
    """
    from .flow_helpers import resolve_stage2_agents  # see Phase 3 note
    agents = resolve_stage2_agents(state)
    if not agents:
        return {}
    results = await asyncio.gather(*[fn(state) for fn in agents], return_exceptions=True)
    merged: dict = {"latency_log": state.get("latency_log") or {}, "stage_errors": state.get("stage_errors") or {}}
    for result in results:
        if isinstance(result, Exception):
            continue  # individual agent already logged to stage_errors
        merged.update(result)
    # D5: compute operating_context after Stage 2
    amp = _build_amp_state({**state, **merged})
    if amp.risk_output and amp.iaa_output:
        merged["operating_context"] = compute_operating_context(amp.risk_output, amp.iaa_output)
    return merged
```

**Note on SWA:** SWA is NOT removed. It fires as `asyncio.create_task(_run_swa_background(s))`
inside `csa_node` immediately after CSA completes — same fire-and-forget pattern as current
flow.py. `swa_result` still gets stored in state and returned in the final AmpState.
LangGraph does not need a SWA node because SWA is background-only, not part of the
sequential pipeline. The output is still visible in Studio's final state snapshot.

**Note on latency_log / stage_errors merging:** These are dicts that accumulate across nodes.
In LangGraph, if multiple nodes write to the same key, the last write wins. To properly merge,
use a custom reducer. Add to state.py:
```python
from typing import Annotated
import operator
# In AmpGraphState:
latency_log: Annotated[dict[str, float], lambda a, b: {**a, **b}]
stage_errors: Annotated[dict[str, str], lambda a, b: {**a, **b}]
```

---

## Phase 3 — flow_helpers.py (extract routing logic)

**File:** `orchestrator/flow_helpers.py`

Extract `_resolve_stage2` from `flow.py` so both `nodes.py` and `flow.py` can use it.
The routing keywords and logic are identical — just move to a shared module.

```python
# _RISK_KEYWORDS, _GOV_KEYWORDS, _IAA_KEYWORDS stay here
# resolve_stage2_agents(state: dict) -> list[Callable]
# Returns list of async node functions (rra_node, gpa_node, iaa_node) to run
```

This avoids duplicating routing logic between flow.py and nodes.py.

---

## Phase 4 — graph.py

**File:** `orchestrator/graph.py`

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from .state import AmpGraphState
from .nodes import csa_node, stage2_node, da_node

def build_graph(checkpointer=None):
    g = StateGraph(AmpGraphState)
    g.add_node("csa", csa_node)
    g.add_node("stage2", stage2_node)
    g.add_node("da", da_node)

    g.set_entry_point("csa")
    g.add_edge("csa", "stage2")
    g.add_edge("stage2", "da")
    g.add_edge("da", END)

    return g.compile(checkpointer=checkpointer or MemorySaver())

# Singleton for Studio and flow.py
_graph = None

def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
```

**Graph shape:**
```
START → csa_node → stage2_node (fan-out/gather internally) → da_node → END
                        ↓ asyncio.create_task
                    swa_background (fire-and-forget)
```

**Why single stage2_node instead of parallel LangGraph edges:**
LangGraph parallel branches via `Send` require each branch to be a separate subgraph node,
and merging their results requires a join node with custom reducers. Using `asyncio.gather`
inside a single `stage2_node` achieves the same parallelism with far less boilerplate —
this is the same pattern used in the current flow.py.

---

## Phase 5 — flow.py rewrite

**File:** `orchestrator/flow.py`

Replace asyncio orchestration with `graph.ainvoke()`. Keep the same public API
(`run_amp_workflow(task_input: dict) -> AmpState`) so callers don't change.

```python
from .graph import get_graph
from .schemas import AmpState, TaskIntake

async def run_amp_workflow(task_input: dict) -> AmpState:
    task_intake = TaskIntake(**{k: v for k, v in task_input.items() if v is not None})
    initial_state = {
        "task_intake": task_intake,
        "latency_log": {},
        "stage_errors": {},
    }
    config = {"configurable": {"thread_id": task_intake.task_id or "default"}}
    final_state = await get_graph().ainvoke(initial_state, config=config)
    return AmpState(**{k: v for k, v in final_state.items() if v is not None})
```

The existing `_resolve_stage2`, `_merge_stage2_results`, `_run_single_stage2` functions
in flow.py are replaced by `stage2_node` + `flow_helpers.resolve_stage2_agents`.

---

## Phase 6 — tools.py simplification

**File:** `orchestrator/tools.py`

DELETE the ADK wrappers (`call_csa`, `call_rra`, `call_gpa`, `call_iaa`, `call_da`, `call_swa`
with ToolContext signatures). Keep only:
- `_call_csa_impl(state: AmpState)`
- `_call_rra_impl(state: AmpState)`
- `_call_gpa_impl(state: AmpState)`
- `_call_iaa_impl(state: AmpState)`
- `_call_da_impl(state: AmpState)`
- `_run_swa_background(state: AmpState)`
- All helper functions: `_url`, `_record_latency`, `_coerce_state`

Also remove `from google.adk.tools import ToolContext` import.

---

## Phase 7 — langgraph.json (Studio config)

**File:** `langgraph.json` at project root

```json
{
  "dependencies": ["."],
  "graphs": {
    "amp_orchestrator": "./orchestrator/graph.py:get_graph"
  },
  "env": ".env"
}
```

**To launch Studio:**
```bash
pip install langgraph-cli
langgraph dev
# Opens Studio UI at http://localhost:8123
```

Studio visualizes the graph, lets you run it interactively, inspect state at each node,
replay from any checkpoint — equivalent to `adk web` but purpose-built for graphs.

---

## Phase 8 — agent.py (delete)

`orchestrator/agent.py` is the ADK wrapper. Delete it entirely.

---

## Phase 9b — demo.py (Streamlit client demo UI)

**File:** `demo/app.py`

Streamlit is already in requirements. A client-facing demo UI wraps `run_amp_workflow()`:

```python
import streamlit as st
import asyncio
from orchestrator.flow import run_amp_workflow

st.title("Project AMP — Workflow Demo")
with st.form("task_form"):
    case_id      = st.text_input("Case ID", "CASE-001")
    case_type    = st.selectbox("Case Type", ["vendor_onboarding","claim_review","fraud_investigation"])
    description  = st.text_area("Task Description")
    priority     = st.selectbox("Priority", ["critical","high","medium","low"])
    submitted    = st.form_submit_button("Run Workflow")

if submitted:
    with st.spinner("Running AMP workflow..."):
        result = asyncio.run(run_amp_workflow({
            "task_id": case_id, "case_id": case_id,
            "case_type": case_type, "task_type": case_type,
            "description": description, "priority": priority,
        }))
    st.success("Workflow complete")
    col1, col2 = st.columns(2)
    col1.metric("Escalation Required", str(result.requires_escalation))
    col2.metric("Operating Context", result.operating_context)
    if result.da_output:
        st.subheader("Assignment")
        st.json(result.da_output.model_dump(mode="json", exclude_none=True))
    if result.risk_output:
        st.subheader("Risk Flags")
        st.write(result.risk_output.risk_flags)
    if result.governance_output:
        st.subheader("Governance Decision")
        st.write(f"{result.governance_output.decision} — {result.governance_output.reason}")
    if result.stage_errors:
        st.warning(f"Stage errors: {result.stage_errors}")
```

**Run:** `streamlit run demo/app.py`

**Two demo modes:**
- **Client demo:** `streamlit run demo/app.py` — polished form → results view
- **Technical demo:** `langgraph dev` → Studio graph visualization + node-by-node state inspection

---

## Phase 10 — requirements.txt updates

**`orchestrator/requirements.txt`** — replace:
```
# REMOVE:
google-adk>=0.1.0

# ADD:
langgraph>=0.2.0
langgraph-cli>=0.1.0
```

**`requirements.txt` (root)** — remove:
```
google-adk>=0.1.0
google-generativeai>=0.8
```

---

## Execution Order (per session)

### Session 1 — Core graph (Opus 4.7, low thinking)
1. Create `orchestrator/state.py`
2. Create `orchestrator/flow_helpers.py` (extract routing from flow.py)
3. Create `orchestrator/nodes.py`
4. Create `orchestrator/graph.py`
5. Rewrite `orchestrator/flow.py`
6. Simplify `orchestrator/tools.py` (delete ADK wrappers)
7. Create `langgraph.json`
8. **Smoke test:** `python -c "from orchestrator.graph import get_graph; print(get_graph())"`
9. **Programmatic test:** `python -c "from orchestrator.flow import run_amp_workflow; import asyncio; print(asyncio.run(run_amp_workflow({...})))"`

### Session 2 — Cleanup + UI (Sonnet 4.6, no thinking)
1. Delete `orchestrator/agent.py`
2. Delete `orchestrator/.adk/` directory
3. Update `orchestrator/requirements.txt`
4. Update root `requirements.txt`
5. **Install:** `pip install langgraph-cli`
6. Create `demo/app.py` (Streamlit client demo)
7. **Studio test:** `langgraph dev` → open http://localhost:8123
8. **Demo test:** `streamlit run demo/app.py`
9. Run a full workflow through both UIs, verify state at each node
10. Update CLAUDE.md run instructions

---

## Verification Checklist

```bash
# 1. Import smoke test
python -c "from orchestrator.graph import get_graph; g = get_graph(); print('nodes:', list(g.nodes))"

# 2. Programmatic workflow (agents must be running)
python -c "
from orchestrator.flow import run_amp_workflow
import asyncio
result = asyncio.run(run_amp_workflow({
    'task_id': 'TEST-001',
    'case_id': 'CASE-001',
    'case_type': 'vendor_onboarding',
    'task_type': 'vendor_onboarding',
    'title': 'Test vendor review',
    'description': 'Review vendor compliance and risk',
    'requester': 'test_user',
    'priority': 'medium',
}))
print('requires_escalation:', result.requires_escalation)
print('stage_errors:', result.stage_errors)
"

# 3. LangGraph Studio
langgraph dev
# Navigate to http://localhost:8123
# Select amp_orchestrator graph
# Paste task_input JSON, run, inspect state at each node

# 4. Existing tests still pass (no agent code changed)
pytest IAA/test_iaa.py -v
pytest RRA/tests/ -v
```

---

## Key Reuse Map

| Old location | New location | Change |
|---|---|---|
| `flow.py::_resolve_stage2` | `flow_helpers.py::resolve_stage2_agents` | Extract, return node fns not _impl fns |
| `flow.py::_merge_stage2_results` | `nodes.py::stage2_node` (inline) | Folded into gather loop |
| `tools.py::_call_*_impl` | `tools.py::_call_*_impl` | No change |
| `schemas.py::AmpState` | `state.py::AmpGraphState` + `schemas.py::AmpState` | AmpState kept, TypedDict added |
| `shims.py::compute_operating_context` | `nodes.py::stage2_node` | Called same way |
| `shims.py::compute_requires_escalation` | `nodes.py::da_node` (via _call_da_impl) | Already in _impl |
| `IAA/orchestrator/orchestrator.py` | `orchestrator/graph.py` | Pattern reference — StateGraph, MemorySaver, get_graph singleton |

---

## Session Resume Instructions

If session resets mid-implementation, read this file first, then:
1. Check which files exist: `ls orchestrator/`
2. If `state.py` exists → Session 1 is in progress, continue from nodes.py
3. If `graph.py` exists → Core done, run smoke test, then Session 2
4. If `langgraph.json` exists → Near complete, just cleanup + Studio test

The `_impl` functions in `tools.py` are the stable foundation — they don't change.
If uncertain, start by running the import smoke test to see what's broken.