"""
Unsupervised ML Detector — DBSCAN Clustering with Cluster Fingerprinting

V3 changes:
  - Each cluster gets a STABLE FINGERPRINT — a string identity that lets us
    track the same cluster across runs even though DBSCAN's numeric label
    (0, 1, 2…) is arbitrary and changes between runs.

  - Fingerprint is built from: dominant_action + dominant_target_type +
    dominant_actor_kind + time_bucket. Two clusters with the same fingerprint
    on different runs are considered "the same pattern."

  - This is what makes incremental learning visible — we can say "Cluster X
    that we saw in round 1 grew from 23 events to 38 events in round 2."
"""
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler

from config.settings import settings


def _featurize_events(df: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    features_df = df.copy()
    features_df["hour_of_day"] = features_df["timestamp"].dt.hour
    features_df["day_of_week"] = features_df["timestamp"].dt.dayofweek

    action_dummies = pd.get_dummies(features_df["action_type"], prefix="action")
    target_dummies = pd.get_dummies(features_df["target_entity_type"], prefix="target")
    actor_type_dummies = pd.get_dummies(features_df["actor_type"], prefix="actor_type")

    numeric = features_df[["hour_of_day", "day_of_week"]].astype(float)

    feature_matrix = pd.concat(
        [action_dummies, target_dummies, actor_type_dummies, numeric],
        axis=1,
    )
    scaler = StandardScaler()
    scaled = scaler.fit_transform(feature_matrix.values)
    return scaled, features_df


def _time_bucket(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "off_hours"


def _make_fingerprint(cluster_events: pd.DataFrame) -> str:
    """
    Build a stable identity for this cluster.

    Format: <dominant_action>::<dominant_target_type>::<dominant_actor_type>::<time_bucket>

    Same fingerprint across runs = same conceptual pattern.
    """
    dom_action = cluster_events["action_type"].mode()[0]
    dom_target = cluster_events["target_entity_type"].mode()[0]
    dom_actor = cluster_events["actor_type"].mode()[0]
    median_hour = int(cluster_events["timestamp"].dt.hour.median())
    bucket = _time_bucket(median_hour)
    return f"{dom_action}::{dom_target}::{dom_actor}::{bucket}"


def detect_unsupervised_clusters(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Run DBSCAN. Each cluster gets a fingerprint for snapshot tracking."""
    if df.empty or len(df) < settings.DBSCAN_MIN_SAMPLES:
        return []

    feature_matrix, enriched_df = _featurize_events(df)

    db_model = DBSCAN(
        eps=settings.DBSCAN_EPS,
        min_samples=settings.DBSCAN_MIN_SAMPLES,
    )
    labels = db_model.fit_predict(feature_matrix)

    enriched_df = enriched_df.copy()
    enriched_df["cluster_label"] = labels

    findings = []
    unique_clusters = sorted(set(labels) - {-1})  # exclude noise

    for cluster_id in unique_clusters:
        cluster_events = enriched_df[enriched_df["cluster_label"] == cluster_id]
        if len(cluster_events) < settings.MIN_REPETITION_THRESHOLD:
            continue

        # Stable fingerprint for snapshot comparison
        fingerprint = _make_fingerprint(cluster_events)

        dominant_action = cluster_events["action_type"].mode()[0]
        dominant_target = cluster_events["target_entity_type"].mode()[0]
        dominant_actor_type = cluster_events["actor_type"].mode()[0]
        actors = list(cluster_events["actor_id"].unique())
        cases = list(cluster_events["case_id"].unique())

        # Distribution stats — useful for the LLM enricher
        action_dist = dict(Counter(cluster_events["action_type"]))
        actor_kind_dist = dict(Counter(cluster_events["actor_id"]))

        # Temporal stats
        ts_sorted = cluster_events["timestamp"].sort_values()
        if len(ts_sorted) >= 2:
            intervals = ts_sorted.diff().dt.total_seconds().dropna() / 3600.0
            mean_hours = float(intervals.mean())
            stddev_hours = float(intervals.std()) if len(intervals) > 1 else 0.0
        else:
            mean_hours, stddev_hours = 0.0, 0.0

        median_hour = int(cluster_events["timestamp"].dt.hour.median())

        findings.append({
            "detector_source": "ml:dbscan_clustering",
            "pattern_type": "unsupervised_discovered_cluster",
            "cluster_id": int(cluster_id),
            "cluster_fingerprint": fingerprint,
            "action_type": dominant_action,
            "target_entity": "<cluster>",
            "target_entity_type": dominant_target,
            "dominant_actor_type": dominant_actor_type,
            "median_hour_of_day": median_hour,
            "occurrences": int(len(cluster_events)),
            "actors_involved": actors[:10],
            "n_actors": len(actors),
            "cases_involved": cases[:10],
            "n_cases": len(cases),
            "action_distribution": action_dist,
            "actor_distribution": dict(list(actor_kind_dist.items())[:5]),
            "mean_interval_hours": mean_hours,
            "stddev_interval_hours": stddev_hours,
            "event_ids": list(cluster_events["event_id"])[:20],
            "sample_context_payloads": [
                cluster_events.iloc[i]["context_payload"]
                for i in range(min(3, len(cluster_events)))
            ],
        })

    return findings
