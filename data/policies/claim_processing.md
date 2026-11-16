# Claim Processing Policy

## Purpose
Govern the straight-through processing of routine insurance claims. Claims below the
review threshold are auto-approved and delegated to the next available claims analyst.
Claims exceeding the threshold require committee review before delegation.

## Scope
Applies to all claim_processing case types submitted via AMP workflow.

## Approval Thresholds

| Claim Amount | Action | Approver |
|---|---|---|
| > $5,000 | ESCALATE | risk_committee |
| > $10,000 | ESCALATE | claims_director |

## Auto-Approval Criteria
Claims are eligible for straight-through processing (no escalation) when:
- Monetary value is $5,000 or below
- All required documentation is present
- No fraud indicators flagged by monitoring systems
- Policy is current and in good standing

## Processing Steps
1. CSA retrieves claim documentation and policy history
2. RRA assesses fraud risk and documentation completeness
3. GPA evaluates monetary thresholds against this policy
4. IAA recommends next action (process_claim or request_additional_docs)
5. DA assigns to claims analyst for final processing
