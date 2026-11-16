# Orchestrator — Project AMP

The LangGraph orchestrator that wires the 6-agent pipeline together.  
Entry point: `run_amp_workflow()` in `flow.py`.

---

## Execution flow

```
run_amp_workflow(task_intake_dict)
        │
        ▼
  [csa_node]          Stage 1 — CSA retrieves context; SWA fires async in background
        │
        ▼
  [stage2_node]       Stage 2 — RRA / GPA / IAA run in parallel via asyncio.gather
        │               Routing: flow_helpers.py determines which subset fires
        ▼
  [da_node]           Stage 3 — DA receives merged Stage 2 output, assigns task
        │
        ▼
  returns AmpState    Meta fields (operating_context, requires_escalation) computed here
```

`stage2` is a single LangGraph node that fans out internally. LangGraph sees one node; the parallelism is `asyncio.gather` inside `nodes.py`.

---

## Running

```bash
# LangGraph Studio — graph UI, node-by-node state inspection, checkpoint replay
langgraph dev
# Opens http://localhost:8123  (requires: pip install langgraph-cli)
# Config: langgraph.json → "amp_orchestrator" → orchestrator/graph.py:get_graph

# Programmatic
from orchestrator.flow import run_amp_workflow
import asyncio
result = asyncio.run(run_amp_workflow({...}))  # pass TaskIntake fields as dict

# Smoke test
python -c "from orchestrator.graph import get_graph; print(list(get_graph().nodes))"
# Expected: ['__start__', 'csa', 'stage2', 'da']
```

---

## File responsibilities

| File | Owns |
|---|---|
| `flow.py` | `run_amp_workflow()` — top-level execution, AmpState assembly |
| `nodes.py` | LangGraph node functions: `csa_node`, `stage2_node`, `da_node` |
| `tools.py` | HTTP calls to each agent (`call_csa`, `call_rra`, `call_gpa`, `call_iaa`, `call_da`, `_run_swa_background`). All `@traceable` for LangSmith. |
| `shims.py` | **All** field mapping between agents — single source of truth. No mapping logic anywhere else. |
| `contracts.py` | Slim per-agent input models (`CSAInput`, `RRAInput`, `GPAInput`, `IAAInput`, `DAInput`, `SWAInput`) |
| `schemas.py` | `AmpState` — canonical Pydantic model for all inter-agent data |
| `flow_helpers.py` | Stage 2 routing: keyword sets that determine which agents fire |
| `graph.py` | `get_graph()` — LangGraph `StateGraph` builder |

**Responsibilities do not bleed across files.** `flow.py` owns execution order. `tools.py` owns HTTP. `shims.py` owns field mapping.

---

## AmpState

`schemas.py` defines `AmpState` — all inter-agent data flows through it.  
`data/AmpState_spec.json` is the annotated canonical reference (type, stage, governing decision for every field).

Fields set by each stage:
- `task_intake` — set by caller before `run_amp_workflow()`
- `csa_output` — set by `csa_node`
- `risk_output`, `governance_output`, `iaa_output`, `swa_output` — set by `stage2_node`
- `da_output` — set by `da_node`
- `meta.operating_context`, `meta.requires_escalation` — computed by `stage2_node` (D5, D7)

---

## Shims

`shims.py` contains two categories of functions:

**Input builders** — construct the slim payload sent to each agent:
- `build_csa_input`, `build_rra_input`, `build_gpa_input`, `build_iaa_input`, `build_da_input`, `build_swa_input`

**Output mappers** — map raw HTTP response dicts to AmpState field models:
- `rra_to_amp`, `gpa_to_amp`, `iaa_to_amp`, `da_to_amp`

**Orchestrator decision shims:**
- `extract_risk_flags` — D3: derives `risk_flags` from `rra_output.risk_items[].risk_type`
- `compute_operating_context` — D5: "partial" if either RRA or IAA reported partial
- `compute_requires_escalation` — D7: True if any of 4 escalation signals set
- `build_da_task` — D4: merges task_intake + IAA TaskItem + GPA output for DA

All shims are pure functions. No side effects, no business logic, no HTTP calls.

---

## Key architectural decisions

| Decision | Summary |
|---|---|
| D1 | `context_summary` removed from IAA `ProcessState` — CSA never generated it |
| D3 | `risk_flags` derived by shim from `rra_output.risk_items[].risk_type.value` |
| D4 | `build_da_task()` shim merges task_intake + IAA TaskItem + GPA output for DA |
| D5 | `meta.operating_context` = "partial" if RRA **or** IAA reported partial |
| D6 | `swa_output` redesigned to match actual `AgentOutput` fields |
| D7 | `requires_escalation` = any of rra.escalate_to_human \| gpa.requires_approval \| iaa.escalate_to_human \| da.escalation_required |

---

## LangSmith tracing

All `call_*` functions in `tools.py` are `@traceable`. When `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` are set, every agent call appears in the trace tree at smith.langchain.com with per-agent latency.

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your-key>
export LANGCHAIN_PROJECT=amp-orchestrator
```

---

## Partial failure tolerance

If one Stage 2 agent fails (HTTP error, timeout), `asyncio.gather` continues. DA receives `None` for the failed agent's output field and sets `requires_escalation=True` when inputs are insufficient. The failure is recorded in `meta.stage_errors`.

**SWA failures are always suppressed** — SWA never blocks the primary workflow.
