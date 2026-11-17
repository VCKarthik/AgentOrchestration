"""
GPA policy-document upload panel for the Streamlit demo sidebar.

The presenter uploads a policy document (PDF or markdown). It is chunked,
rule-extracted, and stored in `GPA/governance_agent.db` so the Governance
Agent can match cases against it during workflow runs.

Production mode: GPA's DB starts empty. The customer (or the demo presenter)
uploads policies that apply to *their* organisation — procurement rules,
claim thresholds, fraud SARs, HR escalation paths, etc. — and GPA's
decision_engine evaluates incoming tasks against only those rules.

Sample policy markdown files live in `data/policies/` for the demo.
"""
from __future__ import annotations

import os
import sys
from typing import Any

import streamlit as st

# ── Make GPA imports work ────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _detect_format(filename: str) -> str:
    fn = (filename or "").lower()
    if fn.endswith(".pdf"):
        return "pdf"
    if fn.endswith(".md") or fn.endswith(".markdown") or fn.endswith(".txt"):
        return "text"
    return "unknown"


def _ingest_policy(file_bytes: bytes, filename: str, policy_type: str,
                   department: str) -> tuple[bool, str, dict[str, int]]:
    """
    Insert a PolicyDocument and run chunker + rule extractor.
    Returns (ok, message, stats).

    PDFs go through GPA's existing extract_text_from_document path.
    Markdown / text bypasses the PDF extractor — text is chunked directly.
    """
    fmt = _detect_format(filename)
    if fmt == "unknown":
        return False, f"Unsupported file type: `{filename}` (use .pdf, .md, or .txt).", {}

    try:
        from GPA.db import SessionLocal, engine, Base  # type: ignore[import]
        from GPA.models import PolicyDocument, PolicyChunk, PolicyRule  # type: ignore[import]
        from GPA.chunker import chunk_text  # type: ignore[import]
        from GPA.rule_extractor import extract_rules_from_chunk  # type: ignore[import]
        from GPA.policy_pipeline import process_policy_document  # type: ignore[import]
        # _POLICIES holds hand-curated rules for the sample markdown files —
        # the rule_extractor's regex patterns don't fire on markdown table
        # syntax, so we fall back to these for known filenames.
        from GPA.seed_policies import _POLICIES  # type: ignore[import]
    except Exception as e:
        return False, f"GPA import failed: {e}", {}

    seed_lookup = {p["file_name"]: p for p in _POLICIES}

    # Make sure tables exist (no-op if they already do).
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(PolicyDocument).filter_by(file_name=filename).first()
        if existing:
            return False, f"`{filename}` is already loaded (document_id {existing.id}).", {}

        doc = PolicyDocument(
            file_name=filename,
            title=filename,
            policy_type=policy_type or "general_policy",
            department=department or "general",
            version="v1",
            file_data=file_bytes,
            source="demo_upload",
            processing_status="NEW",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id

        chunks_created = 0
        rules_created = 0

        if fmt == "pdf":
            # GPA's existing pipeline reads file_data via PdfReader and runs
            # the chunker + rule extractor end-to-end.
            try:
                process_policy_document(db, doc_id)
            except Exception as e:
                doc.processing_status = "FAILED"
                db.commit()
                return False, f"PDF processing failed: {e}", {}
            chunks_created = db.query(PolicyChunk).filter_by(document_id=doc_id).count()
            rules_created  = db.query(PolicyRule ).filter_by(document_id=doc_id).count()

        else:  # markdown / text
            try:
                text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return False, "File is not valid UTF-8 text.", {}

            chunks = chunk_text(text)
            if not chunks:
                return False, "Chunker produced no chunks (file may be empty).", {}

            # Insert chunks
            chunk_rows: list[PolicyChunk] = []
            for idx, c_text in enumerate(chunks):
                ch = PolicyChunk(
                    document_id=doc_id,
                    chunk_index=idx,
                    chunk_text=c_text,
                    section_name=None,
                )
                db.add(ch)
                chunk_rows.append(ch)
            db.flush()
            chunks_created = len(chunk_rows)
            anchor_chunk = chunk_rows[0] if chunk_rows else None

            # If this filename matches a sample seed, apply its hand-curated
            # rules — the rule_extractor's regex patterns don't fire on
            # markdown table syntax, so the seed dict is the source of truth
            # for sample markdown files.
            seed = seed_lookup.get(filename)
            if seed and anchor_chunk is not None:
                seen_keys: set[tuple] = set()
                for (
                    rule_type, subject, operator, value, unit,
                    action, condition_text, confidence, approver,
                ) in seed["rules"]:
                    key = (subject, operator, value, action)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    db.add(PolicyRule(
                        document_id=doc_id,
                        chunk_id=anchor_chunk.id,
                        rule_type=rule_type,
                        subject=subject,
                        operator=operator,
                        value=value,
                        unit=unit,
                        action=action,
                        condition_text=condition_text,
                        confidence=confidence,
                        approver=approver,
                    ))
                    rules_created += 1
                # Tag with the seed's policy_type/department so downstream
                # case_type matching works.
                doc.policy_type = seed.get("policy_type") or doc.policy_type
                doc.department = seed.get("department") or doc.department
                doc.title = seed.get("title") or doc.title
            else:
                # Unknown markdown — try the regex extractor, may or may not fire.
                seen_keys = set()
                for ch in chunk_rows:
                    try:
                        extracted = extract_rules_from_chunk(ch.chunk_text)
                    except Exception:
                        continue
                    for r in extracted or []:
                        key = (
                            ch.id,
                            r.get("subject"),
                            r.get("operator"),
                            r.get("value"),
                            r.get("action"),
                        )
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        db.add(PolicyRule(
                            document_id=doc_id,
                            chunk_id=ch.id,
                            rule_type=r.get("rule_type", "unspecified"),
                            subject=r.get("subject", ""),
                            operator=r.get("operator", ""),
                            value=r.get("value", ""),
                            unit=r.get("unit"),
                            action=r.get("action", ""),
                            condition_text=r.get("condition_text", ""),
                            confidence=r.get("confidence", 0.5),
                            approver=r.get("approver"),
                        ))
                        rules_created += 1

            doc.processing_status = "PROCESSED"
            db.commit()

        # Track upload for the reset button
        log = st.session_state.setdefault("uploaded_policy_doc_ids", [])
        log.append(doc_id)

        msg = (
            f"Loaded **`{filename}`** — {chunks_created} chunks, "
            f"{rules_created} rules extracted."
        )
        return True, msg, {"chunks": chunks_created, "rules": rules_created, "doc_id": doc_id}

    finally:
        db.close()


def _summarize_gpa_db() -> dict[str, int] | None:
    """Return {documents, chunks, rules} or None if GPA is unavailable."""
    try:
        from GPA.db import SessionLocal  # type: ignore[import]
        from GPA.models import PolicyDocument, PolicyChunk, PolicyRule  # type: ignore[import]
    except Exception:
        return None
    db = SessionLocal()
    try:
        return {
            "documents": db.query(PolicyDocument).count(),
            "chunks":    db.query(PolicyChunk).count(),
            "rules":     db.query(PolicyRule).count(),
        }
    except Exception:
        return None
    finally:
        db.close()


def _list_loaded_policies() -> list[tuple[int, str, str, int, int]]:
    """[(doc_id, file_name, policy_type, n_chunks, n_rules), ...]"""
    try:
        from GPA.db import SessionLocal  # type: ignore[import]
        from GPA.models import PolicyDocument, PolicyChunk, PolicyRule  # type: ignore[import]
    except Exception:
        return []
    db = SessionLocal()
    try:
        out: list[tuple[int, str, str, int, int]] = []
        for d in db.query(PolicyDocument).order_by(PolicyDocument.id.desc()).all():
            n_chunks = db.query(PolicyChunk).filter_by(document_id=d.id).count()
            n_rules  = db.query(PolicyRule ).filter_by(document_id=d.id).count()
            out.append((d.id, d.file_name, d.policy_type or "general", n_chunks, n_rules))
        return out
    finally:
        db.close()


def _reset_gpa_db() -> dict[str, int]:
    """
    Full reset of the GPA database. Wipes documents, chunks, rules, decisions,
    and the incoming-task log. Schema is preserved.
    """
    try:
        from GPA.db import SessionLocal  # type: ignore[import]
        from GPA.models import (  # type: ignore[import]
            PolicyDocument, PolicyChunk, PolicyRule,
        )
        # Optional tables that may or may not exist depending on GPA version
        try:
            from GPA.models import GovernanceDecision  # type: ignore[import]
        except Exception:
            GovernanceDecision = None  # type: ignore[assignment]
        try:
            from GPA.models import IncomingTask  # type: ignore[import]
        except Exception:
            IncomingTask = None  # type: ignore[assignment]
    except Exception:
        return {}

    db = SessionLocal()
    counts: dict[str, int] = {}
    try:
        # Order: rules → chunks → docs (FK ordering safety)
        counts["rules"]     = db.query(PolicyRule).delete()
        counts["chunks"]    = db.query(PolicyChunk).delete()
        if GovernanceDecision is not None:
            counts["decisions"] = db.query(GovernanceDecision).delete()
        if IncomingTask is not None:
            counts["tasks"]     = db.query(IncomingTask).delete()
        counts["documents"] = db.query(PolicyDocument).delete()
        db.commit()
    finally:
        db.close()

    st.session_state["uploaded_policy_doc_ids"] = []
    st.session_state["policy_loaded_files"] = set()
    return counts


# ── Public renderer ──────────────────────────────────────────────────────────

def render_sidebar_panel() -> None:
    """Render the GPA policy upload panel inside the sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Policy Documents")
    st.sidebar.caption(
        "Upload your organisation's policies. GPA matches each case against "
        "these rules during the workflow."
    )

    # Sample files live in `data/cases/<CASE-ID>-<workflow>/<original-filename>.md`
    # The original filename (e.g. procurement.md, claims.md) is preserved so
    # GPA's curated-rules lookup in seed_policies._POLICIES still matches.
    cases_root = os.path.join(_REPO_ROOT, "data", "cases")
    if os.path.isdir(cases_root):
        with st.sidebar.expander("Sample policy files"):
            for case_dir in sorted(os.listdir(cases_root)):
                case_full = os.path.join(cases_root, case_dir)
                if not os.path.isdir(case_full):
                    continue
                for fname in sorted(os.listdir(case_full)):
                    if fname.endswith((".md", ".pdf", ".txt")):
                        st.markdown(f"- `data/cases/{case_dir}/{fname}`")
            st.caption("Drag any of these into the uploader below.")

    uploaded = st.sidebar.file_uploader(
        "Upload policy",
        type=["pdf", "md", "txt"],
        key="policy_uploader",
        label_visibility="collapsed",
    )

    # Tag fields — let presenter set policy_type / department
    if uploaded is not None:
        col_a, col_b = st.sidebar.columns(2)
        policy_type = col_a.text_input(
            "Type",
            value=st.session_state.get("policy_type_default", "general_policy"),
            key="policy_type_input",
        )
        department = col_b.text_input(
            "Dept",
            value=st.session_state.get("policy_dept_default", "general"),
            key="policy_dept_input",
        )

        loaded = st.session_state.setdefault("policy_loaded_files", set())
        if uploaded.name not in loaded:
            ok, msg, stats = _ingest_policy(
                uploaded.read(), uploaded.name, policy_type, department
            )
            if ok:
                st.sidebar.success(msg)
                loaded.add(uploaded.name)
            else:
                st.sidebar.error(msg)

    # ── Reset button ─────────────────────────────────────────────────────────
    summary = _summarize_gpa_db()
    has_anything = bool(summary and summary.get("documents", 0) > 0)
    if has_anything:
        if st.sidebar.button(
            "Reset GPA database",
            width='stretch',
            key="reset_gpa_btn",
            help="Clears all policy documents, chunks, rules, and decisions.",
        ):
            counts = _reset_gpa_db()
            st.sidebar.warning(
                f"Reset: {counts.get('documents', 0)} docs, "
                f"{counts.get('chunks', 0)} chunks, "
                f"{counts.get('rules', 0)} rules cleared."
            )
            st.rerun()

    # ── Current GPA DB content ───────────────────────────────────────────────
    if summary and summary.get("documents", 0) > 0:
        with st.sidebar.expander("GPA DB now contains", expanded=False):
            st.markdown(
                f"**{summary['documents']} documents · "
                f"{summary['chunks']} chunks · "
                f"{summary['rules']} rules**"
            )
            st.markdown("")
            for doc_id, name, ptype, nc, nr in _list_loaded_policies():
                st.markdown(
                    f"- `{name}` _({ptype})_ — **{nc}** chunks, **{nr}** rules"
                )
    elif summary is not None:
        st.sidebar.caption("_GPA DB is empty — upload a policy to begin._")
    else:
        st.sidebar.caption("_GPA module unavailable._")
