import re
from typing import List, Dict, Optional


def normalize_money(value: str) -> Optional[str]:
    value = value.lower().replace(",", "").strip()

    if "million" in value:
        num_match = re.search(r'(\d+(?:\.\d+)?)', value)
        if num_match:
            return str(float(num_match.group(1)) * 1_000_000)

    num_match = re.search(r'(\d+(?:\.\d+)?)', value)
    if num_match:
        return str(float(num_match.group(1)))

    return None


def add_rule(
    rules: List[Dict],
    rule_type: str,
    subject: str,
    operator: str,
    value: str,
    unit: Optional[str],
    action: str,
    condition_text: str,
    confidence: float,
    approver: Optional[str] = None,
):
    rules.append({
        "rule_type": rule_type,
        "subject": subject,
        "operator": operator,
        "value": value,
        "unit": unit,
        "action": action,
        "condition_text": condition_text,
        "confidence": confidence,
        "approver": approver,
    })


def extract_rules_from_chunk(chunk_text: str) -> List[Dict]:
    text = re.sub(r"\s+", " ", chunk_text).strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)

    rules: List[Dict] = []

    for sent in sentences:
        s = sent.lower().strip()

        # -------------------------
        # Dollar threshold patterns
        # -------------------------
        money_patterns = [
            r'exceeding \$?(\d[\d,]*(?:\.\d+)?)',
            r'exceeding (\d+(?:\.\d+)? million)',
            r'\$?(\d[\d,]*(?:\.\d+)?) or more',
            r'(\d+(?:\.\d+)? million) or more',
            r'\$?(\d[\d,]*(?:\.\d+)?)\+',
        ]

        extracted_money = None
        for pattern in money_patterns:
            m = re.search(pattern, s)
            if m:
                extracted_money = normalize_money(m.group(1))
                break

        # Board approval
        if "board of trustees must approve" in s or "board approval required" in s:
            if extracted_money:
                add_rule(
                    rules,
                    rule_type="approval_threshold",
                    subject="amount",
                    operator=">=",
                    value=extracted_money,
                    unit="USD",
                    action="ESCALATE",
                    condition_text=sent,
                    confidence=0.92,
                    approver="board_of_trustees",
                )

        if "capital expenditures" in s and extracted_money:
            add_rule(
                rules,
                rule_type="capital_expenditure_threshold",
                subject="capital_expenditure_amount",
                operator=">=",
                value=extracted_money,
                unit="USD",
                action="ESCALATE",
                condition_text=sent,
                confidence=0.90,
                approver="board_of_trustees",
            )

        if "borrowing" in s and extracted_money:
            add_rule(
                rules,
                rule_type="borrowing_threshold",
                subject="borrowing_amount",
                operator=">=",
                value=extracted_money,
                unit="USD",
                action="ESCALATE",
                condition_text=sent,
                confidence=0.90,
                approver="board_of_trustees",
            )

        if "term of five years or more" in s:
            add_rule(
                rules,
                rule_type="term_threshold",
                subject="contract_term_years",
                operator=">=",
                value="5",
                unit="years",
                action="ESCALATE",
                condition_text=sent,
                confidence=0.88,
                approver="board_of_trustees",
            )

        # -----------------------------------
        # Review / approval authority patterns
        # -----------------------------------
        if "general counsel" in s and ("review" in s or "reviewed" in s):
            add_rule(
                rules,
                rule_type="review_requirement",
                subject="legal_review_required",
                operator="==",
                value="true",
                unit=None,
                action="ESCALATE",
                condition_text=sent,
                confidence=0.85,
                approver="general_counsel",
            )

        if "cfo approves" in s or "vice president of finance" in s and "review" in s:
            add_rule(
                rules,
                rule_type="approval_requirement",
                subject="cfo_review_required",
                operator="==",
                value="true",
                unit=None,
                action="ESCALATE",
                condition_text=sent,
                confidence=0.84,
                approver="cfo",
            )

        if "president approves" in s or ("president" in s and "approve" in s):
            add_rule(
                rules,
                rule_type="approval_requirement",
                subject="president_approval_required",
                operator="==",
                value="true",
                unit=None,
                action="ESCALATE",
                condition_text=sent,
                confidence=0.86,
                approver="president",
            )

        if "procurement office reviews" in s or "director of procurement and business services" in s:
            add_rule(
                rules,
                rule_type="review_requirement",
                subject="procurement_review_required",
                operator="==",
                value="true",
                unit=None,
                action="ESCALATE",
                condition_text=sent,
                confidence=0.80,
                approver="procurement",
            )

        # ------------------------------------
        # Common contract condition escalators
        # ------------------------------------
        if "confidential or personal data" in s:
            add_rule(
                rules,
                rule_type="contract_condition",
                subject="confidential_data_involved",
                operator="==",
                value="true",
                unit=None,
                action="ESCALATE",
                condition_text=sent,
                confidence=0.87,
                approver="general_counsel",
            )

        if "extends beyond one year" in s or "renews automatically" in s:
            add_rule(
                rules,
                rule_type="contract_condition",
                subject="multiyear_or_autorenewal",
                operator="==",
                value="true",
                unit=None,
                action="ESCALATE",
                condition_text=sent,
                confidence=0.87,
                approver="gc_and_cfo",
            )

        if "advanced payments" in s:
            add_rule(
                rules,
                rule_type="contract_condition",
                subject="advanced_payment_terms",
                operator="==",
                value="true",
                unit=None,
                action="ESCALATE",
                condition_text=sent,
                confidence=0.84,
                approver="cfo",
            )

        if "limitation of liability" in s:
            add_rule(
                rules,
                rule_type="contract_condition",
                subject="limitation_of_liability_clause",
                operator="==",
                value="true",
                unit=None,
                action="ESCALATE",
                condition_text=sent,
                confidence=0.86,
                approver="general_counsel",
            )

        if "conflicts of interest exist" in s or "potential conflicts of interest" in s:
            add_rule(
                rules,
                rule_type="contract_condition",
                subject="conflict_of_interest",
                operator="==",
                value="true",
                unit=None,
                action="ESCALATE",
                condition_text=sent,
                confidence=0.86,
                approver="general_counsel",
            )

        if "minimum insurance requirements" in s:
            add_rule(
                rules,
                rule_type="contract_condition",
                subject="insurance_certificate_missing",
                operator="==",
                value="true",
                unit=None,
                action="ESCALATE",
                condition_text=sent,
                confidence=0.85,
                approver="gc_and_cfo",
            )

        if "student organizations may not enter into any contracts" in s:
            add_rule(
                rules,
                rule_type="role_restriction",
                subject="student_can_sign_contract",
                operator="==",
                value="false",
                unit=None,
                action="REJECT",
                condition_text=sent,
                confidence=0.91,
                approver="vice_president_student_success",
            )

    # remove exact duplicates
    unique_rules = []
    seen = set()
    for r in rules:
        key = (
            r["rule_type"],
            r["subject"],
            r["operator"],
            r["value"],
            r["action"],
            r["condition_text"],
        )
        if key not in seen:
            seen.add(key)
            unique_rules.append(r)

    return unique_rules