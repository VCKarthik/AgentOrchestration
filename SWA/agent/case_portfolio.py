"""
Case Portfolio Builder
─────────────────────────────────────────────────────────────────
Per Ankit: "Collect the activities happening for that specific case,
            create a portfolio."

Given a case_id, this module builds a full historical view:
timeline, action counts, actor counts, duration, etc.

This is the "case sheet" — the per-case summary that becomes the
basic unit of downstream analysis.
"""
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from agent.models import CasePortfolio, CaseTimelineEntry
from db import db

logger = logging.getLogger("shadow_work.case_portfolio")


def build_portfolio(case_id: str) -> Optional[CasePortfolio]:
    """Build a full portfolio for one case."""
    # Pull ALL events for this case (no time window — we want full history)
    from datetime import timedelta
    far_past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    far_future = datetime.now(timezone.utc) + timedelta(days=1)
    df = db.fetch_events_in_window(far_past, far_future, case_id=case_id)

    if df.empty:
        logger.warning(f"[portfolio] no events found for case {case_id}")
        return None

    # Get case metadata
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT case_type, status FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if not row:
            logger.warning(f"[portfolio] case {case_id} not registered in cases table")
            return None
        case_type = row["case_type"]
        case_status = row["status"]

    # Build timeline
    timeline = [
        CaseTimelineEntry(
            timestamp=row["timestamp"],
            actor_id=row["actor_id"],
            actor_type=row["actor_type"],
            action_type=row["action_type"],
            target_entity=row["target_entity"],
            outcome=row["outcome"],
        )
        for _, row in df.iterrows()
    ]

    # Counters
    action_counts = dict(Counter(df["action_type"].tolist()))
    actor_counts = dict(Counter(df["actor_id"].tolist()))
    target_counts = dict(Counter(df["target_entity"].tolist()))

    # Duration
    duration_hours = None
    if len(df) >= 2:
        duration = df["timestamp"].max() - df["timestamp"].min()
        duration_hours = round(duration.total_seconds() / 3600, 2)

    portfolio = CasePortfolio(
        case_id=case_id,
        case_type=case_type,
        status=case_status,
        total_events=len(df),
        distinct_actors=df["actor_id"].nunique(),
        distinct_actions=df["action_type"].nunique(),
        case_duration_hours=duration_hours,
        timeline=timeline,
        action_counts=action_counts,
        actor_counts=actor_counts,
        target_counts=target_counts,
    )

    # Persist
    db.save_case_portfolio({
        "case_id": case_id,
        "total_events": portfolio.total_events,
        "distinct_actors": portfolio.distinct_actors,
        "distinct_actions": portfolio.distinct_actions,
        "case_duration_hours": portfolio.case_duration_hours,
        "portfolio_json": portfolio.model_dump(mode="json"),
    })
    logger.info(
        f"[portfolio] built for {case_id}: {portfolio.total_events} events, "
        f"{portfolio.distinct_actors} actors, {portfolio.distinct_actions} distinct actions"
    )

    return portfolio


def build_all_portfolios() -> list[CasePortfolio]:
    """Build portfolios for every registered case."""
    case_ids = db.list_all_cases()
    portfolios = []
    for cid in case_ids:
        p = build_portfolio(cid)
        if p:
            portfolios.append(p)
    return portfolios
