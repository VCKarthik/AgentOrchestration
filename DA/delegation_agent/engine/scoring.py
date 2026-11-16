from __future__ import annotations

from typing import List

from ..models.assignee import Assignee, Seniority
from ..models.outputs import CandidateRanking
from ..models.task import Priority, Task


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WEIGHTS = {
    "skill_match": 0.45,        # increased importance
    "experience_fit": 0.20,
    "specialization_fit": 0.15,
    "performance_fit": 0.10,
    "capacity_fit": 0.10,
}

RECOMMENDATION_BOOST: float = 8.0


SENIORITY_RANK = {
    Seniority.JUNIOR: 1,
    Seniority.INTERMEDIATE: 2,
    Seniority.SENIOR: 3,
    Seniority.EXPERT: 4,
    Seniority.LEAD: 5,
}

PRIORITY_SENIORITY_FLOOR = {
    Priority.CRITICAL: 3,
    Priority.HIGH: 2,
    Priority.MEDIUM: 1,
    Priority.LOW: 1,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _priority_to_str(priority):
    return priority if isinstance(priority, str) else priority.value


def _seniority_to_str(s):
    return s if isinstance(s, str) else s.value


# ---------------------------------------------------------------------------
# Component scores
# ---------------------------------------------------------------------------

def _score_skill_match(assignee, task):
    required = [s.lower() for s in (task.required_skills or [])]
    if not required:
        return 100.0

    skill_map = assignee.skill_map()
    matched = [s for s in required if s in skill_map]

    coverage = len(matched) / len(required)

    if matched:
        avg_prof = sum(skill_map[s] for s in matched) / len(matched)
    else:
        avg_prof = 0

    score = (coverage * 75) + ((avg_prof / 100) * 25)

    # 🔥 STRONG penalty for zero match
    if coverage == 0:
        score *= 0.5

    return round(score, 2)


def _score_experience_fit(assignee, task):
    p = _priority_to_str(task.priority)
    s = _seniority_to_str(assignee.seniority)

    required = PRIORITY_SENIORITY_FLOOR.get(p, 1)
    actual = SENIORITY_RANK.get(s, 1)

    if actual >= required:
        return 100
    if actual == required - 1:
        return 60
    return 25   # 🔥 stronger penalty


def _score_specialization_fit(assignee, task):
    if not task.business_domain:
        return 100

    if assignee.covers_domain(task.business_domain):
        return 100
    else:
        return 30   # 🔥 stronger penalty


def _score_performance_fit(assignee):
    return max(0, min(float(getattr(assignee, "performance_score", 50)), 100))


def _score_capacity_fit(assignee):
    util = float(assignee.utilization_percent)

    if util >= 98:
        return 5   # not zero → avoids killing score

    return max(10, (1 - util / 100) * 100)


# ---------------------------------------------------------------------------
# Main scoring
# ---------------------------------------------------------------------------

def compute_candidate_score(assignee: Assignee, task: Task) -> CandidateRanking:

    skill = _score_skill_match(assignee, task)
    exp = _score_experience_fit(assignee, task)
    spec = _score_specialization_fit(assignee, task)
    perf = _score_performance_fit(assignee)
    cap = _score_capacity_fit(assignee)

    composite = (
        skill * WEIGHTS["skill_match"]
        + exp * WEIGHTS["experience_fit"]
        + spec * WEIGHTS["specialization_fit"]
        + perf * WEIGHTS["performance_fit"]
        + cap * WEIGHTS["capacity_fit"]
    )

    # recommendation boost
    boost = (
        RECOMMENDATION_BOOST
        if assignee.assignee_id in (task.recommended_candidates or [])
        else 0
    )

    final_score = min(composite + boost, 100)

    return CandidateRanking(
        assignee_id=assignee.assignee_id,
        name=assignee.name,
        role=assignee.role,
        skill_match_score=round(skill, 2),
        domain_match_score=round(spec, 2),
        capacity_score=round(cap, 2),
        priority_handling_score=round(exp, 2),
        recommendation_boost=boost,
        composite_score=round(final_score, 2),
        utilization_percent=assignee.utilization_percent,
        availability_status=_safe_status(assignee),
        seniority=_seniority_to_str(assignee.seniority),
    )


def _safe_status(a):
    return a.availability_status if isinstance(a.availability_status, str) else a.availability_status.value


def rank_candidates(assignees: List[Assignee], task: Task) -> List[CandidateRanking]:
    rankings = [compute_candidate_score(a, task) for a in assignees]
    rankings.sort(key=lambda r: r.composite_score, reverse=True)
    return rankings