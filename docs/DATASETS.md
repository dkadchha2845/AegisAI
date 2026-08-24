# AegisAI — Dataset Strategy

> Master §26. The dataset is the single most defensible research contribution
> available to this project, because almost nobody has built one for **Indian,
> multilingual, multimodal fraud evidence**.

---

## 1. Position

Public fraud datasets are text-only, English-only, and Western. The
Kaggle-standard options (SMS Spam Collection, Enron, generic credit-card fraud)
do not contain: Hinglish code-mixing, UPI identifiers, digital-arrest scripts,
Indian bank/authority impersonation, WhatsApp-shaped evidence, or QR payloads.

AegisAI therefore builds **AIFC — the AegisAI Indian Fraud Corpus**: a
multimodal, multilingual, licence-clean dataset with per-item provenance.

**Non-negotiable (master §36):** we do not rely entirely on Kaggle, we do not
collect private conversations without consent, and we do not fabricate data and
present it as real. Every item is labelled `synthetic`, `public`, or
`consented`, and that label is a first-class field.

---

## 2. What already exists

| Asset | Size | Quality |
|---|---|---|
| Synthetic scam-call corpus | 1,692 calls, train/val/test split | Good. Zero-leak 7/8-held-out-archetype split; validated by `ml/corpus/validate_corpus.py` |
| Stage transition matrix | Fitted | Powers the Digital Twin |
| Knowledge corpus | 31 chunks / 4 docs | Thin — Phase 3.5 expands to ≥1,500 |
| Coach library | 14 human-reviewed lines | Small but deliberately verbatim-only |
| Generation pipeline | `ml/corpus/` | **Reusable** — seeds, taxonomy, Hinglish handling, paraphrase, validation |

The generation pipeline is the real asset. Extending it to new modalities is far
cheaper than starting over.

---

## 3. Target composition — AIFC v1

**Target: ≥10,000 labelled items across 12 categories.**

| # | Category | Target | Primary modality |
|---|---|---|---|
| 1 | Digital arrest / law-enforcement impersonation | 1,200 | call, chat |
| 2 | Banking / KYC impersonation | 1,200 | SMS, screenshot, call |
| 3 | UPI / payment fraud | 1,000 | QR, screenshot, SMS |
| 4 | Phishing (URL-bearing) | 1,200 | SMS, email, URL |
| 5 | OTP / credential harvesting | 800 | SMS, call |
| 6 | Courier / customs | 700 | call, SMS |
| 7 | Job / task-based scams | 700 | WhatsApp, screenshot |
| 8 | Investment / trading | 700 | WhatsApp, screenshot |
| 9 | Loan / instant-credit apps | 600 | APK metadata, SMS |
| 10 | Customer-support impersonation | 600 | call, screenshot |
| 11 | Remote-access / screen-share | 500 | call, APK |
| 12 | Lottery / reward | 400 | SMS, screenshot |
| — | **BENIGN** (see §4) | **≥3,500** | all |

### Per-item record

```json
{
  "item_id": "aifc-000001",
  "category": "banking_impersonation",
  "label": "fraud",
  "risk_level": "high",
  "provenance": "synthetic",
  "language": "hinglish",
  "modalities": ["text", "screenshot", "url"],
  "text": "...",
  "assets": [{"type": "screenshot", "path": "...", "sha256": "..."}],
  "entities": {"urls": [...], "upi_ids": [...], "phones": [...]},
  "manipulation_tactics": ["authority_impersonation", "urgency", "fear"],
  "conversation_stages": ["GREETING", "AUTHORITY_CLAIM", "FEAR_INDUCTION"],
  "evidence_rationale": "Claims RBI authority; demands OTP within 10 minutes.",
  "annotator_ids": ["a1", "a2"],
  "agreement": 1.0,
  "created_at": "2026-10-04",
  "license": "MIT",
  "pii_status": "synthetic_identifiers_only"
}
```

---

## 4. The BENIGN class is the hard part

**≥35% of the corpus must be benign** — and benign in the *difficult* way:
messages that share vocabulary with scams but are legitimate.

- Real bank transaction alerts ("₹4,999 debited from A/c XX4471")
- Genuine KYC-update reminders from actual banks
- Real courier delivery notifications with tracking links
- Legitimate OTP messages
- Actual government advisories (which *do* use urgent language)
- Real merchant UPI QR codes
- Genuine customer-support callbacks

**Why this dominates the design:** a model trained on obvious scams versus random
benign text scores 0.99 and is useless. The benign class is what makes the
false-positive rate meaningful, and false positives are the failure mode that
matters for a citizen-facing safety tool.

Sources: public advisory corpora, consented volunteer donations with redaction,
and templates reconstructed from published examples — never scraped private inboxes.

---

## 5. Generation & collection pipeline

```
Seeds (archetype × language × channel × tactic)
        ↓
LLM generation (provider-abstracted, temperature-varied)
        ↓
Entity substitution — deterministic, offline, synthetic identifiers only
        ↓
Paraphrase augmentation (lexical + LLM)
        ↓
Rendering: text → SMS / WhatsApp / email screenshot (Task 8.3)
        ↓
Automated validation (schema, leakage, near-duplicate, banned-content)
        ↓
Human annotation (≥2 annotators on a 500-item overlap)
        ↓
Split assignment: temporal + held-out-archetype
        ↓
AIFC release bundle + data card
```

Steps 1–4 already exist in `ml/corpus/` and only need extending.

### Synthetic identifiers — strict rules 🛡️

- Phones: reserved/test ranges only, never a real subscriber number
- UPI VPAs: nonexistent handles at a reserved test domain
- URLs: a project-controlled sinkhole domain, or clearly-fake TLDs
- Names, addresses, account numbers: generated, never real
- Any real artefact from a public source is retained **only** with its licence
  and with PII redacted

---

## 6. Real-world data sources (public, licence-checked)

| Source | Use | Licence check |
|---|---|---|
| PhishTank / OpenPhish | Phishing URLs (positives) | Required before use |
| Tranco top-1M | Benign domains (negatives) | Open |
| URLhaus / abuse.ch | Malicious URL + malware indicators | Required |
| CERT-In advisories | RAG corpus + scam patterns | Public advisory |
| RBI / NPCI circulars | RAG corpus, benign-language reference | Public |
| MHA / I4C published cases | Category grounding, statistics | Public |
| AndroZoo / public APK sets | APK agent evaluation | Research agreement required |
| Consented volunteer donations | Real screenshots, redacted | Explicit consent form |

**Rule:** every external source is recorded in the data card with URL, access
date, licence, and how it was transformed. A reviewer must be able to audit it.

---

## 7. Splits — designed against leakage

Three splits, reported separately, because each answers a different question:

1. **Random split** — the optimistic number. Reported for comparability only.
2. **Held-out archetype** — train on 11 categories, test on the 12th. Answers
   *"does it generalise to a scam pattern it has never seen?"* This is the
   inherited discipline that produced the honest 0.767 macro-F1.
3. **Temporal split** — train on earlier items, test on later. Phishing and scam
   scripts are non-stationary; a random split silently inflates every URL result
   in the literature.

**Leakage guards (tested in CI):**
- No entity (URL, phone, UPI, domain) appears in more than one split
- No near-duplicate text across splits (MinHash threshold)
- No template/seed shared across splits
- Graph features computed only from data predating the test item (Task 3.7)

---

## 8. Annotation

- Written guidelines with worked examples and edge cases, versioned in the repo.
- ≥2 independent annotators on a **500-item overlap**.
- **Cohen's κ reported per label.** Target κ ≥ 0.75; anything below triggers
  guideline revision, not quiet acceptance.
- Disagreements adjudicated by a third annotator and the resolution recorded.
- Annotators may mark `uncertain` — forced choice manufactures false confidence.

---

## 9. Ethics, privacy, licensing

- Default synthetic. Real data only when public-and-licensed or explicitly consented.
- PII redaction before any item enters the corpus; verified by an automated scan.
- Released under **MIT**, matching the root `LICENSE`, with a documented
  exclusion list for third-party items whose licence forbids redistribution.
  (Changed from CC-BY-4.0 on 2026-08-24 when the licence was added: one licence
  for the whole project was the owner's call, and two files naming different
  ones is the drift task 0.7 exists to prevent.) Items this project does not own
  keep their own terms — a licence grants only what the grantor holds.
- **Dual-use acknowledged:** a corpus of convincing scam messages could be
  misused. Mitigation: release the *labelled evaluation* set and the *generation
  recipe*, with high-fidelity generated attack text gated behind a research
  request. Stated explicitly in the data card and the paper.
- Data card follows the Gebru et al. datasheet structure: motivation,
  composition, collection, preprocessing, uses, distribution, maintenance.

---

## 10. Success criteria

- [ ] ≥10,000 items, ≥35% benign, 12 categories
- [ ] ≥4 modalities represented (text, screenshot, URL, QR/audio)
- [ ] ≥3 languages/registers (English, Hindi, Hinglish)
- [ ] Cohen's κ ≥ 0.75 on the overlap set
- [ ] Zero leakage across all three splits, proven in CI
- [ ] Every item has provenance and licence
- [ ] Data card published
- [ ] `make dataset` reproduces the corpus from seeds
