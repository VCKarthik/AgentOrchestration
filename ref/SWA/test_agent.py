"""
Offline sanity tests — run without DB or LLM.
Tests the core detection logic by loading synthetic events from JSON
and running them through the pipeline in-memory.

Run:   python -m tests.test_agent
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.detectors import run_all_heuristic_detectors
from agent.escalator import split_findings
from agent.ml_detector import detect_unsupervised_clusters
from agent.normalizer import add_signature_columns
from agent.scorer import score_all


def load_events() -> pd.DataFrame:
    path = Path("data/synthetic_events.json")
    if not path.exists():
        raise FileNotFoundError("Run `python -m data.synthetic_events` first")
    data = json.loads(path.read_text())
    df = pd.DataFrame(data["events"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def _check(name: str, ok: bool, detail: str = ""):
    icon = "✓" if ok else "✗"
    print(f"  {icon} {name}" + (f"  [{detail}]" if detail else ""))


def test_normalizer():
    print("\nTEST: Normalizer adds signatures")
    df = add_signature_columns(load_events())
    required = {"structural_signature", "actor_target_signature", "cross_case_signature"}
    _check("signature columns present", required.issubset(df.columns))


def test_heuristic_detectors():
    print("\nTEST: Heuristic detectors")
    df = add_signature_columns(load_events())
    findings = run_all_heuristic_detectors(df)
    _check("heuristic detectors produced findings", len(findings) > 0, f"n={len(findings)}")

    chase_findings = [f for f in findings if f["action_type"] == "sent_followup"]
    _check("follow-up chase patterns detected", len(chase_findings) > 0, f"n={len(chase_findings)}")


def test_ml_detector():
    print("\nTEST: ML (DBSCAN) detector")
    df = add_signature_columns(load_events())
    findings = detect_unsupervised_clusters(df)
    _check("ML detector ran without error", True, f"clusters={len(findings)}")


def test_scoring_and_dedup():
    print("\nTEST: Scorer + dedup")
    df = add_signature_columns(load_events())
    raw = run_all_heuristic_detectors(df) + detect_unsupervised_clusters(df)
    scored = score_all(raw)
    _check("scoring completed", len(scored) > 0)
    _check("all scored items have confidence", all("confidence" in f for f in scored))
    _check("all scored items have decision", all(f.get("decision") in ("recommend", "watch", "escalate") for f in scored))


def test_domain_agnostic():
    print("\nTEST: Domain-agnostic structural signatures")
    df = add_signature_columns(load_events())
    raw = run_all_heuristic_detectors(df)

    banned = {"vendor", "plot", "police", "references", "construction", "insurance", "hiring"}
    leaked = []
    for f in raw:
        for key in ("action_type", "target_entity_type", "pattern_type"):
            val = str(f.get(key, "")).lower()
            for word in banned:
                if word in val:
                    leaked.append((key, val, word))

    _check("no domain words in detection structure", not leaked, str(leaked)[:80] if leaked else "")


def test_split_findings():
    print("\nTEST: Recommendation vs escalation split")
    df = add_signature_columns(load_events())
    raw = run_all_heuristic_detectors(df) + detect_unsupervised_clusters(df)
    scored = score_all(raw)
    for s in scored:
        s.setdefault("description", "stub")
        s.setdefault("domain_contextualized_description", "stub")
    recs, escs = split_findings(scored)
    _check("split completed", True, f"{len(recs)} recs, {len(escs)} escalations")


def main():
    print("=" * 70)
    print("SHADOW WORK AGENT v2 — SANITY TESTS")
    print("=" * 70)

    test_normalizer()
    test_heuristic_detectors()
    test_ml_detector()
    test_scoring_and_dedup()
    test_domain_agnostic()
    test_split_findings()

    print("\n" + "=" * 70)
    print("Tests complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
