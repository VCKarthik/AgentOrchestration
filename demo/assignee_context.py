"""
DA team-roster upload panel for the Streamlit demo sidebar.

The presenter uploads a JSON describing the customer's team — names, roles,
skills, departments, current workloads. DA's `AssigneeRepository` picks this
up automatically on the next `/predict` call (the agent is instantiated fresh
per request, so no DA restart is needed).

Production mode: in real deployment, the customer would feed their HR
system or org chart through this same JSON shape (or a connector that
produces it).

Schema (matches DA Assignee model exactly):

    {
      "metadata": { "description": "...", "version": "1.0" },
      "assignees": [
        { "assignee_id": "EMP-001", "name": "...", "role": "...",
          "department": "...", "skills": [{"skill": "...", "proficiency": 90}],
          "business_domains": [...], "capacity_limit": 10,
          "current_workload": 2, "active_tasks_count": 2,
          "utilization_percent": 20.0, "availability_status": "available",
          "escalation_authority": false, "performance_score": 85.0, ... }
      ]
    }

Sample roster lives at `data/assignee_rosters/sample_roster.json` (9 employees
mirroring the previous hardcoded set — preserves Suyash's load-balancer demo).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st

# ── Make DA imports work ─────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _active_roster_path() -> Path:
    """The path DA's repository reads from. Stays in sync with DA's source."""
    try:
        from DA.delegation_agent.repositories.assignee_repository import (  # type: ignore[import]
            get_active_roster_path,
        )
        return get_active_roster_path()
    except Exception:
        # Fallback: hardcoded path — must match assignee_repository.py
        return _REPO_ROOT / "data" / "assignee_rosters" / "active_roster.json"


def _validate_payload(payload: Any) -> tuple[bool, str, list[dict]]:
    """Validate the uploaded JSON, return (ok, message, normalized_assignees)."""
    if not isinstance(payload, dict):
        return False, "Top level must be a JSON object.", []
    assignees = payload.get("assignees")
    if not isinstance(assignees, list):
        return False, "JSON must contain an `assignees` array.", []

    # Validate each assignee against the Assignee Pydantic model
    try:
        from DA.delegation_agent.models.assignee import Assignee  # type: ignore[import]
    except Exception as e:
        return False, f"DA model import failed: {e}", []

    normalized: list[dict] = []
    errors: list[str] = []
    for i, raw in enumerate(assignees):
        try:
            a = Assignee(**raw)
            normalized.append(a.model_dump(mode="json"))
        except Exception as exc:
            errors.append(
                f"Row {i} ({raw.get('assignee_id', '<no-id>')}): {exc}"
            )

    if errors and not normalized:
        return False, "All assignees failed validation:\n• " + "\n• ".join(errors[:5]), []
    if errors:
        return (
            True,
            f"Loaded {len(normalized)} assignees ({len(errors)} skipped, see log).",
            normalized,
        )
    return True, f"Loaded {len(normalized)} assignees.", normalized


def _write_active_roster(assignees: list[dict], metadata: dict | None = None) -> Path:
    """Persist the active roster JSON. Creates parent dir if missing."""
    path = _active_roster_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": metadata or {"source": "demo_upload"},
        "assignees": assignees,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def _read_active_roster() -> list[dict]:
    path = _active_roster_path()
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("assignees") or []
    except Exception:
        return []


def _reset_active_roster() -> bool:
    """Delete the active roster file. Returns True if a file was removed."""
    path = _active_roster_path()
    if path.exists():
        path.unlink()
        return True
    return False


# ── Public renderer ──────────────────────────────────────────────────────────

def render_sidebar_panel() -> None:
    """Render the DA team-roster upload panel inside the sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Team Roster")
    st.sidebar.caption(
        "Upload your team's employees. DA scores and assigns each task to the "
        "best-fit available person."
    )

    sample_path = _REPO_ROOT / "data" / "assignee_rosters"
    if sample_path.is_dir():
        with st.sidebar.expander("Sample roster"):
            samples = sorted(
                f.name for f in sample_path.iterdir()
                if f.suffix == ".json" and f.name != "active_roster.json"
            )
            for s in samples:
                st.markdown(f"- `data/assignee_rosters/{s}`")
            st.caption("Drag any of these into the uploader below.")

    uploaded = st.sidebar.file_uploader(
        "Upload team roster JSON",
        type=["json"],
        key="roster_uploader",
        label_visibility="collapsed",
    )

    if uploaded is not None and uploaded.name not in st.session_state.get(
        "roster_loaded_files", set()
    ):
        try:
            payload = json.load(uploaded)
        except json.JSONDecodeError as e:
            st.sidebar.error(f"Invalid JSON: {e}")
        else:
            ok, msg, assignees = _validate_payload(payload)
            if ok:
                metadata = payload.get("metadata") or {}
                metadata["source"] = "demo_upload"
                metadata["original_filename"] = uploaded.name
                _write_active_roster(assignees, metadata=metadata)
                st.sidebar.success(msg)
                loaded = st.session_state.setdefault("roster_loaded_files", set())
                loaded.add(uploaded.name)
            else:
                st.sidebar.error(msg)

    # ── Reset button ─────────────────────────────────────────────────────────
    current = _read_active_roster()
    if current:
        if st.sidebar.button(
            "Reset team roster",
            width='stretch',
            key="reset_roster_btn",
            help="Removes the active roster — DA will have no assignees until "
                 "a new roster is uploaded.",
        ):
            removed = _reset_active_roster()
            st.session_state["roster_loaded_files"] = set()
            if removed:
                st.sidebar.warning("Roster cleared. DA has no assignees now.")
            st.rerun()

    # ── Current roster summary ───────────────────────────────────────────────
    if current:
        with st.sidebar.expander(
            f"DA roster ({len(current)} people)", expanded=False
        ):
            # Aggregate by department
            by_dept: dict[str, int] = {}
            avail_count = 0
            for a in current:
                dept = a.get("department") or "—"
                by_dept[dept] = by_dept.get(dept, 0) + 1
                if (a.get("availability_status") or "").lower() == "available":
                    avail_count += 1
            st.markdown(f"**{avail_count}/{len(current)} available**")
            st.markdown("")
            for d, n in sorted(by_dept.items(), key=lambda x: -x[1]):
                st.markdown(f"- `{d}` — **{n}** people")
            with st.expander("Names"):
                for a in current:
                    util = a.get("utilization_percent", 0)
                    status = a.get("availability_status", "")
                    st.markdown(
                        f"- `{a.get('assignee_id', '?')}` "
                        f"**{a.get('name', '?')}** "
                        f"({a.get('role', '?')}) — {util:.0f}% util · {status}"
                    )
    else:
        st.sidebar.caption(
            "_No roster loaded — DA will return escalations until you upload._"
        )
