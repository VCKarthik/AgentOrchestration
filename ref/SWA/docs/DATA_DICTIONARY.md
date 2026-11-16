# Data Dictionary — Shadow Work Agent v2

**Purpose:** This document defines every field the Shadow Work Agent expects to receive from other agents in the AITS system. Per Ankit's request, this is the contract between our agent and the orchestrator/other agents. Their output is our input.

---

## Table: `cases`

Registry of every case in the system. Other agents create cases; Shadow Work observes their lifecycle.

| Field | Type | Required | Valid Values | Source | Description |
|---|---|---|---|---|---|
| `case_id` | string | Yes | Unique identifier | AITS orchestrator | Primary key. Every event must reference a registered case. |
| `case_type` | string | Yes | Free text (e.g., `vendor_onboarding`, `auto_claim`) | Triaging agent | Categorical label for the kind of work |
| `status` | string | Yes | `open`, `in_progress`, `closed` | AITS orchestrator | Current lifecycle state |
| `created_at` | timestamp | Yes | ISO 8601 UTC | AITS orchestrator | When the case was opened |
| `closed_at` | timestamp | No | ISO 8601 UTC | AITS orchestrator | When the case was closed (null if still open) |
| `domain_metadata` | JSON | No | Any JSON object | Triaging agent | Domain-specific case info (opaque to Shadow Work) |

---

## Table: `activity_log`

Every action by every agent or human lands here. Shadow Work is "CC'd" on every event.

| Field | Type | Required | Valid Values | Source | Description |
|---|---|---|---|---|---|
| `event_id` | string | Yes | Unique identifier | Writing agent | Primary key |
| `case_id` | string | Yes | Must reference existing case | Writing agent | Links event to its case |
| `timestamp` | timestamp | Yes | ISO 8601 UTC | Writing agent | When the action occurred |
| `actor_id` | string | Yes | Agent ID or user ID | Writing agent | Who performed the action |
| `actor_type` | string | Yes | `agent`, `human` | Writing agent | Whether the actor is a system agent or a person |
| `action_type` | string | Yes | Closed vocabulary (see below) | Writing agent | What was done |
| `target_entity` | string | Yes | Entity identifier | Writing agent | The thing being acted upon |
| `target_entity_type` | string | Yes | Closed vocabulary (see below) | Writing agent | The kind of thing being acted upon |
| `parent_task_id` | string | No | Task identifier | Writing agent | Groups related events within a case |
| `context_payload` | JSON | No | Any JSON object | Writing agent | Domain-specific details (opaque to Shadow Work detection) |
| `outcome` | string | Yes | `success`, `pending`, `failed` | Writing agent | Result of the action |

---

## Closed Vocabulary: `action_type`

The action_type field MUST be one of these values. Who defines this set? The AITS platform governance team (or whoever configures the deployment) agrees on the vocabulary before any agent writes. Shadow Work consumes this vocabulary — it does not define it.

### Automatable actions

Safe to auto-recommend for automation:

| Value | Meaning |
|---|---|
| `sent_followup` | Follow-up message sent after no response |
| `sent_reminder` | Reminder message (first touch or proactive) |
| `status_check` | Reading a status from a system or queue |
| `requested_document` | Formal request for information |
| `scheduled_meeting` | Calendar invite sent |

### Approval-type actions

Always escalate, never auto-recommend:

| Value | Meaning |
|---|---|
| `approved` | Formal approval granted |
| `rejected` | Formal rejection |
| `escalated_to_human` | Pushed up the chain |
| `manual_override` | Policy bypass |
| `policy_exception_granted` | Deviation from standard process |

### Informational actions

Log but don't flag as shadow work:

| Value | Meaning |
|---|---|
| `received_message` | Passive receipt |
| `logged_note` | Annotation |
| `viewed_document` | Read-only access |
| `case_opened` | Lifecycle event |
| `case_closed` | Lifecycle event |

---

## Closed Vocabulary: `target_entity_type`

| Value | Meaning | Examples |
|---|---|---|
| `external_contact` | Someone outside the organization | Vendor, client, candidate, claimant |
| `internal_system` | A system or automated service | Approvals queue, database, dashboard |
| `internal_user` | An organizational employee | Employee, manager, agent |
| `task` | A unit of work | Task record, ticket, story |
| `document` | A file or record | Contract, form, report |

---

## Outputs Produced by Shadow Work

These are what Shadow Work produces — the contract for whoever consumes our output (the AITS orchestrator, a dashboard, etc.).

### `case_portfolios`

Per-case historical summaries. One row per case. Produced by Module 1 (logging tool).

See `CasePortfolio` in `agent/models.py` for the full schema.

### `analysis_runs`

Audit trail. One row per analysis run. Contains the full `AgentOutput` JSON as a field.

See `AgentOutput` in `agent/models.py` for the full schema.

### `ingestion_log`

Record of every ingestion attempt, including rejections. Proves the logging tool captured everything.

---

## Field Source Summary (who writes what)

| Field | Source |
|---|---|
| Case metadata | AITS orchestrator or triaging agent |
| Event `actor_id` (agent) | The agent itself writes this |
| Event `actor_id` (human) | AITS orchestrator derives from message/task origin |
| `action_type` | Agent classifies its own action against the closed vocabulary |
| `target_entity_type` | Agent classifies based on the entity being acted upon |
| `context_payload` | Free-form — agent fills with domain details |
| `outcome` | Agent reports after action completes |

---

## Data Quality Rules

1. **Every event must have a registered case_id.** If not, the logging tool rejects it.
2. **Every action_type must be in the closed vocabulary.** Unknown action types are rejected.
3. **Every target_entity_type must be in the closed vocabulary.** Unknown target types are rejected.
4. **Timestamps must be UTC.** Mixed timezones break temporal analysis.
5. **Rejected events are still logged** in `ingestion_log` with the rejection reason — we track the full attempt history.
