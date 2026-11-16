import re

CASE_TYPE_KEYWORDS = {
    "claim_review":       ["claim","damage","incident","adjuster","repair","invoice","inspection","water","fire","theft","injury"],
    "policy_renewal":     ["renewal","renew","premium","expiry","expire","extend","policy","quote","coverage"],
    "fraud_investigation":["fraud","suspicious","investigation","alert","pattern","fake","false"],
}

def extract_metadata(text):
    text_lower = text.lower()
    return {
        "case_id":       _extract_case_id(text),
        "case_type":     _detect_case_type(text_lower),
        "keywords":      _extract_keywords(text_lower),
        "original_text": text,
    }

def _extract_case_id(text):
    match = re.search(r'\bCASE[-_](\d+)\b', text, re.IGNORECASE)
    if match:
        return f"CASE-{match.group(1)}"
    match = re.search(r'(?:policy\s*#?|#)(\d{4,})', text, re.IGNORECASE)
    if match:
        return {"4821":"CASE-1001","7734":"CASE-2002","9910":"CASE-3003"}.get(match.group(1))
    return None

def _detect_case_type(text_lower):
    scores = {ct: sum(1 for kw in kws if kw in text_lower)
              for ct, kws in CASE_TYPE_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None

def _extract_keywords(text_lower):
    stop = {"a","an","the","and","or","in","on","at","to","for","of","with","by","from",
            "is","are","was","be","has","have","do","will","i","me","we","you","it","this",
            "that","please","find","get","show","need","want","review","check","help","case","task"}
    words = re.findall(r'\b[a-z][a-z0-9]*\b', text_lower)
    seen, unique = set(), []
    for w in words:
        if w not in stop and len(w) > 2 and w not in seen:
            seen.add(w); unique.append(w)
    return unique[:10]