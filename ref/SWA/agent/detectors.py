"""
Heuristic detectors. Three detectors, all deterministic, all case-aware now.

Each detector returns 'raw findings' that are scored and enriched downstream.
"""
from typing import Any

import pandas as pd

from agent.normalizer import compute_intervals
from config.settings import settings


def detect_repetition(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Same actor repeatedly doing same action on same target."""
    if df.empty:
        return []

    intervals = compute_intervals(df, "actor_target_signature")
    if intervals.empty:
        return []

    threshold = settings.MIN_REPETITION_THRESHOLD
    repetitions = intervals[intervals["count"] >= threshold]

    findings = []
    for _, row in repetitions.iterrows():
        actor_id, action_type, target_entity = row["group_key"].split("::", 2)
        subset = df[df["actor_target_signature"] == row["group_key"]]
        if subset.empty:
            continue

        findings.append({
            "detector_source": "heuristic:repetition",
            "pattern_type": "repeated_action_same_target",
            "action_type": action_type,
            "target_entity": target_entity,
            "target_entity_type": subset.iloc[0]["target_entity_type"],
            "occurrences": int(row["count"]),
            "actors_involved": [actor_id],
            "cases_involved": list(subset["case_id"].unique()),
            "mean_interval_hours": row["mean_interval_hours"],
            "stddev_interval_hours": row["stddev_interval_hours"],
            "event_ids": row["event_ids"],
            "sample_context_payloads": [
                subset.iloc[i]["context_payload"] for i in range(min(3, len(subset)))
            ],
        })

    return findings


def detect_temporal_regularity(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Actions happening on a clockwork schedule."""
    if df.empty:
        return []

    intervals = compute_intervals(df, "actor_target_signature")
    if intervals.empty:
        return []

    findings = []
    for _, row in intervals.iterrows():
        if row["count"] < settings.MIN_REPETITION_THRESHOLD:
            continue
        mean = row["mean_interval_hours"]
        stddev = row["stddev_interval_hours"]
        if mean == 0:
            continue

        regularity_score = max(0.0, min(1.0, 1.0 - (stddev / mean)))
        if regularity_score < settings.MIN_REGULARITY_SCORE:
            continue

        actor_id, action_type, target_entity = row["group_key"].split("::", 2)
        subset = df[df["actor_target_signature"] == row["group_key"]]

        findings.append({
            "detector_source": "heuristic:temporal_regularity",
            "pattern_type": "scheduled_recurring_action",
            "action_type": action_type,
            "target_entity": target_entity,
            "target_entity_type": subset.iloc[0]["target_entity_type"],
            "occurrences": int(row["count"]),
            "actors_involved": [actor_id],
            "cases_involved": list(subset["case_id"].unique()),
            "mean_interval_hours": mean,
            "stddev_interval_hours": stddev,
            "regularity_score": regularity_score,
            "event_ids": row["event_ids"],
            "sample_context_payloads": [
                subset.iloc[i]["context_payload"] for i in range(min(3, len(subset)))
            ],
        })

    return findings


def detect_cross_case(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Same structural pattern across multiple unrelated cases.
    Renamed from 'cross_workflow' — per client's vocabulary, case is the term.

    Also computes per-actor intervals to fix the v1 issue where global averages
    were misleading.
    """
    if df.empty:
        return []

    threshold = settings.MIN_REPETITION_THRESHOLD
    findings = []

    for sig, group_df in df.groupby("cross_case_signature"):
        cases = group_df["case_id"].unique()
        if len(cases) < 2:
            continue
        if len(group_df) < threshold:
            continue

        action_type, target_entity_type = sig.split("::")

        unique_targets = group_df["target_entity"].nunique()
        if unique_targets < 2:
            continue

        # FIX FROM V1: per-actor interval instead of global
        per_actor_intervals = []
        for actor_id, actor_df in group_df.groupby("actor_id"):
            if len(actor_df) < 2:
                continue
            ts = actor_df["timestamp"].sort_values()
            intervals = ts.diff().dt.total_seconds().dropna() / 3600.0
            per_actor_intervals.extend(intervals.tolist())

        if per_actor_intervals:
            mean_hours = sum(per_actor_intervals) / len(per_actor_intervals)
            import statistics
            stddev_hours = statistics.stdev(per_actor_intervals) if len(per_actor_intervals) > 1 else 0.0
        else:
            mean_hours, stddev_hours = 0.0, 0.0

        findings.append({
            "detector_source": "heuristic:cross_case",
            "pattern_type": "recurring_cross_case_action",
            "action_type": action_type,
            "target_entity": "<multiple>",
            "target_entity_type": target_entity_type,
            "occurrences": int(len(group_df)),
            "actors_involved": list(group_df["actor_id"].unique()),
            "cases_involved": list(cases),
            "mean_interval_hours": float(mean_hours),
            "stddev_interval_hours": float(stddev_hours),
            "event_ids": list(group_df["event_id"]),
            "sample_context_payloads": [
                group_df.iloc[i]["context_payload"] for i in range(min(3, len(group_df)))
            ],
        })

    return findings


def run_all_heuristic_detectors(df: pd.DataFrame) -> list[dict[str, Any]]:
    return (
        detect_repetition(df)
        + detect_temporal_regularity(df)
        + detect_cross_case(df)
    )
