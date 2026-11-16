from core.retrieval_engine import fetch_context, get_all_records, validate_context
from core.qdrant_manager import search as qdrant_search
from core.metadata_extractor import extract_metadata

def hybrid_fetch(task_text, top_k=5):
    meta      = extract_metadata(task_text)
    case_id   = meta["case_id"]
    case_type = meta["case_type"]
    keywords  = meta["keywords"]

    print(f"[Hybrid] case_id={case_id}, case_type={case_type}, keywords={keywords}")

    # SQLite exact match
    sql_results = {}
    if case_id and case_type:
        sql_results = fetch_context(case_id, case_type)
    elif case_id:
        for ct in ["claim_review","policy_renewal","fraud_investigation"]:
            r = fetch_context(case_id, ct)
            if sum(len(v) for v in r.values()) > 0:
                sql_results = r; case_type = ct; break

    # Qdrant semantic search
    qdrant_results = qdrant_search(query_text=task_text, top_k=top_k, case_id=case_id)

    # Hydrate Qdrant hits with full records from SQLite
    qdrant_full = _hydrate(qdrant_results)

    # Merge
    merged = _merge(sql_results, qdrant_full)

    return {
        "results": merged,
        "meta": {
            "case_id":    case_id,
            "case_type":  case_type,
            "keywords":   keywords,
            "sql_hits":   sum(len(v) for v in sql_results.values()),
            "qdrant_hits":sum(len(v) for v in qdrant_full.values()),
        }
    }

def _hydrate(qdrant_results):
    hydrated = {"emails":[],"documents":[],"calendar_events":[],"case_history":[]}
    for source_type, hits in qdrant_results.items():
        all_records   = get_all_records(source_type)
        records_by_id = {r["id"]: r for r in all_records}
        for hit in hits:
            sid = hit.get("source_id")
            if sid and sid in records_by_id:
                r = dict(records_by_id[sid])
                r["relevance_score"] = hit["relevance_score"]
                r["matched_by"]      = "semantic"
                hydrated[source_type].append(r)
    return hydrated

def _merge(sql_results, qdrant_results):
    merged = {}
    for st in ["emails","documents","calendar_events","case_history"]:
        seen, combined = set(), []
        for r in sql_results.get(st, []):
            rid = r.get("id")
            if rid and rid not in seen:
                r = dict(r); r["relevance_score"] = 1.0; r["matched_by"] = "exact"
                seen.add(rid); combined.append(r)
        for r in qdrant_results.get(st, []):
            rid = r.get("id")
            if rid and rid not in seen:
                seen.add(rid); combined.append(r)
        combined.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        merged[st] = combined
    return merged