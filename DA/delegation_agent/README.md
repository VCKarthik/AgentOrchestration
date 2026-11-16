# Delegation Agent

### Project AMP — Intelligent Task Routing System

> **Status:** Final Prototype — Client Demo Ready
> **Python:** 3.11+
> **Architecture:** Deterministic Decision Engine + LLM-Enhanced Explainability

---

##  Overview

The **Delegation Agent** is a core component of a multi-agent enterprise orchestration system.

It is responsible for:

* Determining **how a task should be handled**
* Selecting the appropriate **execution channel**
* Assigning the correct **owner (human, automation, supervisor, or agent)**
* Providing **transparent reasoning**
* Generating **structured outputs (YAML)** for downstream systems

---

##  Problem Statement

In enterprise environments, tasks vary in:

* complexity
* urgency
* domain requirements
* risk levels
* resource availability

A simple “assign-to-person” system is insufficient.

The Delegation Agent solves this by introducing:

 **Channel-first intelligent routing + explainable decision-making**

---

##  Core Capabilities

###  1. Channel-Based Routing

Tasks are routed into one of four execution paths:

| Channel               | Purpose                                                |
| --------------------- | ------------------------------------------------------ |
| **human_owner**       | Assign to human based on skill, domain, and capacity   |
| **automation**        | Route to system workflows for repetitive tasks         |
| **supervisor_review** | Route to approval queues for high-risk/value decisions |
| **specialized_agent** | Route to domain-specific agents                        |

---

###  2. Multi-Stage Decision Pipeline

The system uses a structured pipeline:

```
1. Task Validation  
2. Candidate Retrieval  
3. Filtering (availability, domain)  
4. Scoring  
5. Rule Evaluation  
6. Escalation Detection  
7. Channel Selection  
8. Owner Assignment  
9. Explanation Generation  
10. Audit + Notification + Output  
```

---

###  3. Deterministic Scoring Engine

Candidates are evaluated using:

* Skill match
* Domain alignment
* Capacity (bandwidth)
* Priority handling

#### Scoring Formula:

```
composite_score =
    (skill_match × 0.40)
  + (domain_match × 0.20)
  + (capacity_fit × 0.25)
  + (priority_fit × 0.15)
```

---

###  4. Business Rules & Constraints

Hard rules ensure correctness:

* Required skill enforcement
* Availability checks
* Domain restrictions
* Capacity limits

---

###  5. Escalation Logic

Automatically detects scenarios requiring escalation:

* High monetary value
* Compliance or regulatory risk
* SLA violations
* No eligible assignees
* Low confidence decisions

---

###  6. Capacity & Workload Awareness

* Tracks assignee utilization via `bandwidth_repository`
* Prevents overload
* Improves assignment fairness and realism

---

###  7. Task Effort Estimation

* Estimates effort dynamically
* Helps in better capacity-aware routing
* Supports realistic decision-making

---

###  8. LLM-Enhanced Explainability

* Uses Gemini (when available)
* Generates human-readable explanations
* Provides reasoning for:

  * routing decision
  * confidence score

👉 Designed as **advisory only**, never overrides logic

---

###  9. Fail-Safe Architecture

* Works even if LLM fails
* Uses deterministic fallback
* Ensures system reliability

---

###  10. Structured YAML Output

Each decision is exported as YAML:

```yaml
assignment_id: ASN-221039CA48
task_id: TSK-2026-001
status: assigned

selected_channel: human_owner
selected_owner:
  name: Suyash Wagh
  role: Senior Claims Adjuster

confidence_score: 92.08

reasons:
  - Requires human judgment due to task complexity
  - Assigned to best matching candidate
```

 Enables:

* Orchestrator integration
* Debugging
* Auditing

---

###  11. Audit Logging

* Every decision is recorded
* Tracks reasoning and confidence
* Supports traceability

---

###  12. Channel-Aware Notifications

| Channel    | Action         |
| ---------- | -------------- |
| Human      | Email          |
| Supervisor | Approval queue |
| Automation | System trigger |
| Agent      | Agent handoff  |

---

##  Architecture

```
Incoming Task
     ↓
Validation
     ↓
Candidate Retrieval
     ↓
Filtering
     ↓
Scoring Engine
     ↓
Rules Engine
     ↓
Escalation Logic
     ↓
Channel Selection
     ↓
Owner Assignment
     ↓
LLM Explanation (optional)
     ↓
Audit + Notification + YAML Output
```

---

##  Project Structure

```
delegation_agent/
│
├── engine/
│   ├── scoring.py
│   ├── rules.py
│   ├── escalation.py
│   └── stages.py
│
├── models/
│   ├── task.py
│   ├── assignee.py
│   └── outputs.py
│
├── repositories/
│   ├── assignee_repository.py
│   ├── audit_repository.py
│   └── bandwidth_repository.py
│
├── services/
│   ├── audit.py
│   ├── notifier.py
│   ├── llm_service.py
│   ├── llm_router.py
│   ├── exporter.py
│   └── task_estimator.py
│
├── tests/
│   └── test_delegation.py
│
├── agent.py
├── main.py
└── requirements.txt
```

---

##  Running the Demo

```bash
python -m delegation_agent.main
```

### Demo Includes:

* 5 real-world task scenarios
* All routing channels
* LLM explanations
* YAML outputs
* Audit summary

---

##  Running Tests

```bash
pytest delegation_agent/tests/ -v
```

---

##  Orchestrator Integration

```python
from delegation_agent.agent import DelegationAgent

agent = DelegationAgent()

decision = agent.evaluate_task(task_payload)

print(decision.selected_channel)
print(decision.selected_owner)
print(decision.confidence_score)
```

---

##  Design Principles

### 1. Deterministic First

Core decisions are rule-based and predictable

### 2. LLM as Enhancement

Improves reasoning but does not control decisions

### 3. Channel-Based Thinking

Routing is not just *who*, but *how*

### 4. Fail-Safe Design

System works even without LLM

### 5. Integration Ready

Structured outputs enable orchestration

---

##  Future Enhancements

* Queue-based task ingestion
* Database integration (PostgreSQL / Redis)
* FastAPI endpoint
* Advanced LLM-based task understanding
* ML-based scoring optimization

---

##  Summary

The Delegation Agent delivers:

* Intelligent task routing
* Multi-channel execution
* Explainable decisions
* Production-ready outputs

## A hybrid system combining **deterministic reliability** with **LLM intelligence**
