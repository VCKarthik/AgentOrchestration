"""
Packet Parser — converts a Context Stitching Agent (CSA) output packet into
a CaseInput the Risk Radar agent can evaluate.

Responsibilities:
  1. Map case_type (CSA's term)        -> workflow_type (registry term)
  2. Map filename -> document type     using keyword-overlap matching
  3. Derive workflow_state             from latest case_history entry
  4. Derive dependency_status          from history (blocked/escalated/pending)
  5. Derive prior_delay_count and prior_escalation_count from history events
  6. Derive sla_deadline / due_date    from calendar_events.end_time
  7. Map validation.status             -> operating_context (FULL vs PARTIAL)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


PACKETS_PATH  = Path(__file__).parent / "csa_packets.json"
REGISTRY_PATH = Path(__file__).parent / "workflow_registry.json"


# CSA's "case_type" -> our workflow registry key.
CASE_TYPE_MAP: Dict[str, str] = {
    "claim_review":      "insurance_claim",
    "vendor_review":     "vendor_onboarding",
    "contract_review":   "contract_review",
    "payment_review":    "payment_approval",
    "kyc_review":        "customer_kyc",
    "loan_review":       "loan_approval",
    "filing_review":     "regulatory_filing",
    "onboarding_review": "employee_onboarding",
}


def _normalize(s: str) -> str:
    """Strip extension, IDs, version suffixes; lowercase; collapse separators."""
    s = s.lower()
    s = re.sub(r"\.[a-z0-9]+$", "", s)         # extension
    s = re.sub(r"[#_\-]?\d+", "", s)           # numeric IDs (e.g., 4821, _v3)
    s = re.sub(r"[\s\-]+", "_", s)             # spaces/dashes -> underscore
    s = re.sub(r"_+", "_", s).strip("_")       # collapse underscores
    return s


def identify_doctype(filename: str, candidates: List[str]) -> Optional[str]:
    """Match a filename to one of the candidate document types.

    Strategy:
      1. Exact normalized equality
      2. Substring (filename contains doctype, or vice versa)
      3. Word-overlap score (best-scoring candidate wins, ties broken by length)
    """
    base = _normalize(filename)
    if not base:
        return None

    for c in candidates:
        if base == c:
            return c

    for c in candidates:
        if c in base or base in c:
            return c

    base_words = set(base.split("_"))
    best: Tuple[int, int, Optional[str]] = (0, 0, None)  # (score, len, name)
    for c in candidates:
        c_words = set(c.split("_"))
        score = len(base_words & c_words)
        if score > best[0] or (score == best[0] and len(c) > best[1]):
            best = (score, len(c), c)
    return best[2] if best[0] > 0 else None


# ── Registry-aware loaders ────────────────────────────────────────────────────

def _load_registry() -> Dict:
    return json.loads(REGISTRY_PATH.read_text())["workflows"]


def _candidates_for(workflow_type: str, registry: Dict) -> List[str]:
    return registry.get(workflow_type, {}).get("required_inputs", [])


# ── History → derived fields ──────────────────────────────────────────────────

_DELAY_TOKENS     = ("delayed",)
_ESCALATION_TOKENS = ("escalated", "escalation")
_BLOCKED_TOKENS   = ("blocked",)


def _derive_history(events: List[Dict]) -> Dict:
    delay_count, escalation_count = 0, 0
    last_status = None
    for ev in events:
        ev_type = (ev.get("event_type") or "").lower()
        status  = (ev.get("status")     or "").lower()
        if any(tok in ev_type for tok in _DELAY_TOKENS):
            delay_count += 1
        if any(tok in ev_type or tok in status for tok in _ESCALATION_TOKENS):
            escalation_count += 1
        if status:
            last_status = status
    return {
        "prior_delay_count":      delay_count,
        "prior_escalation_count": escalation_count,
        "last_status":            last_status,
    }


_DEP_STATUS_MAP = {
    "blocked":   "blocked",
    "escalated": "at_risk",
    "pending":   "pending",
    "complete":  "clear",
    "closed":    "clear",
    "approved":  "clear",
}


def _derive_dependency(last_status: Optional[str]) -> str:
    return _DEP_STATUS_MAP.get(last_status or "", "clear")


def _derive_workflow_state(last_status: Optional[str], case_type: str) -> str:
    """Heuristic mapping. Falls back to 'compliance_review' for review-shaped types."""
    if last_status in ("complete", "closed", "approved"):
        return "closed"
    if "review" in case_type:
        return "compliance_review"
    return "intake"


# ── Calendar → timing ─────────────────────────────────────────────────────────

def _derive_timing(events: List[Dict]) -> Dict[str, Optional[str]]:
    """Take the earliest end_time as the working SLA; latest as due_date."""
    end_times: List[str] = []
    for ev in events:
        et = ev.get("end_time")
        if et:
            end_times.append(et)
    if not end_times:
        return {"sla_deadline": None, "due_date": None}
    end_times_sorted = sorted(end_times)
    return {"sla_deadline": end_times_sorted[0], "due_date": end_times_sorted[-1]}


# ── Public: parse a packet ────────────────────────────────────────────────────

def parse_packet(packet: Dict) -> Dict:
    """Convert a CSA packet into a CaseInput-shaped dict."""
    registry  = _load_registry()
    case_type = packet.get("case_type", "")
    wf_type   = CASE_TYPE_MAP.get(case_type, case_type)

    # ── Documents ─
    candidates = _candidates_for(wf_type, registry)
    docs       = packet.get("context", {}).get("documents", [])
    received: List[str] = []
    matched_pairs: List[Tuple[str, Optional[str]]] = []
    for d in docs:
        fname = d.get("filename", "")
        doctype = identify_doctype(fname, candidates)
        matched_pairs.append((fname, doctype))
        if doctype and doctype not in received:
            received.append(doctype)

    mandatory = registry.get(wf_type, {}).get("mandatory_inputs", [])

    # ── History ─
    history = packet.get("context", {}).get("case_history", [])
    derived = _derive_history(history)

    # ── Timing ─
    timing = _derive_timing(packet.get("context", {}).get("calendar_events", []))

    # ── Validation -> operating context ─
    val_status = (packet.get("validation", {}).get("status") or "").upper()
    operating_partial = val_status not in ("COMPLETE",)

    # Stakeholder/policy flags — heuristic from case_type and warnings
    warnings_raw = packet.get("validation", {}).get("warnings") or []
    warnings = " ".join(str(w).lower() for w in warnings_raw)
    policy_flag = case_type in ("claim_review", "kyc_review", "filing_review", "contract_review")
    stakeholder_priority = "regulatory" if "regulatory" in warnings or case_type in ("kyc_review", "filing_review") \
        else "legal" if case_type == "contract_review" \
        else "standard"

    return {
        "task_id":                packet.get("case_id", packet.get("task_id", "")),
        "workflow_type":          wf_type,
        "workflow_state":         _derive_workflow_state(derived["last_status"], case_type),
        "priority":               "P1" if "urgent" in warnings or "high priority" in warnings else "P2",
        "required_inputs":        list(_candidates_for(wf_type, registry)),
        "mandatory_inputs":       list(mandatory),
        "received_inputs":        received,
        "dependency_status":      _derive_dependency(derived["last_status"]),
        "blocker_flag":           derived["last_status"] == "blocked",
        "policy_flag":            policy_flag,
        "stakeholder_priority":   stakeholder_priority,
        "prior_delay_count":      derived["prior_delay_count"],
        "prior_escalation_count": derived["prior_escalation_count"],
        "sla_deadline":           timing["sla_deadline"],
        "due_date":               timing["due_date"],
        # Side data for UI:
        "_filename_matches":      matched_pairs,
        "_operating_partial":     operating_partial,
    }


# ── Public: store of packets ──────────────────────────────────────────────────

class PacketStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or PACKETS_PATH
        self._cache: Optional[Dict] = None

    def _load(self) -> Dict:
        if self._cache is None:
            self._cache = json.loads(self.path.read_text())
        return self._cache

    def reload(self) -> None:
        self._cache = None

    def list_case_ids(self) -> List[str]:
        return list(self._load().get("packets", {}).keys())

    def get_packet(self, case_id: str) -> Optional[Dict]:
        return self._load().get("packets", {}).get(case_id)
