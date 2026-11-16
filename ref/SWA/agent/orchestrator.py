"""
Main Orchestrator — Shadow Work Agent v3

V3 changes:
  - After each run, saves a cluster snapshot
  - Compares current clusters vs. previous snapshot
  - Outputs cluster_evolution section showing what changed
  - Skips portfolio building when --no-portfolios flag is set (faster on big DBs)

Usage:
  python -m agent.orchestrator                      # global sweep
  python -m agent.orchestrator --case_id case_xyz   # single case
  python -m agent.orchestrator --no-portfolios      # skip case portfolios
  python -m agent.orchestrator --evolution          # just print snapshot timeline
"""
import argparse
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure output dir exists before logging setup
Path("output").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("output/agent.log", mode="a"),
    ],
)
logger = logging.getLogger("shadow_work.orchestrator")

from agent.case_portfolio import build_all_portfolios, build_portfolio
from agent.cluster_tracker import (
    compare_with_previous, get_evolution_timeline, save_current_snapshot,
)
from agent.detectors import run_all_heuristic_detectors
from agent.escalator import split_findings
from agent.llm_enricher import enrich_findings
from agent.ml_detector import detect_unsupervised_clusters
from agent.models import (
    AgentOutput, AnalysisWindow, AutomationRecommendation,
    Escalation, Finding, RunMetrics, TemporalSignature,
)
from agent.normalizer import add_signature_columns
from agent.scorer import score_all
from config.settings import settings
from db import db


def _finding_from_dict(f: dict, run_id: str, idx: int) -> Finding:
    return Finding(
        finding_id=f"{run_id}_f_{idx:03d}",
        detector_source=", ".join(f.get("detector_sources", [f.get("detector_source", "unknown")])),
        pattern_type=f["pattern_type"],
        pattern_signature=(
            f"action:{f['action_type']} → target_type:{f['target_entity_type']} "
            f"→ interval:~{round(f.get('mean_interval_hours', 0))}h"
        ),
        occurrences=f["occurrences"],
        actors_involved=f["actors_involved"][:10] if isinstance(f.get("actors_involved"), list) else [],
        cases_involved=f.get("cases_involved", [])[:10],
        temporal_signature=TemporalSignature(
            mean_interval_hours=round(f.get("mean_interval_hours", 0), 2),
            stddev_interval_hours=round(f.get("stddev_interval_hours", 0), 2),
            regularity_score=round(f.get("regularity_score", 0.0), 2),
        ),
        description=f.get("description", ""),
        domain_contextualized_description=f.get("domain_contextualized_description"),
        automation_recommendation=AutomationRecommendation(
            type="scheduled_automation_rule",
            trigger=f"after {round(f.get('mean_interval_hours', 0))}h with no resolution",
            action=f.get("automation_action", "Automate this repetitive action"),
        ),
        confidence=f["confidence"],
        risk_level=f["risk_level"],
        decision=f["decision"],
        requires_human_approval=f["requires_human_approval"],
        evidence_event_ids=f.get("event_ids", [])[:10],
    )


def analyze(
    case_id: Optional[str] = None,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
    trigger_type: str = "scheduled_sweep",
    skip_portfolios: bool = False,
) -> tuple[AgentOutput, dict]:
    """
    Run one analysis. Returns (output, run_metadata) where metadata includes
    the cluster comparison vs previous snapshot.
    """
    t0 = time.time()

    if window_start is None or window_end is None:
        window_start, window_end = db.default_window()

    scope = f"case:{case_id}" if case_id else "global"
    run_id = f"sw_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"

    logger.info(f"[{run_id}] starting analysis — scope={scope}")

    # 1. Ingest
    df = db.fetch_events_in_window(window_start, window_end, case_id=case_id)
    events_processed = len(df)
    logger.info(f"[{run_id}] loaded {events_processed} events")

    # 2. Build portfolios
    portfolios_out = []
    if skip_portfolios:
        logger.info(f"[{run_id}] skipping case portfolios (--no-portfolios)")
    elif case_id:
        p = build_portfolio(case_id)
        if p:
            portfolios_out.append(p)
    else:
        portfolios_out = build_all_portfolios()
    logger.info(f"[{run_id}] built {len(portfolios_out)} case portfolios")

    # 3. Normalize
    df = add_signature_columns(df)

    # 4. Heuristic detectors — always run
    heuristic_findings = run_all_heuristic_detectors(df) if events_processed else []

    # 5. ML detector (DBSCAN) — only when there is enough data for clustering
    #    to be meaningful. With a handful of cases the model finds noise, not
    #    patterns. Below the thresholds we fall back to heuristics only.
    n_cases = df["case_id"].nunique() if events_processed else 0
    ml_ready = (
        events_processed >= settings.ML_MIN_EVENTS
        and n_cases >= settings.ML_MIN_CASES
    )
    if ml_ready:
        ml_findings = detect_unsupervised_clusters(df)
        ml_status = f"{len(ml_findings)} clusters found"
    else:
        ml_findings = []
        ml_status = (
            f"skipped — need ≥{settings.ML_MIN_EVENTS} events "
            f"and ≥{settings.ML_MIN_CASES} cases "
            f"(have {events_processed} events, {n_cases} cases). "
            f"Heuristic detectors only."
        )

    raw_findings = heuristic_findings + ml_findings
    logger.info(
        f"[{run_id}] detectors: {len(heuristic_findings)} heuristic | "
        f"ML: {ml_status} | total={len(raw_findings)}"
    )

    # 6. Score + dedupe
    scored = score_all(raw_findings)
    logger.info(f"[{run_id}] scored (after dedup): {len(scored)} unique findings")

    # 7. LLM enrichment
    enriched = enrich_findings(scored)

    # 8. Split
    recommendations, escalations_raw = split_findings(enriched)

    # 9. Format
    findings = [_finding_from_dict(r, run_id, i) for i, r in enumerate(recommendations)]
    escalations = [Escalation(**e) for e in escalations_raw]
    elapsed_ms = (time.time() - t0) * 1000.0

    output = AgentOutput(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc),
        scope=scope,
        trigger_type=trigger_type,
        window_analyzed=AnalysisWindow(
            start=window_start, end=window_end, events_processed=events_processed
        ),
        case_portfolios=portfolios_out,
        findings=findings,
        escalations=escalations,
        metrics=RunMetrics(
            patterns_detected=len(enriched),
            recommendations_made=len(findings),
            escalations_raised=len(escalations),
            events_processed=events_processed,
            processing_time_ms=round(elapsed_ms, 1),
            detectors_used=(
                [
                    "heuristic:repetition",
                    "heuristic:temporal_regularity",
                    "heuristic:cross_case",
                    "ml:dbscan_clustering",
                ]
                if ml_ready else
                [
                    "heuristic:repetition",
                    "heuristic:temporal_regularity",
                    "heuristic:cross_case",
                    f"ml:skipped (need ≥{settings.ML_MIN_EVENTS} events, ≥{settings.ML_MIN_CASES} cases)",
                ]
            ),
        ),
    )

    # ──────────────────────────────────────────────────────────────
    # V3: Save cluster snapshot + compare with previous (global only)
    # ──────────────────────────────────────────────────────────────
    cluster_evolution = None
    if not case_id:  # only track snapshots on global runs
        try:
            total_cases = db.count_cases()
            total_events = db.count_events()

            # Persist run FIRST (snapshot has FK to it)
            db.save_analysis_run({
                "run_id": run_id,
                "run_timestamp": output.timestamp,
                "scope": scope,
                "window_start": window_start,
                "window_end": window_end,
                "events_processed": events_processed,
                "patterns_detected": len(enriched),
                "recommendations": len(findings),
                "escalations": len(escalations),
                "output_json": output.model_dump(mode="json"),
            })

            # Compare against previous BEFORE saving new snapshot
            cluster_evolution = compare_with_previous(run_id, ml_findings)

            # Save the new snapshot
            save_current_snapshot(
                run_id=run_id,
                total_cases=total_cases,
                total_events=total_events,
                ml_findings=ml_findings,
            )

            if cluster_evolution:
                d = cluster_evolution["delta_summary"]
                logger.info(
                    f"[{run_id}] cluster evolution: "
                    f"{d['new_clusters']} new, {d['strengthened_clusters']} strengthened, "
                    f"{d['stable_clusters']} stable, {d['dissolved_clusters']} dissolved"
                )
        except Exception as e:
            logger.warning(f"[{run_id}] snapshot tracking failed: {e}")
    else:
        # Case-level run — just save the run, no snapshot
        try:
            db.save_analysis_run({
                "run_id": run_id,
                "run_timestamp": output.timestamp,
                "scope": scope,
                "window_start": window_start,
                "window_end": window_end,
                "events_processed": events_processed,
                "patterns_detected": len(enriched),
                "recommendations": len(findings),
                "escalations": len(escalations),
                "output_json": output.model_dump(mode="json"),
            })
        except Exception as e:
            logger.warning(f"[{run_id}] could not persist run: {e}")

    logger.info(
        f"[{run_id}] complete in {elapsed_ms:.0f}ms — "
        f"{len(findings)} recommendations, {len(escalations)} escalations"
    )

    return output, {"cluster_evolution": cluster_evolution}


def main():
    parser = argparse.ArgumentParser(description="Shadow Work Agent v3")
    parser.add_argument("--case_id", type=str, default=None)
    parser.add_argument("--all-cases", action="store_true")
    parser.add_argument("--no-portfolios", action="store_true")
    parser.add_argument("--evolution", action="store_true",
                        help="Just print the cluster evolution timeline")
    args = parser.parse_args()

    if args.evolution:
        timeline = get_evolution_timeline()
        print("\n" + "=" * 70)
        print("CLUSTER EVOLUTION TIMELINE")
        print("=" * 70)
        if not timeline:
            print("(no snapshots yet — run the agent first)")
        else:
            for s in timeline:
                print(f"  {s['timestamp']}  cases={s['total_cases']:>4}  "
                      f"events={s['total_events']:>5}  clusters={s['clusters_found']}")
        print("=" * 70 + "\n")
        return

    if args.all_cases:
        case_ids = db.list_all_cases()
        print(f"\nRunning per-case analysis for {len(case_ids)} cases...\n")
        for cid in case_ids:
            output, _ = analyze(case_id=cid, skip_portfolios=False)
            out_file = Path("output") / f"{output.run_id}.json"
            out_file.write_text(json.dumps(output.model_dump(mode="json"), indent=2, default=str))
            print(f"  {cid}: {output.metrics.recommendations_made} recommendations, "
                  f"{output.metrics.escalations_raised} escalations → {out_file}")
        return

    output, meta = analyze(
        case_id=args.case_id,
        skip_portfolios=args.no_portfolios,
    )

    payload = output.model_dump(mode="json")
    if meta.get("cluster_evolution"):
        payload["cluster_evolution"] = meta["cluster_evolution"]

    print("\n" + "=" * 70)
    print(f"SHADOW WORK AGENT v3 — {'CASE ' + args.case_id if args.case_id else 'GLOBAL SWEEP'}")
    print("=" * 70)
    print(json.dumps(payload, indent=2, default=str))

    out_file = Path("output") / f"{output.run_id}.json"
    out_file.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nOutput saved to {out_file}")


if __name__ == "__main__":
    main()
