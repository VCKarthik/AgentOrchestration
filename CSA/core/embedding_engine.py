from sentence_transformers import SentenceTransformer

MODEL_NAME  = "all-MiniLM-L6-v2"
VECTOR_SIZE = 384
_model = None

def get_model():
    global _model
    if _model is None:
        print("[Embedding] Loading model...")
        _model = SentenceTransformer(MODEL_NAME)
        print("[Embedding] Model ready.")
    return _model

def embed_text(text):
    return get_model().encode(text, normalize_embeddings=True).tolist()

def record_to_text(source_type, record):
    if source_type == "emails":
        return "\n".join(filter(None, [
            f"Subject: {record.get('subject','')}",
            f"From: {record.get('sender','')}",
            f"To: {record.get('recipients','')}",
            f"Body: {record.get('body','')}",
        ]))
    if source_type == "documents":
        tags = record.get("tags","")
        if isinstance(tags, list): tags = ", ".join(tags)
        return "\n".join(filter(None, [
            f"Filename: {record.get('filename','')}",
            f"Description: {record.get('description','')}",
            f"Tags: {tags}",
        ]))
    if source_type == "calendar_events":
        att = record.get("attendees","")
        if isinstance(att, list): att = ", ".join(att)
        return "\n".join(filter(None, [
            f"Title: {record.get('title','')}",
            f"Location: {record.get('location','')}",
            f"Description: {record.get('description','')}",
            f"Attendees: {att}",
        ]))
    if source_type == "case_history":
        return "\n".join(filter(None, [
            f"Event: {record.get('event_type','')}",
            f"Notes: {record.get('notes','')}",
            f"Status: {record.get('status','')}",
        ]))
    return str(record)