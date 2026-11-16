"""
Cluster Tracker — Incremental Learning Insights
─────────────────────────────────────────────────────────────────
Saves cluster snapshots after each run and compares with the previous
snapshot to surface what changed:

  - new_clusters         : patterns we hadn't seen before
  - strengthened_clusters: patterns growing (more events / cases)
  - dissolved_clusters   : patterns from before that no longer cluster
  - stable_clusters      : patterns roughly the same size

This is what makes the agent measurably "learn" as more cases arrive.
Run after run, the comparison output tells you whether the new data
revealed new behaviors or reinforced known ones.
"""
import logging
from typing import Any, Optional

from db import db

logger = logging.getLogger("shadow_work.cluster_tracker")


def _to_summary(finding: dict) -> dict:
    """Compact representation of one cluster, safe to serialize."""
    return {
        "fingerprint": finding["cluster_fingerprint"],
        "action_type": finding["action_type"],
        "target_entity_type": finding["target_entity_type"],
        "dominant_actor_type": finding.get("dominant_actor_type", "unknown"),
        "median_hour_of_day": finding.get("median_hour_of_day"),
        "size": finding["occurrences"],
        "n_actors": finding.get("n_actors", len(finding.get("actors_involved", []))),
        "n_cases": finding.get("n_cases", len(finding.get("cases_involved", []))),
        "mean_interval_hours": round(finding.get("mean_interval_hours", 0), 2),
    }


def save_current_snapshot(
    run_id: str,
    total_cases: int,
    total_events: int,
    ml_findings: list[dict],
) -> str:
    """Persist a snapshot of the current ML clusters."""
    cluster_summaries = [_to_summary(f) for f in ml_findings]
    snapshot_id = db.save_cluster_snapshot(
        run_id=run_id,
        total_cases=total_cases,
        total_events=total_events,
        clusters=cluster_summaries,
    )
    logger.info(
        f"[snapshot] saved {snapshot_id}: {len(cluster_summaries)} clusters, "
        f"{total_cases} cases, {total_events} events"
    )
    return snapshot_id


def compare_with_previous(current_run_id: str, current_findings: list[dict]) -> Optional[dict]:
    """
    Return a comparison vs. the previous snapshot.
    Returns None if there's no previous snapshot.
    """
    previous = db.get_previous_snapshot(before_run_id=current_run_id)
    if previous is None:
        logger.info("[compare] no previous snapshot — first run, baseline established")
        return None

    prev_clusters = previous["cluster_summary"] or []
    if isinstance(prev_clusters, str):
        import json
        prev_clusters = json.loads(prev_clusters)

    current_summaries = [_to_summary(f) for f in current_findings]

    prev_by_fp = {c["fingerprint"]: c for c in prev_clusters}
    curr_by_fp = {c["fingerprint"]: c for c in current_summaries}

    new_clusters = []
    strengthened = []
    dissolved = []
    stable = []

    # Walk current — find new and strengthened
    for fp, curr in curr_by_fp.items():
        if fp not in prev_by_fp:
            new_clusters.append({
                **curr,
                "verdict": "NEW pattern discovered — wasn't visible in previous run",
            })
        else:
            prev = prev_by_fp[fp]
            size_delta = curr["size"] - prev["size"]
            cases_delta = curr["n_cases"] - prev["n_cases"]
            if size_delta >= 3 or cases_delta >= 2:
                strengthened.append({
                    **curr,
                    "previous_size": prev["size"],
                    "current_size": curr["size"],
                    "size_delta": size_delta,
                    "cases_delta": cases_delta,
                    "verdict": (
                        f"Pattern STRENGTHENED — grew from {prev['size']} to {curr['size']} events"
                        + (f", spans {cases_delta} more cases" if cases_delta > 0 else "")
                    ),
                })
            else:
                stable.append({
                    **curr,
                    "previous_size": prev["size"],
                    "current_size": curr["size"],
                    "verdict": "Pattern STABLE — roughly same size as before",
                })

    # Walk previous — find dissolved
    for fp, prev in prev_by_fp.items():
        if fp not in curr_by_fp:
            dissolved.append({
                **prev,
                "verdict": "DISSOLVED — pattern no longer clusters, may have resolved",
            })

    return {
        "previous_run_id": previous["run_id"],
        "previous_snapshot_id": previous["snapshot_id"],
        "previous_total_cases": previous["total_cases"],
        "previous_total_events": previous["total_events"],
        "previous_clusters_count": previous["clusters_found"],
        "current_run_id": current_run_id,
        "current_clusters_count": len(current_summaries),
        "delta_summary": {
            "new_clusters": len(new_clusters),
            "strengthened_clusters": len(strengthened),
            "stable_clusters": len(stable),
            "dissolved_clusters": len(dissolved),
        },
        "new_clusters": new_clusters,
        "strengthened_clusters": strengthened,
        "stable_clusters": stable,
        "dissolved_clusters": dissolved,
    }


def get_evolution_timeline() -> list[dict]:
    """
    Return all snapshots ordered by time — useful for plotting how
    clusters have evolved across rounds.
    """
    snapshots = db.list_all_snapshots()
    timeline = []
    for s in snapshots:
        timeline.append({
            "snapshot_id": s["snapshot_id"],
            "timestamp": s["snapshot_timestamp"],
            "total_cases": s["total_cases"],
            "total_events": s["total_events"],
            "clusters_found": s["clusters_found"],
        })
    return timeline
