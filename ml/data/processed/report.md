# PRESAGE corpus report

- Calls: **338** (209 scam / 129 benign)
- Utterances after de-duplication: **1617**
- **Leave-archetypes-out split.** 8 whole skeletons are held out for test; the model never trains on them.
- Held out: `benign_0061_telecom_plan_upgrade`, `gold_0004_courier_parcel`, `gold_0008_loan_app_harassment`, `gold_0009_refund_overpayment`, `gold_0013_genuine_police`, `scam_0027_kyc_expiry`, `scam_0192_income_tax_refund`, `scam_0212_credit_limit_upgrade`
- Validation is carved from training skeletons (used only for early stopping, never reported).

## Class distribution

| Stage | train | val | test |
|---|---:|---:|---:|
| GREETING | 78 | 26 | 64 |
| AUTHORITY_CLAIM | 90 | 28 | 121 |
| FEAR_INDUCTION | 85 | 39 | 53 |
| ISOLATION | 46 | 27 | 15 |
| VERIFICATION_DEMAND | 43 | 16 | 26 |
| PAYMENT_SETUP | 142 | 40 | 27 |
| PAYMENT_EXECUTION | 147 | 38 | 58 |
| BENIGN | 174 | 175 | 59 |

## Warnings

- `ISOLATION` has only 46 training examples — generate more calls before trusting its recall.
- `VERIFICATION_DEMAND` has only 43 training examples — generate more calls before trusting its recall.

## Digital Twin — top transitions

| From | Most likely next | p |
|---|---|---:|
| GREETING | AUTHORITY_CLAIM | 0.97 |
| AUTHORITY_CLAIM | FEAR_INDUCTION | 0.56 |
| FEAR_INDUCTION | ISOLATION | 0.58 |
| ISOLATION | VERIFICATION_DEMAND | 0.58 |
| VERIFICATION_DEMAND | FEAR_INDUCTION | 0.46 |
| PAYMENT_SETUP | PAYMENT_EXECUTION | 0.58 |
| PAYMENT_EXECUTION | GREETING | 0.12 |
| BENIGN | GREETING | 0.12 |

## Median turns to payment

| Stage | median turns | n |
|---|---:|---:|
| PAYMENT_SETUP | 3 | 68 |
| AUTHORITY_CLAIM | 7 | 68 |
| VERIFICATION_DEMAND | 8 | 17 |
| GREETING | 9 | 68 |
| ISOLATION | 12 | 34 |
| FEAR_INDUCTION | 16 | 34 |
