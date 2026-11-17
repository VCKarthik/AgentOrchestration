# `data/cases/` — Demo case bundles

One folder per workflow. Each folder is a **self-contained bundle** of
everything that case needs to run end-to-end through the AMP pipeline.

Currently bundled cases:

| Folder | Workflow | Headline |
|---|---|---|
| [`CASE-1001-vendor-onboarding/`](CASE-1001-vendor-onboarding/) | `vendor_onboarding` | TechSupply Inc. — insurance certificate missing, NDA pending |
| [`CASE-2001-interview-scheduling/`](CASE-2001-interview-scheduling/) | `interview_scheduling` | Sarah Johnson — background check pending, conflict of interest with prior employer |
| [`CASE-3001-claim-review/`](CASE-3001-claim-review/) | `claim_review` | David Kim — $1,200 medical claim, all documents verified |

## What's inside each folder

| File | Used by | Purpose |
|---|---|---|
| `intake.json` | `demo/app.py` (Case Queue) | The 12-field task intake — what kicks off the workflow |
| `<workflow>.md` (e.g. `procurement.md`, `claims.md`, `interview_scheduling.md`) | GPA — uploaded via the **Policy Documents** sidebar panel | Markdown policy doc for this workflow's domain. Original filename is preserved so `GPA/seed_policies._POLICIES` curated-rule lookup still matches |
| `workflow_context.json` | SWA — uploaded via the **Workflow Context** sidebar panel | Past cases + activity events, used as backdrop for SWA's pattern mining |
| `csa_seed.json` | CSA — already pre-loaded into `CSA/data/csa.db` by `infra/seed_csa_db.py` | Emails, documents, calendar events, case history that CSA returns when this `case_id` is queried. The JSON here is a copy for reference; the live data lives in the SQLite DB. |

## Demo flow per case

For any one of the three cases:

1. Open the dashboard at http://localhost:8501
2. Sidebar → **Workflow Context** → upload `workflow_context.json` from this folder
3. Sidebar → **Policy Documents** → upload the `<workflow>.md` file from this folder
4. Sidebar → **Team Roster** → upload `data/assignee_rosters/sample_roster.json` (shared across all three cases)
5. Click the case in the Case Queue → **Run Workflow**

CSA reads its source data straight from `CSA/data/csa.db` (no upload step
needed) — the records originate from `infra/seed_csa_db.py`, which is the
source of truth. The `csa_seed.json` file in each folder is a human-readable
mirror of that data.

## Adding a fourth workflow

1. Pick a case ID and a `case_type` (e.g. `CASE-4001-payroll-review`)
2. Create `data/cases/CASE-4001-payroll-review/` and add the four files listed above
3. Append a row to `DEMO_CASES` in `demo/app.py`
4. Append the email/document/calendar/case_history rows to `infra/seed_csa_db.py`
5. Add a corresponding entry to `_POLICIES` in `GPA/seed_policies.py` so markdown rule extraction works
6. Re-run `python3 -m infra.init_all` (idempotent)

That's the entire surface needed to bring up a new workflow.
