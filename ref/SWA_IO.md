# Shadow Work Agent
## Input:
{
"case": {
"case_id": "case_vendor_0042",
"case_type": "vendor_onboarding",
"status": "in_progress",
"created_at": "2026-04-27T09:00:00Z",
"closed_at": null,
"domain_metadata": {
"client_name": "Acme Corp",
"priority": "high"
}
},
"events": [
{
"event_id": "evt_001",
"case_id": "case_vendor_0042",
"timestamp": "2026-04-27T09:05:00Z",
"actor_id": "context_stitching_agent",
"actor_type": "agent",
"action_type": "context_gathered",
"target_entity": "sys_procurement_queue",
"target_entity_type": "internal_system",
"parent_task_id": "task_v0042",
"context_payload": { "records_found": 3 },
"outcome": "success"
},
{
"event_id": "evt_002",
"case_id": "case_vendor_0042",
"timestamp": "2026-04-27T09:30:00Z",
"actor_id": "risk_radar_agent",
"actor_type": "agent",
"action_type": "risk_flagged",
"target_entity": "sys_procurement_queue",
"target_entity_type": "internal_system",
"parent_task_id": "task_v0042",
"context_payload": { "risk": "missing_compliance_cert" },
"outcome": "success"
},
{
"event_id": "evt_003",
"case_id": "case_vendor_0042",
"timestamp": "2026-04-27T09:45:00Z",
"actor_id": "risk_radar_agent",
"actor_type": "agent",
"action_type": "sent_followup",
"target_entity": "vendor_acme",
"target_entity_type": "external_contact",
"parent_task_id": "task_v0042",
"context_payload": { "channel": "email", "doc_type": "compliance_cert" },
"outcome": "pending"
},
{
"event_id": "evt_004",
"case_id": "case_vendor_0042",
"timestamp": "2026-04-27T10:00:00Z",
"actor_id": "governance_policy_agent",
"actor_type": "agent",
"action_type": "policy_check",
"target_entity": "sys_compliance_db",
"target_entity_type": "internal_system",
"parent_task_id": "task_v0042",
"context_payload": { "policy": "vendor_compliance_v2" },
"outcome": "success"
},
{
"event_id": "evt_005",
"case_id": "case_vendor_0042",
"timestamp": "2026-04-27T10:15:00Z",
"actor_id": "delegation_agent",
"actor_type": "agent",
"action_type": "task_assigned",
"target_entity": "user_proc_01",
"target_entity_type": "internal_user",
"parent_task_id": "task_v0042",
"context_payload": { "assignment_kind": "review" },
"outcome": "success"
},
{
"event_id": "evt_006",
"case_id": "case_vendor_0042",
"timestamp": "2026-04-27T10:30:00Z",
"actor_id": "intent_anticipation_agent",
"actor_type": "agent",
"action_type": "intent_predicted",
"target_entity": "task_v0042",
"target_entity_type": "task",
"parent_task_id": "task_v0042",
"context_payload": { "predicted_next": "document_collection" },
"outcome": "success"
},
{
"event_id": "evt_007",
"case_id": "case_vendor_0042",
"timestamp": "2026-04-29T09:00:00Z",
"actor_id": "user_proc_01",
"actor_type": "human",
"action_type": "sent_followup",
"target_entity": "vendor_acme",
"target_entity_type": "external_contact",
"parent_task_id": "task_v0042",
"context_payload": { "channel": "email", "doc_type": "compliance_cert" },
"outcome": "pending"
},
{
"event_id": "evt_008",
"case_id": "case_vendor_0042",
"timestamp": "2026-05-01T09:00:00Z",
"actor_id": "user_proc_01",
"actor_type": "human",
"action_type": "sent_followup",
"target_entity": "vendor_acme",
"target_entity_type": "external_contact",
"parent_task_id": "task_v0042",
"context_payload": { "channel": "email", "doc_type": "compliance_cert" },
"outcome": "pending"
},
{
"event_id": "evt_009",
"case_id": "case_vendor_0042",
"timestamp": "2026-05-01T11:00:00Z",
"actor_id": "user_proc_01",
"actor_type": "human",
"action_type": "requested_document",
"target_entity": "vendor_acme",
"target_entity_type": "external_contact",
"parent_task_id": "task_v0042",
"context_payload": { "doc_type": "compliance_cert", "channel": "email" },
"outcome": "pending"
},
{
"event_id": "evt_010",
"case_id": "case_vendor_0042",
"timestamp": "2026-05-02T09:00:00Z",
"actor_id": "user_proc_01",
"actor_type": "human",
"action_type": "status_check",
"target_entity": "sys_procurement_queue",
"target_entity_type": "internal_system",
"parent_task_id": "task_v0042",
"context_payload": { "system": "procurement_queue" },
"outcome": "success"
},
{
"event_id": "evt_011",
"case_id": "case_vendor_0042",
"timestamp": "2026-05-03T14:00:00Z",
"actor_id": "user_proc_01",
"actor_type": "human",
"action_type": "approved",
"target_entity": "task_v0042",
"target_entity_type": "task",
"parent_task_id": "task_v0042",
"context_payload": { "approval_level": "tier_1" },
"outcome": "success"
}
],
"thresholds": {
"analysis_window_days": 90,
"min_repetition_threshold": 3,
"min_regularity_score": 0.7,
"confidence_threshold": 0.75,
"dbscan_eps": 1.2,
"dbscan_min_samples": 5,
"scheduler_case_threshold": 20
}
}
### Output:
{
"agent": "shadow_work",
"run_id": "sw_20260427_090000_ab12",
"timestamp": "2026-04-27T10:30:00Z",
"scope": "global",
"trigger_type": "scheduled_sweep",
"window_analyzed": {
"start": "2026-03-28T10:30:00Z",
"end": "2026-04-27T10:30:00Z",
"events_processed": 2303
},
"case_portfolios": [
{
"case_id": "case_vendor_0042",
"case_type": "vendor_onboarding",
"status": "in_progress",
"total_events": 11,
"distinct_actors": 4,
"distinct_actions": 5,
"case_duration_hours": 143.82,
"timeline": [
{
"timestamp": "2026-04-27T09:05:00Z",
"actor_id": "context_stitching_agent",
"actor_type": "agent",
"action_type": "context_gathered",
"target_entity": "sys_procurement_queue",
"outcome": "success"
}
],
"action_counts": {
"sent_followup": 3,
"context_gathered": 1,
"policy_check": 2
},
"actor_counts": {
"risk_radar_agent": 2,
"context_stitching_agent": 1,
"user_proc_01": 3
},
"target_counts": {
"vendor_acme": 3,
"sys_procurement_queue": 2
}
}
],
"findings": [
{
"finding_id": "sw_20260427_090000_ab12_f_000",
"detector_source":"heuristic:repetition, heuristic:temporal_regularity",
"pattern_type": "scheduled_recurring_action",
"pattern_signature":
"action:sent_followup → target_type:external_contact → interval:~48h",
"occurrences": 9,
"actors_involved":["user_proc_01", "user_clm_01", "user_rec_01"],
"cases_involved": ["case_vendor_0042", "case_ins_001", "case_hire_001"],
"temporal_signature": {
"mean_interval_hours": 48.0,
"stddev_interval_hours": 0.42,
"regularity_score": 1.0
},
"description":
"sent followup action occurred 9 times against external contact entities",
"domain_contextualized_description":
"Three case managers are chasing external contacts every 48 hours — strong candidate for automated
follow-up scheduling.",
"automation_recommendation": {
"type": "scheduled_automation_rule",
"trigger": "after 48h with no resolution",
"action": "Automate sent followup after 48.0h interval",
"estimated_time_saved_per_week_hours": null
},
"confidence": 0.798,
"risk_level": "medium",
"decision": "recommend",
"requires_human_approval": false,
"evidence_event_ids": [
"evt_001", "evt_002", "evt_003"
]
}
],
"escalations": [
{
"escalation_id": "sw_e_a3b2c1d4",
"reason": "pattern observed but below confidence threshold; continue monitoring",
"pattern_signature": "action:task_assigned → target_type:internal_user",
"occurrences": 16,
"recommended_human_role": "operations_coordinator",
"summary_for_human": "task_assigned action occurred 16 times against internal user entities, mean
interval 45.0h. Human review recommended.",
"evidence_event_ids": [
"evt_010", "evt_011", "evt_012"
]
}
],
"metrics": {
"patterns_detected": 13,
"recommendations_made": 2,
"escalations_raised": 4,
"events_processed": 2303,
"processing_time_ms": 3200.0,
"detectors_used": [
"heuristic:repetition",
"heuristic:temporal_regularity",
"heuristic:cross_case",
"ml:dbscan_clustering"
]
},
"cluster_evolution": {
"previous_run_id": "sw_20260420_090000_cd34",
"previous_total_cases": 200,
"current_clusters_count": 14,
"delta_summary": {
"new_clusters": 1,
"strengthened_clusters": 6,
"stable_clusters": 7,
"dissolved_clusters": 0
},
"new_clusters": [
{
"fingerprint": "policy_check::internal_system::agent::afternoon",
"size": 22,
"n_cases": 22,
"verdict": "NEW pattern discovered — wasn't visible in previous run"
}
],
"strengthened_clusters": [
{
"fingerprint": "sent_followup::external_contact::human::morning",
"previous_size": 433,
"current_size": 478,
"size_delta": 45,
"cases_delta": 20,
"verdict": "Pattern STRENGTHENED — grew from 433 to 478 events"
}
]
}
}