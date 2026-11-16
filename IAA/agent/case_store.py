"""
case_store.py
Simple file-backed case store for Project AMP.

Used by CSA and other agents to persist per-case JSON payloads
(emails, extracted fields, policy refs, etc.) so all agents can read
the same case state without spinning up an external DB.

Layout:
  data/cases/
      CASE-001.json
      CASE-002.json
      ...

Each file is a single JSON dict. Schema is free-form — whatever the
producing agent wants to store. Use case_id as the filename stem.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Optional


class CaseStore:
    """File-backed per-case JSON store. Safe against missing files."""

    def __init__(self, store_dir: str = "./data/cases"):
        self.store_dir = Path(store_dir)
        try:
            self.store_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[case_store] Warning: could not create {self.store_dir}: {e}")

    def _path(self, case_id: str) -> Path:
        # Sanitise — prevent traversal
        safe = str(case_id).replace("/", "_").replace("\\", "_")
        return self.store_dir / f"{safe}.json"

    def save_case(self, case_id: str, data: dict) -> None:
        """Write data to data/cases/{case_id}.json. Never raises."""
        try:
            path = self._path(case_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"[case_store] save_case({case_id}) failed: {e}")

    def load_case(self, case_id: str) -> Optional[dict]:
        """Return dict for case_id, or None if missing / unreadable."""
        try:
            path = self._path(case_id)
            if not path.exists():
                return None
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[case_store] load_case({case_id}) failed: {e}")
            return None

    def list_cases(self) -> list[str]:
        """Return all case IDs (filenames without .json). Empty list on error."""
        try:
            if not self.store_dir.exists():
                return []
            return sorted(p.stem for p in self.store_dir.glob("*.json"))
        except Exception as e:
            print(f"[case_store] list_cases failed: {e}")
            return []

    def update_case(self, case_id: str, updates: dict) -> dict:
        """
        Shallow-merge updates into existing case dict, save, return merged.
        Creates a new case if none exists.
        Returns the merged dict (or just the updates on save failure).
        """
        try:
            existing = self.load_case(case_id) or {}
            merged = {**existing, **updates}
            self.save_case(case_id, merged)
            return merged
        except Exception as e:
            print(f"[case_store] update_case({case_id}) failed: {e}")
            return dict(updates)

    def delete_case(self, case_id: str) -> bool:
        """Delete a case file. Returns True if deleted, False otherwise."""
        try:
            path = self._path(case_id)
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception as e:
            print(f"[case_store] delete_case({case_id}) failed: {e}")
            return False
