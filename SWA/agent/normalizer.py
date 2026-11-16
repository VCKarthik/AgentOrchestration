"""
Normalizer — creates domain-blind structural signatures.
The ONLY file that touches event structure for detection purposes.

Rule: NEVER use anything from context_payload here. That's reserved for LLM.
"""
import pandas as pd


def add_signature_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()

    # Per-event structural signature
    out["structural_signature"] = out["action_type"] + "::" + out["target_entity_type"]

    # Actor-target repetition signature (for repetition detector)
    out["actor_target_signature"] = (
        out["actor_id"] + "::" + out["action_type"] + "::" + out["target_entity"]
    )

    # Cross-case signature (for cross-case detector)
    out["cross_case_signature"] = out["action_type"] + "::" + out["target_entity_type"]

    return out


def compute_intervals(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Compute per-group time interval statistics."""
    if df.empty:
        return pd.DataFrame()

    df_sorted = df.sort_values("timestamp")
    groups = []
    for key, group_df in df_sorted.groupby(group_col):
        if len(group_df) < 2:
            continue
        ts = group_df["timestamp"].sort_values()
        intervals_hours = ts.diff().dt.total_seconds().dropna() / 3600.0
        groups.append({
            "group_key": key,
            "count": len(group_df),
            "mean_interval_hours": float(intervals_hours.mean()),
            "stddev_interval_hours": float(intervals_hours.std()) if len(intervals_hours) > 1 else 0.0,
            "actors": list(group_df["actor_id"].unique()),
            "cases": list(group_df["case_id"].unique()),
            "event_ids": list(group_df["event_id"]),
        })

    return pd.DataFrame(groups)
