# AegisAI corpus report

- Calls: **338** (209 scam / 129 benign)
- Utterances after de-duplication: **1617**
- Calls contributing at least one utterance: **304** (34 were entirely near-duplicates of earlier calls)
- **Leave-archetypes-out split.** Every archetype (scam type) sits in exactly one split; the model never sees a test archetype in any form. Seed 9.
- Test archetypes (7): `electricity_bill`, `genuine_police`, `investment_returns`, `loan_app_harassment`, `mutual_fund_sip`, `sim_swap_trai`, `tech_support_remote`
- Val archetypes (6): `family_conversation`, `genuine_delivery`, `hospital_emergency`, `income_tax_refund`, `insurance_claim`, `kyc_expiry`
- Train archetypes: 12 (always including `digital_arrest`, the scam the live product is built around)
- Validation is archetype-disjoint from training too; it picks the early-stopping epoch and is never reported.

## Class distribution

| Stage | train | val | test |
|---|---:|---:|---:|
| GREETING | 87 | 29 | 52 |
| AUTHORITY_CLAIM | 150 | 21 | 68 |
| FEAR_INDUCTION | 93 | 40 | 44 |
| ISOLATION | 45 | 14 | 29 |
| VERIFICATION_DEMAND | 47 | 30 | 8 |
| PAYMENT_SETUP | 130 | 8 | 71 |
| PAYMENT_EXECUTION | 200 | 12 | 31 |
| BENIGN | 275 | 50 | 83 |

## Warnings

- `ISOLATION` has only 45 training examples — generate more calls before trusting its recall.
- `VERIFICATION_DEMAND` has only 47 training examples — generate more calls before trusting its recall.

## Digital Twin — top transitions

| From | Most likely next | p |
|---|---|---:|
| GREETING | AUTHORITY_CLAIM | 0.97 |
| AUTHORITY_CLAIM | FEAR_INDUCTION | 0.50 |
| FEAR_INDUCTION | ISOLATION | 0.34 |
| ISOLATION | VERIFICATION_DEMAND | 0.71 |
| VERIFICATION_DEMAND | PAYMENT_SETUP | 0.72 |
| PAYMENT_SETUP | PAYMENT_EXECUTION | 0.77 |
| PAYMENT_EXECUTION | ISOLATION | 0.82 |
| BENIGN | GREETING | 0.12 |

## Median turns to payment

| Stage | median turns | n |
|---|---:|---:|
| PAYMENT_SETUP | 3 | 102 |
| ISOLATION | 6 | 82 |
| VERIFICATION_DEMAND | 6 | 61 |
| AUTHORITY_CLAIM | 10 | 102 |
| FEAR_INDUCTION | 11 | 62 |
| GREETING | 12 | 102 |
