# AegisAI corpus report

- Calls: **338** (209 scam / 129 benign)
- Utterances after de-duplication: **1617**
- **Leave-archetypes-out split.** Every archetype (scam type) sits in exactly one split; the model never sees a test archetype in any form. Seed 8.
- Test archetypes (5): `army_officer_olx`, `electricity_bill`, `loan_app_harassment`, `refund_overpayment`, `telecom_plan_upgrade`
- Val archetypes (4): `courier_parcel`, `credit_card_reward`, `credit_limit_upgrade`, `kyc_expiry`
- Train archetypes: 16 (always including `digital_arrest`, the scam the live product is built around)
- Validation is archetype-disjoint from training too; it picks the early-stopping epoch and is never reported.

## Class distribution

| Stage | train | val | test |
|---|---:|---:|---:|
| GREETING | 60 | 46 | 62 |
| AUTHORITY_CLAIM | 101 | 69 | 69 |
| FEAR_INDUCTION | 83 | 47 | 47 |
| ISOLATION | 71 | 12 | 5 |
| VERIFICATION_DEMAND | 37 | 39 | 9 |
| PAYMENT_SETUP | 156 | 4 | 49 |
| PAYMENT_EXECUTION | 106 | 8 | 129 |
| BENIGN | 358 | 18 | 32 |

## Warnings

- `VERIFICATION_DEMAND` has only 37 training examples — generate more calls before trusting its recall.
- `ISOLATION` has only 5 test examples — its recall figure will be too noisy to quote.

## Digital Twin — top transitions

| From | Most likely next | p |
|---|---|---:|
| GREETING | AUTHORITY_CLAIM | 0.96 |
| AUTHORITY_CLAIM | FEAR_INDUCTION | 0.51 |
| FEAR_INDUCTION | ISOLATION | 0.88 |
| ISOLATION | VERIFICATION_DEMAND | 0.48 |
| VERIFICATION_DEMAND | PAYMENT_SETUP | 0.84 |
| PAYMENT_SETUP | ISOLATION | 0.58 |
| PAYMENT_EXECUTION | FEAR_INDUCTION | 0.42 |
| BENIGN | GREETING | 0.12 |

## Median turns to payment

| Stage | median turns | n |
|---|---:|---:|
| PAYMENT_SETUP | 4 | 46 |
| ISOLATION | 8 | 46 |
| VERIFICATION_DEMAND | 8 | 24 |
| AUTHORITY_CLAIM | 12 | 46 |
| GREETING | 14 | 46 |
| FEAR_INDUCTION | 16 | 26 |
