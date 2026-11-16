import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "../data/csa.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS emails (
        id TEXT PRIMARY KEY, case_id TEXT NOT NULL, case_type TEXT NOT NULL,
        subject TEXT, sender TEXT, recipients TEXT, date TEXT, body TEXT,
        attachments TEXT, thread_id TEXT, file_path TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, case_id TEXT NOT NULL, case_type TEXT NOT NULL,
        filename TEXT, file_type TEXT, description TEXT,
        tags TEXT, created_at TEXT, file_path TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS calendar_events (
        id TEXT PRIMARY KEY, case_id TEXT NOT NULL, case_type TEXT NOT NULL,
        title TEXT, start_time TEXT, end_time TEXT, attendees TEXT,
        location TEXT, description TEXT, status TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS case_history (
        id TEXT PRIMARY KEY, case_id TEXT NOT NULL, case_type TEXT NOT NULL,
        event_type TEXT, actor TEXT, timestamp TEXT, notes TEXT, status TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS query_runs (
        run_id TEXT PRIMARY KEY, case_id TEXT, case_type TEXT,
        task_query TEXT, timestamp TEXT, output_path TEXT,
        total_sources INTEGER, confidence REAL
    )""")
    conn.commit()
    _seed_data(conn)
    conn.close()
    print("[DB] Initialized at", DB_PATH)

def _seed_data(conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM emails")
    if c.fetchone()[0] > 0:
        return

    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/files"))

    emails = [
        ("E001","CASE-1001","claim_review",
         "Policy #4821 - Initial Claim Submission",
         "john.doe@insurer.com","claims@insurer.com","2026-03-10 09:15:00",
         "Dear team, please find attached the initial claim for policy #4821. Water damage to property on March 5th.",
         "claim_form_4821.pdf,photos_damage.zip","THREAD-001",
         f"{base}/emails/E001_claim_submission.txt"),
        ("E002","CASE-1001","claim_review",
         "Re: Policy #4821 - Missing Documentation",
         "adjuster.smith@insurer.com","john.doe@insurer.com","2026-03-12 14:30:00",
         "We need the plumber invoice and repair estimate before we can proceed.",
         "","THREAD-001",f"{base}/emails/E002_missing_docs.txt"),
        ("E003","CASE-1001","claim_review",
         "Re: Policy #4821 - Documents Submitted",
         "john.doe@insurer.com","adjuster.smith@insurer.com","2026-03-15 11:00:00",
         "Please find the plumber invoice and repair estimate attached.",
         "plumber_invoice.pdf,repair_estimate.pdf","THREAD-001",
         f"{base}/emails/E003_docs_submitted.txt"),
        ("E004","CASE-2002","policy_renewal",
         "Policy #7734 - Renewal Notice",
         "renewals@insurer.com","alice.wang@client.com","2026-02-20 08:00:00",
         "Your policy #7734 is due for renewal on April 1st. Premium: $1,240/year.",
         "renewal_quote_7734.pdf","THREAD-002",
         f"{base}/emails/E004_renewal_notice.txt"),
        ("E005","CASE-2002","policy_renewal",
         "Re: Policy #7734 - Renewal Query",
         "alice.wang@client.com","renewals@insurer.com","2026-02-22 10:45:00",
         "Can you clarify what changed from last year regarding the premium increase?",
         "","THREAD-002",f"{base}/emails/E005_renewal_query.txt"),
        ("E006","CASE-3003","fraud_investigation",
         "ALERT: Suspicious Claim Pattern - Policy #9910",
         "fraud.team@insurer.com","investigation@insurer.com","2026-03-01 16:20:00",
         "Policy #9910 has submitted 3 claims in 6 months all involving theft. Escalating.",
         "fraud_flag_report.pdf","THREAD-003",
         f"{base}/emails/E006_fraud_alert.txt"),
    ]
    c.executemany("""INSERT INTO emails
        (id,case_id,case_type,subject,sender,recipients,date,body,attachments,thread_id,file_path)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", emails)

    documents = [
        ("D001","CASE-1001","claim_review","policy_4821.pdf","pdf",
         "Original property insurance policy #4821","policy,property,insurance",
         "2025-01-15",f"{base}/documents/policy_4821.pdf"),
        ("D002","CASE-1001","claim_review","claim_form_4821.pdf","pdf",
         "Completed claim form water damage","claim,form,water_damage",
         "2026-03-10",f"{base}/documents/claim_form_4821.pdf"),
        ("D003","CASE-1001","claim_review","plumber_invoice.pdf","pdf",
         "Invoice from licensed plumber","invoice,repair,plumber",
         "2026-03-14",f"{base}/documents/plumber_invoice.pdf"),
        ("D004","CASE-1001","claim_review","repair_estimate.pdf","pdf",
         "Property repair estimate from contractor","estimate,repair",
         "2026-03-14",f"{base}/documents/repair_estimate.pdf"),
        ("D005","CASE-2002","policy_renewal","renewal_quote_7734.pdf","pdf",
         "Annual renewal quote with premium breakdown","renewal,quote,premium",
         "2026-02-20",f"{base}/documents/renewal_quote_7734.pdf"),
        ("D006","CASE-2002","policy_renewal","policy_7734_current.pdf","pdf",
         "Current active policy for #7734","policy,active,renewal",
         "2025-04-01",f"{base}/documents/policy_7734_current.pdf"),
        ("D007","CASE-3003","fraud_investigation","fraud_flag_report.pdf","pdf",
         "Fraud flag report with pattern analysis","fraud,flag,investigation",
         "2026-03-01",f"{base}/documents/fraud_flag_report.pdf"),
        ("D008","CASE-3003","fraud_investigation","claims_history_9910.xlsx","xlsx",
         "Claims history for policy #9910 over 24 months","history,claims",
         "2026-03-01",f"{base}/documents/claims_history_9910.xlsx"),
    ]
    c.executemany("""INSERT INTO documents
        (id,case_id,case_type,filename,file_type,description,tags,created_at,file_path)
        VALUES (?,?,?,?,?,?,?,?,?)""", documents)

    events = [
        ("EV001","CASE-1001","claim_review","Claim Adjuster Review - Policy #4821",
         "2026-03-18 10:00:00","2026-03-18 11:00:00",
         "adjuster.smith@insurer.com,john.doe@insurer.com",
         "Conference Room B / Zoom",
         "Initial adjuster review meeting for water damage claim.","confirmed"),
        ("EV002","CASE-1001","claim_review","Site Inspection - Policy #4821",
         "2026-03-22 09:00:00","2026-03-22 12:00:00",
         "inspector.jones@insurer.com,john.doe@insurer.com",
         "123 Oak Street Buffalo NY","On-site property inspection.","confirmed"),
        ("EV003","CASE-2002","policy_renewal","Policy Renewal Discussion - Alice Wang",
         "2026-03-05 14:00:00","2026-03-05 14:30:00",
         "renewals@insurer.com,alice.wang@client.com",
         "Phone Call","Discuss premium increase for policy #7734.","confirmed"),
        ("EV004","CASE-3003","fraud_investigation","Fraud Investigation Kickoff",
         "2026-03-08 09:00:00","2026-03-08 10:30:00",
         "fraud.team@insurer.com,investigation@insurer.com,legal@insurer.com",
         "Investigation Room","Review fraud flag and establish investigation plan.","confirmed"),
    ]
    c.executemany("""INSERT INTO calendar_events
        (id,case_id,case_type,title,start_time,end_time,attendees,location,description,status)
        VALUES (?,?,?,?,?,?,?,?,?,?)""", events)

    history = [
        ("H001","CASE-1001","claim_review","created","system","2026-03-10 09:00:00",
         "Case created upon receipt of initial claim for policy #4821.","open"),
        ("H002","CASE-1001","claim_review","updated","adjuster.smith@insurer.com","2026-03-12 14:30:00",
         "Requested additional docs: plumber invoice and repair estimate.","pending"),
        ("H003","CASE-1001","claim_review","updated","john.doe@insurer.com","2026-03-15 11:00:00",
         "Client submitted requested documents. Ready for review.","open"),
        ("H004","CASE-1001","claim_review","reviewed","adjuster.smith@insurer.com","2026-03-18 11:00:00",
         "Documents verified. Site inspection scheduled for March 22nd.","pending"),
        ("H005","CASE-2002","policy_renewal","created","system","2026-02-20 08:00:00",
         "Renewal notice issued. Deadline April 1st.","open"),
        ("H006","CASE-2002","policy_renewal","updated","alice.wang@client.com","2026-02-22 10:45:00",
         "Client queried premium increase. Awaiting clarification.","pending"),
        ("H007","CASE-3003","fraud_investigation","created","fraud.team@insurer.com","2026-03-01 16:20:00",
         "Fraud flag triggered. 3 theft claims in 6 months.","open"),
        ("H008","CASE-3003","fraud_investigation","escalated","investigation@insurer.com","2026-03-08 10:30:00",
         "Escalated to full investigation. Legal team engaged.","escalated"),
    ]
    c.executemany("""INSERT INTO case_history
        (id,case_id,case_type,event_type,actor,timestamp,notes,status)
        VALUES (?,?,?,?,?,?,?,?)""", history)

    conn.commit()
    print("[DB] Seed data inserted.")
    _seed_demo_cases(conn)


def _seed_demo_cases(conn):
    """Seed demo case data for all 6 UI demo cases. Uses INSERT OR IGNORE — safe to re-run."""
    c = conn.cursor()
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/files"))

    emails = [
        # CASE-VND-001 — vendor_onboarding
        ("VE001","CASE-VND-001","vendor_onboarding",
         "Acme Corp — Vendor Application Submitted",
         "acme.procurement@acmecorp.com","vendor.review@company.com","2026-04-02 09:00:00",
         "Please find attached our completed vendor application package including signed agreement, insurance certificate, and W-9.",
         '["signed_vendor_agreement.pdf","certificate_of_insurance.pdf","w9_form.pdf"]',
         "VTHREAD-001",f"{base}/emails/VE001_acme_application.txt"),
        ("VE002","CASE-VND-001","vendor_onboarding",
         "Re: Acme Corp — Background Check Initiated",
         "vendor.review@company.com","acme.procurement@acmecorp.com","2026-04-04 14:00:00",
         "Thank you. We have initiated the background and financial standing check. Expect 3–5 business days.",
         "[]","VTHREAD-001",f"{base}/emails/VE002_acme_background.txt"),
        ("VE003","CASE-VND-001","vendor_onboarding",
         "Re: Acme Corp — CFO Approval Required",
         "vendor.review@company.com","cfo@company.com","2026-04-07 10:30:00",
         "Acme Corp vendor contract value is $150,000. Per procurement policy, CFO sign-off is required before onboarding.",
         "[]","VTHREAD-001",f"{base}/emails/VE003_acme_cfo.txt"),
        # CASE-CLM-002 — claim_review
        ("CE001","CASE-CLM-002","claim_review",
         "Claim #INV-2024-089 — Initial Submission",
         "policyholder.nguyen@email.com","claims@company.com","2026-03-20 08:45:00",
         "Submitting claim for property damage on 2024-11-15. Damage to roof and water intrusion. All repair receipts attached.",
         '["claim_form_INV-2024-089.pdf","repair_receipts.pdf"]',
         "CTHREAD-002",f"{base}/emails/CE001_claim_submission.txt"),
        ("CE002","CASE-CLM-002","claim_review",
         "Re: Claim #INV-2024-089 — Adjuster Assigned",
         "claims@company.com","policyholder.nguyen@email.com","2026-03-22 11:00:00",
         "Adjuster Martinez has been assigned. A medical report and independent contractor estimate are required.",
         "[]","CTHREAD-002",f"{base}/emails/CE002_adjuster_assigned.txt"),
        ("CE003","CASE-CLM-002","claim_review",
         "Re: Claim #INV-2024-089 — Documents Received",
         "policyholder.nguyen@email.com","claims@company.com","2026-03-25 15:30:00",
         "Please find the medical report and independent contractor estimate attached.",
         '["medical_report.pdf","adjuster_notes.pdf"]',
         "CTHREAD-002",f"{base}/emails/CE003_claim_docs.txt"),
        # CASE-FRD-003 — fraud_investigation
        ("FE001","CASE-FRD-003","fraud_investigation",
         "ALERT: Fraud Pattern Detected — Policy #FRD-2024-112",
         "fraud.monitor@company.com","fraud.team@company.com","2026-04-01 07:00:00",
         "Automated monitoring has flagged three suspicious transactions totalling $12,000. Mismatched claimant IDs and rapid escalation pattern detected.",
         '["fraud_alert_FRD-2024-112.pdf","transaction_log.xlsx"]',
         "FTHREAD-003",f"{base}/emails/FE001_fraud_alert.txt"),
        ("FE002","CASE-FRD-003","fraud_investigation",
         "Re: Policy #FRD-2024-112 — Investigation Opened",
         "fraud.team@company.com","compliance@company.com","2026-04-01 09:30:00",
         "Full investigation opened. Legal and Compliance team engaged. SAR filing being prepared.",
         "[]","FTHREAD-003",f"{base}/emails/FE002_investigation_open.txt"),
        # CASE-CMP-004 — compliance_review
        ("ME001","CASE-CMP-004","compliance_review",
         "Annual GDPR Audit — EU Data Ops (2026)",
         "legal.team@company.com","dpo@company.com","2026-03-15 09:00:00",
         "Initiating annual GDPR audit for all EU data processing activities. Please confirm data flow inventory is up to date.",
         '["gdpr_audit_checklist.pdf"]',"MTHREAD-004",
         f"{base}/emails/ME001_gdpr_initiation.txt"),
        ("ME002","CASE-CMP-004","compliance_review",
         "Re: GDPR Audit — Data Flow Diagram Submitted",
         "dpo@company.com","legal.team@company.com","2026-03-18 14:00:00",
         "Updated data flow diagram attached. No new third-party processors added this year.",
         '["data_flow_diagram.pdf"]',"MTHREAD-004",
         f"{base}/emails/ME002_gdpr_dfd.txt"),
        # CASE-CLA-005 — claim_processing
        ("LA001","CASE-CLA-005","claim_processing",
         "Auto Claim — Policy #AC-7721 Submitted",
         "policyholder.jones@email.com","claims@company.com","2026-04-10 10:00:00",
         "Submitting routine auto collision claim. Incident on April 8th. All documentation complete including repair estimate and photos.",
         '["claim_form_AC-7721.pdf","collision_photos.pdf","repair_estimate.pdf"]',
         "LTHREAD-005",f"{base}/emails/LA001_auto_claim.txt"),
        ("LA002","CASE-CLA-005","claim_processing",
         "Re: Policy #AC-7721 — Documentation Complete",
         "claims@company.com","policyholder.jones@email.com","2026-04-10 14:00:00",
         "All documents received. Claim is within policy limits. Processing for straight-through approval.",
         "[]","LTHREAD-005",f"{base}/emails/LA002_auto_claim_ack.txt"),
        # CASE-DOC-006 — document_review
        ("DE001","CASE-DOC-006","document_review",
         "Q2 Supplier Contract Review — Initiated",
         "legal.ops@company.com","procurement@company.com","2026-04-05 09:00:00",
         "Initiating quarterly review of 12 supplier contracts. Please share the consolidated contract bundle and current procurement policy.",
         '["supplier_contracts_q2.pdf"]',"DTHREAD-006",
         f"{base}/emails/DE001_contract_review.txt"),
        ("DE002","CASE-DOC-006","document_review",
         "Re: Q2 Contract Review — Conflicts Identified",
         "procurement@company.com","legal.ops@company.com","2026-04-08 11:30:00",
         "Three contracts contain clauses that conflict with the updated procurement policy. Conflict summary attached.",
         '["policy_conflict_summary.pdf"]',"DTHREAD-006",
         f"{base}/emails/DE002_conflicts_found.txt"),
    ]

    documents = [
        # CASE-VND-001
        ("VD001","CASE-VND-001","vendor_onboarding","signed_vendor_agreement.pdf","pdf",
         "Executed master vendor agreement — Acme Corp","vendor,agreement,contract",
         "2026-04-02",f"{base}/documents/CASE-VND-001/signed_vendor_agreement.pdf"),
        ("VD002","CASE-VND-001","vendor_onboarding","certificate_of_insurance.pdf","pdf",
         "Certificate of insurance — $2M general liability","insurance,certificate",
         "2026-04-02",f"{base}/documents/CASE-VND-001/certificate_of_insurance.pdf"),
        ("VD003","CASE-VND-001","vendor_onboarding","w9_form.pdf","pdf",
         "IRS W-9 form — Acme Corp tax identification","w9,tax,vendor",
         "2026-04-02",f"{base}/documents/CASE-VND-001/w9_form.pdf"),
        # CASE-CLM-002
        ("CD001","CASE-CLM-002","claim_review","claim_form_INV-2024-089.pdf","pdf",
         "Completed claim form for property damage claim","claim,form,property",
         "2026-03-20",f"{base}/documents/CASE-CLM-002/claim_form_INV-2024-089.pdf"),
        ("CD002","CASE-CLM-002","claim_review","medical_report.pdf","pdf",
         "Medical report from treating physician","medical,report,injury",
         "2026-03-25",f"{base}/documents/CASE-CLM-002/medical_report.pdf"),
        ("CD003","CASE-CLM-002","claim_review","adjuster_notes.pdf","pdf",
         "Independent contractor damage estimate","estimate,damage,repair",
         "2026-03-25",f"{base}/documents/CASE-CLM-002/adjuster_notes.pdf"),
        # CASE-FRD-003
        ("FD001","CASE-FRD-003","fraud_investigation","fraud_alert_FRD-2024-112.pdf","pdf",
         "Automated fraud flag report with pattern analysis","fraud,alert,pattern",
         "2026-04-01",f"{base}/documents/CASE-FRD-003/fraud_alert_FRD-2024-112.pdf"),
        ("FD002","CASE-FRD-003","fraud_investigation","transaction_log.xlsx","xlsx",
         "Full transaction log for flagged policy","transactions,log,history",
         "2026-04-01",f"{base}/documents/CASE-FRD-003/transaction_log.xlsx"),
        ("FD003","CASE-FRD-003","fraud_investigation","witness_statement.pdf","pdf",
         "Witness statement collected during initial inquiry","witness,statement",
         "2026-04-02",f"{base}/documents/CASE-FRD-003/witness_statement.pdf"),
        # CASE-CMP-004
        ("MD001","CASE-CMP-004","compliance_review","gdpr_audit_checklist.pdf","pdf",
         "Annual GDPR compliance checklist — EU data ops","gdpr,compliance,audit",
         "2026-03-15",f"{base}/documents/CASE-CMP-004/gdpr_audit_checklist.pdf"),
        ("MD002","CASE-CMP-004","compliance_review","data_flow_diagram.pdf","pdf",
         "Updated EU data flow diagram 2026","gdpr,data_flow,diagram",
         "2026-03-18",f"{base}/documents/CASE-CMP-004/data_flow_diagram.pdf"),
        # CASE-CLA-005
        ("LD001","CASE-CLA-005","claim_processing","claim_form_AC-7721.pdf","pdf",
         "Auto collision claim form — Policy AC-7721","claim,auto,collision",
         "2026-04-10",f"{base}/documents/CASE-CLA-005/claim_form_AC-7721.pdf"),
        ("LD002","CASE-CLA-005","claim_processing","collision_photos.pdf","pdf",
         "Photo documentation of vehicle collision damage","photos,collision,damage",
         "2026-04-10",f"{base}/documents/CASE-CLA-005/collision_photos.pdf"),
        ("LD003","CASE-CLA-005","claim_processing","repair_estimate.pdf","pdf",
         "Certified repair shop estimate — $1,800","estimate,repair,auto",
         "2026-04-10",f"{base}/documents/CASE-CLA-005/repair_estimate.pdf"),
        # CASE-DOC-006
        ("DD001","CASE-DOC-006","document_review","supplier_contracts_q2.pdf","pdf",
         "Consolidated Q2 supplier contract bundle — 12 agreements","contracts,supplier,q2",
         "2026-04-05",f"{base}/documents/CASE-DOC-006/supplier_contracts_q2.pdf"),
        ("DD002","CASE-DOC-006","document_review","policy_conflict_summary.pdf","pdf",
         "Summary of clauses conflicting with updated procurement policy","conflict,policy,legal",
         "2026-04-08",f"{base}/documents/CASE-DOC-006/policy_conflict_summary.pdf"),
    ]

    calendar_events = [
        ("VEV001","CASE-VND-001","vendor_onboarding","Acme Corp Vendor Review Meeting",
         "2026-04-09 10:00:00","2026-04-09 11:00:00",
         "vendor.review@company.com,cfo@company.com,acme.procurement@acmecorp.com",
         "Board Room A","Review Acme Corp vendor package and CFO sign-off.","confirmed"),
        ("CEV001","CASE-CLM-002","claim_review","Adjuster Site Visit — Claim #INV-2024-089",
         "2026-03-28 09:00:00","2026-03-28 12:00:00",
         "adjuster.martinez@company.com,policyholder.nguyen@email.com",
         "45 Elm Street, Denver CO","On-site property damage assessment.","confirmed"),
        ("FEV001","CASE-FRD-003","fraud_investigation","Fraud Investigation Kickoff — Policy #FRD-2024-112",
         "2026-04-02 09:00:00","2026-04-02 10:30:00",
         "fraud.team@company.com,compliance@company.com,legal@company.com",
         "Investigation Suite","Establish investigation plan and assign SAR filing.","confirmed"),
        ("MEV001","CASE-CMP-004","compliance_review","GDPR Audit Review Meeting",
         "2026-03-20 14:00:00","2026-03-20 15:00:00",
         "legal.team@company.com,dpo@company.com",
         "Legal Conference Room","Review data flow diagram and audit findings.","confirmed"),
        ("LEV001","CASE-CLA-005","claim_processing","Auto Claim #AC-7721 — Straight-Through Review",
         "2026-04-11 10:00:00","2026-04-11 10:30:00",
         "claims@company.com",
         "Virtual / Async","Standard review for straight-through approval.","confirmed"),
        ("DEV001","CASE-DOC-006","document_review","Q2 Contract Review — Legal Alignment Session",
         "2026-04-10 13:00:00","2026-04-10 14:30:00",
         "legal.ops@company.com,procurement@company.com",
         "Legal Conference Room","Align on conflicting clauses and resolution approach.","confirmed"),
    ]

    history = [
        # CASE-VND-001
        ("VH001","CASE-VND-001","vendor_onboarding","created","system","2026-04-02 09:00:00",
         "Vendor application received from Acme Corp.","open"),
        ("VH002","CASE-VND-001","vendor_onboarding","updated","vendor.review@company.com","2026-04-04 14:00:00",
         "Background check initiated.","pending"),
        ("VH003","CASE-VND-001","vendor_onboarding","escalated","vendor.review@company.com","2026-04-07 10:30:00",
         "Contract value $150,000 exceeds $100,000 threshold. CFO approval required.","escalated"),
        # CASE-CLM-002
        ("CH001","CASE-CLM-002","claim_review","created","system","2026-03-20 08:45:00",
         "Claim #INV-2024-089 submitted by policyholder.","open"),
        ("CH002","CASE-CLM-002","claim_review","updated","claims@company.com","2026-03-22 11:00:00",
         "Adjuster Martinez assigned. Additional documents requested.","pending"),
        ("CH003","CASE-CLM-002","claim_review","updated","policyholder.nguyen@email.com","2026-03-25 15:30:00",
         "All requested documents received.","open"),
        ("CH004","CASE-CLM-002","claim_review","reviewed","adjuster.martinez@company.com","2026-03-28 12:00:00",
         "Site visit completed. Damage assessed at $7,500.","pending"),
        # CASE-FRD-003
        ("FH001","CASE-FRD-003","fraud_investigation","created","fraud.monitor@company.com","2026-04-01 07:00:00",
         "Automated fraud flag triggered on Policy #FRD-2024-112.","open"),
        ("FH002","CASE-FRD-003","fraud_investigation","escalated","fraud.team@company.com","2026-04-01 09:30:00",
         "Full investigation opened. SAR filing initiated.","escalated"),
        ("FH003","CASE-FRD-003","fraud_investigation","updated","compliance@company.com","2026-04-02 10:30:00",
         "Compliance team engaged. Legal review in progress.","pending"),
        # CASE-CMP-004
        ("MH001","CASE-CMP-004","compliance_review","created","legal.team@company.com","2026-03-15 09:00:00",
         "Annual GDPR audit initiated for EU data ops.","open"),
        ("MH002","CASE-CMP-004","compliance_review","updated","dpo@company.com","2026-03-18 14:00:00",
         "Data flow diagram submitted. No new processors added.","open"),
        ("MH003","CASE-CMP-004","compliance_review","reviewed","legal.team@company.com","2026-03-20 15:00:00",
         "Audit findings reviewed. No material issues found.","pending"),
        # CASE-CLA-005
        ("LH001","CASE-CLA-005","claim_processing","created","system","2026-04-10 10:00:00",
         "Auto collision claim submitted for Policy AC-7721. All docs complete.","open"),
        ("LH002","CASE-CLA-005","claim_processing","updated","claims@company.com","2026-04-10 14:00:00",
         "Documentation verified. Eligible for straight-through processing.","open"),
        ("LH003","CASE-CLA-005","claim_processing","reviewed","claims@company.com","2026-04-11 10:30:00",
         "Straight-through review complete. Claim approved at $1,800.","resolved"),
        # CASE-DOC-006
        ("DH001","CASE-DOC-006","document_review","created","legal.ops@company.com","2026-04-05 09:00:00",
         "Q2 supplier contract review initiated for 12 agreements.","open"),
        ("DH002","CASE-DOC-006","document_review","updated","procurement@company.com","2026-04-08 11:30:00",
         "Three contracts flagged with policy conflicts. Conflict summary prepared.","pending"),
        ("DH003","CASE-DOC-006","document_review","escalated","legal.ops@company.com","2026-04-10 14:30:00",
         "Scope value $6,200 exceeds $5,000 threshold. Legal counsel review required.","escalated"),
    ]

    # Patch any pre-existing documents for demo cases that lack file_path
    c.execute("""
        SELECT id, case_id, filename FROM documents
        WHERE file_path IS NULL
        AND case_id IN (
            'CASE-VND-001','CASE-CLM-002','CASE-FRD-003',
            'CASE-CMP-004','CASE-CLA-005','CASE-DOC-006'
        )
    """)
    for doc_id, case_id, filename in c.fetchall():
        c.execute("UPDATE documents SET file_path=? WHERE id=?",
                  (f"{base}/documents/{case_id}/{filename}", doc_id))

    c.executemany("""INSERT OR IGNORE INTO emails
        (id,case_id,case_type,subject,sender,recipients,date,body,attachments,thread_id,file_path)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", emails)
    c.executemany("""INSERT OR IGNORE INTO documents
        (id,case_id,case_type,filename,file_type,description,tags,created_at,file_path)
        VALUES (?,?,?,?,?,?,?,?,?)""", documents)
    c.executemany("""INSERT OR IGNORE INTO calendar_events
        (id,case_id,case_type,title,start_time,end_time,attendees,location,description,status)
        VALUES (?,?,?,?,?,?,?,?,?,?)""", calendar_events)
    c.executemany("""INSERT OR IGNORE INTO case_history
        (id,case_id,case_type,event_type,actor,timestamp,notes,status)
        VALUES (?,?,?,?,?,?,?,?)""", history)
    conn.commit()
    print("[DB] Demo case seed data inserted.")


def get_all_case_ids():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT case_id, case_type FROM case_history ORDER BY case_id")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

if __name__ == "__main__":
    init_db()