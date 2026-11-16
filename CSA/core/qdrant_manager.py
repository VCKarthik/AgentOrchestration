from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, Filter, FieldCondition, MatchValue
from core.embedding_engine import VECTOR_SIZE, record_to_text, embed_text
import uuid

_client = None
_collections_initialized = False
_indexed = False

COLLECTIONS = {
    "emails":          "csa_emails",
    "documents":       "csa_documents",
    "calendar_events": "csa_calendar_events",
    "case_history":    "csa_case_history",
}

def get_client():
    global _client
    if _client is None:
        _client = QdrantClient(":memory:")
        print("[Qdrant] Client ready (in-memory mode).")
    return _client

def init_collections():
    global _collections_initialized
    if _collections_initialized: return
    c = get_client()
    existing = [col.name for col in c.get_collections().collections]
    for key, name in COLLECTIONS.items():
        if name not in existing:
            c.create_collection(collection_name=name,
                                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE))
    _collections_initialized = True
    print("[Qdrant] Collections ready.")

def index_all_records():
    global _indexed
    if _indexed: return
    init_collections()
    from core.retrieval_engine import get_all_records
    total = 0
    for source_type, collection_name in COLLECTIONS.items():
        records = get_all_records(source_type)
        if not records: continue
        points = []
        for record in records:
            text = record_to_text(source_type, record)
            if not text.strip(): continue
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=embed_text(text),
                payload={
                    "source_type": source_type,
                    "source_id":   record["id"],
                    "case_id":     record.get("case_id",""),
                    "case_type":   record.get("case_type",""),
                    "text":        text[:500],
                }
            ))
        if points:
            get_client().upsert(collection_name=collection_name, points=points)
            total += len(points)
            print(f"[Qdrant] Indexed {len(points)} {source_type} records.")
    _indexed = True
    print(f"[Qdrant] Total indexed: {total} records.")

def search(query_text, top_k=5, min_score=0.3, case_id=None, source_types=None):
    init_collections()
    query_vector = embed_text(query_text)
    results = {}
    for source_type in (source_types or list(COLLECTIONS.keys())):
        collection_name = COLLECTIONS.get(source_type)
        if not collection_name: continue
        try:
            query_filter = None
            if case_id:
                query_filter = Filter(must=[FieldCondition(key="case_id", match=MatchValue(value=case_id))])
            hits = get_client().query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=top_k,
                query_filter=query_filter,
            ).points
            # Filter by minimum relevance score
            hits = [h for h in hits if h.score >= min_score]
            results[source_type] = [{
                "source_id":       h.payload.get("source_id"),
                "source_type":     h.payload.get("source_type"),
                "case_id":         h.payload.get("case_id"),
                "case_type":       h.payload.get("case_type"),
                "relevance_score": round(h.score, 4),
            } for h in hits]
        except Exception as e:
            print(f"[Qdrant] Error in {source_type}: {e}")
            results[source_type] = []
    return results

def upsert_record(source_type, record):
    init_collections()
    text = record_to_text(source_type, record)
    if not text.strip(): return
    get_client().upsert(
        collection_name=COLLECTIONS[source_type],
        points=[PointStruct(
            id=str(uuid.uuid4()), vector=embed_text(text),
            payload={"source_type":source_type,"source_id":record["id"],
                     "case_id":record.get("case_id",""),"case_type":record.get("case_type",""),"text":text[:500]}
        )]
    )