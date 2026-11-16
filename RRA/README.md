# Risk Radar Agent (RRA)

> **Stage 2 of Project AMP** — Evaluates operational and temporal risk in enterprise workflows using a deterministic, LLM-optional rule engine. Returns a risk severity rating, proceed decision, and human-readable reasoning summary before any task execution proceeds.

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![Dataclasses](https://img.shields.io/badge/stdlib_dataclasses-no_ORM-555555?style=flat)
![Google AI](https://img.shields.io/badge/Gemini-optional_summarizer-4285F4?style=flat&logo=google&logoColor=white)

> RRA uses stdlib dataclasses internally. No SQLAlchemy, no Pydantic. The HTTP boundary isolates it from the orchestrator's Pydantic v2 models — do not "fix" this.

---

## Features

- **5 risk rule categories** — deadline, missing input, dependency, historical delay, compliance — each in its own module
- **Deterministic output** — no LLM required; `GOOGLE_API_KEY` only needed for the optional reasoning summarizer
- **Severity consolidation** — pure function maps rule results → `low / medium / high / critical` + `proceed / caution / hold`
- **Operating context detection** — downgrades to `partial` when upstream CSA context is incomplete
- **Escalation signal** — sets `escalate_to_human=True` when severity ≥ HIGH or policy flag is raised
- **FastAPI HTTP server** — exposes `/health` + `/predict`; consumed by the LangGraph orchestrator on port 8002

---

## Architecture

```
POST /predict (CaseInput dict)
     │
     ├── packet_parser.py     ← parses CSA output packet into CaseInput
     │
     ├── rules/               ← one module per risk category
     │     ├── deadline.py
     │     ├── missing_input.py
     │     ├── dependency.py
     │     ├── historical_delay.py
     │     └── compliance.py
     │
     ├── severity.py          ← consolidate() — pure function
     │
     ├── summarizer.py        ← optional LLM reasoning summary (Gemini)
     │
     └── RiskRadarOutput (dataclass)
           │
           → .to_dict() → JSON response
           → orchestrator maps via shims.rra_to_amp()
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- `GOOGLE_API_KEY` in `.env` — only required if the reasoning summarizer is enabled

### Installation

```bash
# From project root
pip install -r requirements.txt
cp .env.example .env   # set GOOGLE_API_KEY
```

### Running

```bash
# From project root
uvicorn RRA.api:app --port 8002

# Or via start_agents.sh (recommended)
bash start_agents.sh
```

### Health check

```bash
curl http://localhost:8002/health
# {"status": "ok"}
```

---

## Usage

### Predict risk for a case

```bash
curl -s -X POST http://localhost:8002/predict \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "TASK-001",
    "workflow_type": "vendor_onboarding",
    "workflow_state": "PARTIAL",
    "required_inputs": ["emails", "documents", "calendar_events", "case_history"],
    "received_inputs": ["emails"],
    "mandatory_inputs": ["documents", "calendar_events"],
    "policy_flag": true,
    "blocker_flag": false,
    "prior_delay_count": 2,
    "prior_escalation_count": 0
  }' | python -m json.tool
```

**Response shape:**

```json
{
  "task_id": "TASK-001",
  "workflow_state": "PARTIAL",
  "priority": "medium",
  "risk_items": [
    {
      "risk_type": "missing_input",
      "severity": "high",
      "description": "Missing mandatory inputs: documents, calendar_events",
      "rule_name": "MissingInputRule"
    }
  ],
  "overall_risk_level": "high",
  "can_proceed": "caution",
  "escalate_to_human": true,
  "escalation_target": "risk_committee",
  "reasoning_summary": "...",
  "operating_context": "partial",
  "model_used": null,
  "timestamp": "2026-04-29T12:00:00+00:00"
}
```

### CLI runner (standalone)

```bash
python -m RRA.main path/to/case.json
```

### In-process use

```python
from RRA.agent import RiskRadarAgent
from RRA.schema import CaseInput

agent = RiskRadarAgent()
case  = CaseInput.from_dict(payload_dict)
output = agent.evaluate(case)
print(output.overall_risk_level)   # "high"
print(output.escalate_to_human)    # True
print([i.risk_type.value for i in output.risk_items])
```

---

## Risk Rules

| Rule | Triggers on | Default severity |
|------|------------|-----------------|
| `MissingInputRule` | Mandatory inputs absent | HIGH |
| `DeadlineRule` | Due date within threshold | MEDIUM → HIGH |
| `DependencyRule` | Blocked dependencies present | MEDIUM |
| `HistoricalDelayRule` | Prior delays > threshold | MEDIUM |
| `ComplianceRule` | Policy flag raised by CSA | HIGH |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `POST` | `/predict` | Evaluate risk; accepts `csa_to_rra()` payload |

---

## Running Tests

```bash
pytest RRA/tests/ -v
```

---

## Project Structure

```
RRA/
├── api.py            # FastAPI HTTP server (GET /health, POST /predict)
├── agent.py          # RiskRadarAgent — orchestrates rule execution
├── schema.py         # Stdlib dataclasses: CaseInput, RiskItem, RiskRadarOutput
├── severity.py       # consolidate() — maps rule results to overall severity
├── summarizer.py     # Optional LLM reasoning summary
├── packet_parser.py  # Parses CSA output packet → CaseInput
├── config.py         # Thresholds, SLA rules, escalation config
├── rules/
│   ├── base.py
│   ├── deadline.py
│   ├── missing_input.py
│   ├── dependency.py
│   ├── historical_delay.py
│   └── compliance.py
└── tests/
    ├── test_agent.py
    ├── fixture_builders.py
    └── conftest.py
```
