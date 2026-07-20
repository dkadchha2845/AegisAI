# PRESAGE corpus report

- Calls: **320** (200 scam / 120 benign)
- Utterances after de-duplication: **1240**
- **Leave-archetypes-out split.** 4 whole skeletons are held out for test; the model never trains on them.
- Held out: `gold_0002_kyc_expiry`, `gold_0005_electricity_bill`, `gold_0010_sim_swap_trai`, `gold_0013_genuine_police`
- Validation is carved from training skeletons (used only for early stopping, never reported).

## Class distribution

| Stage | train | val | test |
|---|---:|---:|---:|
| GREETING | 88 | 14 | 44 |
| AUTHORITY_CLAIM | 173 | 28 | 15 |
| FEAR_INDUCTION | 75 | 12 | 51 |
| ISOLATION | 42 | 5 | 4 |
| VERIFICATION_DEMAND | 38 | 3 | 24 |
| PAYMENT_SETUP | 160 | 23 | 2 |
| PAYMENT_EXECUTION | 183 | 30 | 4 |
| BENIGN | 172 | 23 | 27 |

## Warnings

- `ISOLATION` has only 42 training examples — generate more calls before trusting its recall.
- `VERIFICATION_DEMAND` has only 38 training examples — generate more calls before trusting its recall.
- `ISOLATION` has only 4 test examples — its recall figure will be too noisy to quote.
- `PAYMENT_EXECUTION` has only 4 test examples — its recall figure will be too noisy to quote.

## Digital Twin — top transitions

| From | Most likely next | p |
|---|---|---:|
| GREETING | AUTHORITY_CLAIM | 0.97 |
| AUTHORITY_CLAIM | FEAR_INDUCTION | 0.49 |
| FEAR_INDUCTION | ISOLATION | 0.48 |
| ISOLATION | VERIFICATION_DEMAND | 0.49 |
| VERIFICATION_DEMAND | PAYMENT_SETUP | 0.72 |
| PAYMENT_SETUP | PAYMENT_EXECUTION | 0.65 |
| PAYMENT_EXECUTION | ISOLATION | 0.83 |
| BENIGN | GREETING | 0.12 |

## Median turns to payment

| Stage | median turns | n |
|---|---:|---:|
| PAYMENT_SETUP | 3 | 85 |
| ISOLATION | 4 | 85 |
| VERIFICATION_DEMAND | 6 | 51 |
| AUTHORITY_CLAIM | 10 | 102 |
| FEAR_INDUCTION | 11 | 68 |
| GREETING | 12 | 102 |
