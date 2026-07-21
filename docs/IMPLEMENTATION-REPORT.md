# KAVACH — Implementation Report

**What this session delivered:** the two missing modules (FIGAE + CFSRP), an
awwwards-grade landing + login, multi-tenant organisations, a 5× corpus
expansion + retrain pipeline, a full security-hardening pass, a **critical
crash fix**, and this report. The result is the complete PDF pipeline —
**Detect → Connect → Protect** — running end to end.

> Read alongside [`AUDIT.md`](AUDIT.md) (the Phase-1 audit that scoped this work)
> and [`STATUS.md`](../STATUS.md) (the running build record).

---

## 0. Headline results

| Check | Before | After |
|---|---|---|
| Backend tests | 58 | **84 passing** (+26: intel, shield, security, orgs) |
| Contract check | passing | **passing** (unchanged — no schema drift) |
| Frontend typecheck + build | passing | **passing** |
| KAVACH modules present | 1 of 3 | **3 of 3** |
| Fraud-intel graph | — | **114 cases → 9 clusters, 9 campaigns** |
| ML pipeline | retrain crashed at save | **2 latent bugs fixed; `ml/train.py` runs** |
| Main JS bundle | 845 kB | **48 kB** (libs split into cached chunks) |
| API under concurrent load | **SIGSEGV** | **stable** (temp-file DB fix) |
| Multi-tenant | single-org | **orgs + isolation, backward compatible** |
| Security headers / rate limiting | none | **CSP + 4 headers, token-bucket limiter, login backoff** |

---

## 1. The critical fix (do not skip this in the demo prep)

**Symptom:** the API segfaulted (exit 139) under a handful of concurrent
requests — reproducible, and fatal for a live demo.

**Cause:** a latent Track-2 bug. The default in-memory SQLite used
`StaticPool` — a *single* connection shared across every thread — because a
second connection to `:memory:` opens a different empty database. FastAPI serves
sync routes from a threadpool, so many threads drove one sqlite connection at
once, crashing the native library. The new parallel-fetching dashboards exposed
it.

**Fix** ([`services/api/db.py`](../services/api/db.py)): the ephemeral default is
now a **temp file**, unique per process and deleted on exit. Each thread checks
out its own connection; sqlite serialises file access itself. Still zero-config,
still ephemeral (`db:ephemeral`), now crash-safe. **Verified** by re-running the
exact load that crashed it (120 concurrent `auth/me` + 160 mixed + 30 POSTs) →
survives, returns 200.

---

## 2. Module 2 — FIGAE (Fraud Intelligence & Geospatial Analytics)

Correlates individual Module 1 detections into organised-crime intelligence. The
PDF named Neo4j; we use **NetworkX** (already a dependency, no server to fail on
stage) behind an interface Neo4j can swap into — reported honestly, like every
other optional backend.

### Files, in build order

| # | File | Role |
|---|---|---|
| 1 | `services/api/intel/entities.py` | Fraud-entity extraction (phone, UPI, wallet, bank, email, domain, amount, authority) from text **and** from a Module 1 evidence package |
| 2 | `services/api/intel/geo.py` | India gazetteer (24 cities + 15 state centroids) + hotspot detection (state/district/city, risk-banded) |
| 3 | `services/api/intel/repository.py` | Unified fraud repository — deterministic historical seed (8 campaigns with **reused infrastructure**) + Module 1 ingest |
| 4 | `services/api/intel/scoring.py` | Dynamic cluster risk (6 factors → LOW/MEDIUM/HIGH/CRITICAL) with named contributions |
| 5 | `services/api/intel/graph.py` | NetworkX knowledge graph + community detection, centrality, **link prediction**, campaign detection, subgraph export |
| 6 | `services/api/intel/report.py` | AI investigation report generator (the PDF's FC-021 exemplar) + optional LLM prose |
| 7 | `services/api/intel/service.py` | Cached, rebuild-on-write service + entity search |
| 8 | `services/api/routes/intel.py` | 9 read-only endpoints for the dashboard |
| 9 | `services/api/main.py` | Warm-load graph at startup; `/api/health.intel` |
| 10 | `services/api/routes/reports.py` | **Wired Module 1 → Module 2**: saving a case ingests it into the graph |
| 11 | `apps/web/src/components/intel/ForceGraph.tsx` | Dependency-free force-directed graph (velocity-Verlet, ~90 nodes) |
| 12 | `apps/web/src/components/intel/HotspotMap.tsx` | SVG India choropleth, real lat/lon projection, risk-coloured bubbles |
| 13 | `apps/web/src/pages/Intel.tsx` | The investigator dashboard |

### What it produces (measured on the committed seed)

- **9 clusters**, **9 campaigns**, **47 linked entities**, **₹12.15 cr** exposure.
- **FC-001 reproduces the PDF's FC-021 exemplar**: 26-case digital-arrest campaign, CRITICAL, Karnataka/Telangana/Tamil Nadu, 4 shared phones, 3 shared UPIs.
- **Link prediction found the cross-crew money mule**: two phone numbers joined only through a shared payment account (`customs.duty@okaxis`) — the PDF's canonical example, working.
- **Community detection correctly split campaigns** by modularity while keeping bridged crews connected.
- Isolated seed cases are **not** folded into campaigns (false-positive discipline for the graph).

### Endpoints

`GET /api/intel/{stats,clusters,clusters/{id},clusters/{id}/report,geo,centrality,links,search,graph}`

---

## 3. Module 3 — CFSRP (Citizen Fraud Shield & Response)

The user-facing layer. It doesn't detect — it **fuses Module 1 + Module 2** into
one citizen answer, then delivers guidance, emergency response, evidence
preservation, and a filable complaint.

### Files, in build order

| # | File | Role |
|---|---|---|
| 1 | `services/api/shield/guidance.py` | Stage-aware protective actions; coach line delivered **verbatim** |
| 2 | `services/api/shield/response.py` | Emergency engine — official helpline directory (1930, cybercrime.gov.in, 112, 1909) + severity-scaled checklist |
| 3 | `services/api/shield/verify.py` | Threat verification — Module 1 analyzer + Module 2 cluster cross-reference |
| 4 | `services/api/models_db.py` | `CitizenReport` model — the evidence vault (token-addressed) |
| 5 | `services/api/shield/complaint.py` | Structured cybercrime-complaint package; reuses the Module 1 PDF renderer |
| 6 | `services/api/routes/shield.py` | Public verify / preserve / vault / complaint(.pdf) / awareness |
| 7 | `apps/web/src/pages/Shield.tsx` | The citizen shield UI |

### Behaviour (verified live in the browser + tests)

- Digital-arrest message → **"This is very likely a scam", CRITICAL (93)**, panic banner with 1930 / cybercrime.gov.in tap buttons, verbatim coach line, 4-item checklist, **linked to FC-001 + FC-002** with their state spread.
- Genuine bank reminder → **LIKELY_LEGITIMATE, CALM** (false-positive discipline intact — an explicit evaluation axis).
- A *known-fraud number* escalates a thin message to LIKELY_SCAM (the value of connecting the modules); an *unknown* number never manufactures danger.
- Vault is token-gated (possession-based access, since a citizen has no account); no executable uploads.

### Endpoints

`GET /api/shield/{helplines,awareness}` · `POST /api/shield/{verify,preserve}` · `GET /api/shield/vault/{token}[/complaint][.pdf]`

---

## 4. Landing + login (awwwards-grade)

| File | Change |
|---|---|
| `apps/web/src/pages/Home.tsx` | Rebuilt: full-bleed WebGL hero, kinetic headline, **Detect → Connect → Protect** pipeline, live stats, GSAP scroll choreography, magnetic CTA, its own minimal header. Outside the app shell. |
| `apps/web/src/pages/Login.tsx` | New dedicated auth screen — glassmorphic panel over the WebGL backdrop, open-demo-mode note + seeded credentials, wired to `AuthContext`, redirect-back. |
| `apps/web/src/App.tsx` | Landing + login outside the shell; **all other routes lazy-loaded** behind Suspense. |
| `apps/web/src/styles/modules.css` | ~430 lines of styling for the two modules, landing, and login — same restrained token system. |

Motion respects `prefers-reduced-motion` and the existing GSAP failsafe; every element is legible with JS disabled.

---

## 5. Multi-tenant organisations (Track 2 extension)

Backward compatible: a default org is seeded, the demo is unchanged, and
multi-tenancy only *appears* when an owner creates a second org.

| File | Change |
|---|---|
| `services/api/models_db.py` | `Organization` model; `org_id` on User/CaseRecord/AuditEvent/CitizenReport; `owner` role atop the ladder |
| `services/api/orgs.py` | Seed default org, create org, **`scope_query`** — the single tenant-isolation choke point |
| `services/api/auth.py` | Token carries `org`; seed creates default org + owner; `create_user` takes `org_id` |
| `services/api/routes/orgs.py` | `GET/POST /api/orgs`, `GET /api/orgs/current` |
| `services/api/routes/{auth,reports}.py` | Users, cases, audit **scoped by org**; owner sees across; IDOR-closed |
| `apps/web/.../CaseBook.tsx`, `AuthContext.tsx`, `lib/api.ts` | Org shown in identity card; owner-only org-management table |

**Isolation is tested** (`test_orgs.py`): an org admin sees only their own org's users/cases; an owner sees all; an org admin cannot mint an owner.

---

## 6. Security hardening + performance

| Area | Change | File |
|---|---|---|
| Rate limiting | Token-bucket per IP + route class (auth 10/min, analyze/shield 40/min) → 429 | `services/api/security.py` |
| Security headers | CSP `default-src 'none'`, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy on every response | `services/api/security.py` |
| Login backoff | 5 failures / 5 min per email+IP → 429 cooling-off (CWE-307) | `security.py` + `routes/auth.py` |
| Crash safety | Temp-file DB (see §1) | `db.py` |
| Code splitting | Every route lazy-loaded; three.js / GSAP / React split into cached vendor chunks | `App.tsx`, `vite.config.ts` |

**Verified live:** headers present on `/api/health`; limiter returns 429 over
limit and passes normal traffic; `test_security.py` (5 tests) locks it in.

---

## 7. Track 3 — corpus expansion + MuRIL retrain

**The STATUS P0.** The fine-tuned model memorised call *archetypes* rather than
learning *stages*, because 16 archetypes (8 held out) is too few. The measured
fix is more data with more archetypes and denser starved-stage coverage — and,
crucially, **no LLM key** (Gemini's free quota is exhausted; a corpus step must
not depend on a service that can 429).

This is the one workstream that ended somewhere other than where it started, and
the honest account matters more than a headline number.

### What was attempted, and what it taught

I built `ml/synth_seeds.py` — a deterministic, **no-LLM** corpus generator
(Gemini's free quota is exhausted, so a corpus step could not depend on it) — and
used it to expand the corpus 5× (338 → 1,692 calls) across 16 new archetypes,
weighted toward the starved stages. On paper the class balance improved
dramatically (ISOLATION 47 → 776 train, VERIFICATION 67 → 931).

Then I trained and **measured** — and the held-out score came back **0.9986**,
which is not a win, it is a **red flag**. The generator reuses the *same phrase
banks across every synthetic archetype*, so holding one archetype out of the
leave-archetypes-out split does not actually hold out its vocabulary. The split
leaked, and the number is inflated and meaningless. Committing a 0.9986 that a
judge could puncture in one question ("your held-out archetypes share phrase
templates — that's leakage") is the exact opposite of the auditability this
product is built on.

### What was kept

- **Reverted the corpus** to the original 338-call set, whose leave-archetypes-out
  split is a *valid* benchmark (distinct per-archetype vocabulary). The committed
  comparison stands: **lexical macro-F1 0.368 > MuRIL 0.221 on unseen
  archetypes**, so the promotion gate correctly serves lexical and `/api/health`
  says so.
- **Fixed two real latent bugs in the training pipeline** (kept):
  - `ml/train.py` was missing `save_safetensors=False`, so **every** run crashed
    at the first epoch-boundary checkpoint save on MuRIL's non-contiguous tensors
    — the documented "regenerate with `ml/train.py`" path was broken. Now it runs.
  - `classification_report` was called without `labels=`, so a split missing any
    class crashed the run *after* training finished. Now robust.
- **Kept `ml/synth_seeds.py`** as a documented tool, with the leakage limitation
  written down: templated expansion improves balance but cannot produce a valid
  *unseen-archetype* benchmark — that needs genuine per-archetype vocabulary,
  i.e. LLM-diverse generation, which is the offline next step.

### The honest takeaway

The fine-tuned model still loses to the lexical baseline on a valid benchmark, and
KAVACH **serves the baseline and reports that it is doing so**. That is the
STATUS-documented state, now with a training pipeline that actually runs end to
end. Refusing to ship an inflated number is the same discipline as the honest
promotion gate — and it is a stronger technical-excellence story than a
suspicious 0.99.

---

## 8. What is done vs what is next

### Done and demoable
- All 3 modules end to end; 9 routes for Module 2, 8 for Module 3.
- Landing, login, investigator dashboard (graph + India map + clusters + AI report + search), citizen shield (verify + guidance + emergency + vault + complaint PDF).
- Multi-tenant orgs with isolation tests; security hardening; the crash fix.
- 84 backend tests, contract check, typecheck, build — all green.

### Next (additive, none blocks the demo)
- **LLM-diverse corpus expansion** offline (when API quota is available) — genuine per-archetype vocabulary is what could finally beat the lexical baseline; the `ml/train.py` pipeline now runs end to end to support it.
- **Live audio/ASR** (contract already anticipates it — `partial_text`, binary WS frames).
- **Real outbound guardian alert** (SMS/WhatsApp) and **real UPI hold** (regulatory, not code).
- **Neo4j** swap behind `intel/graph.py` for graph persistence at national scale.
- **Dense retrieval / OCR** — uncomment the optional deps.

---

## 9. Demo script (5 minutes, judge-facing)

1. **Landing** (`/`) — "digital-arrest scams are an industrial pipeline, so the defence is a pipeline: Detect → Connect → Protect." Scroll the three modules.
2. **Detect** (`/console`) — type three caller lines; watch the stage classifier, threat meter ratchet, and the twin forecast "money moves in ~Ns".
3. **Analyzer** (`/analyzer`) — paste a scam SMS → scored verdict with named drivers + citations. Paste a benign bank line → LIKELY_LEGITIMATE (show the false-positive discipline).
4. **Connect** (`/intel`) — the fraud graph. Open **FC-001** (the 26-case digital-arrest campaign), show shared infra, the AI investigation report + suggested actions, the India hotspot map, and **entity search** for `customs.duty@okaxis` → the cross-crew mule the link-prediction found.
5. **Protect** (`/shield`) — paste the digital-arrest message + caller number `7042118830` → CRITICAL, panic banner with 1930, verbatim coach line, **"linked to known fraud networks FC-001/FC-002"**, then **Preserve & prepare complaint** → download the PDF.
6. **Platform** (`/cases`) — saved cases, append-only audit, users, and (as owner) **organisations**. Mention the crash fix and honest degradation reporting on the dashboard.

**One-liner:** *"It detects the scam on the call, connects it to the network behind it, and protects the citizen on the line — and every number it shows, it can defend."*

---

## 10. Presentation guidance — mapped to the judging criteria

| Criterion | Weight | The argument to make |
|---|---:|---|
| **Innovation** | 25% | Not another classifier — an end-to-end **Detect→Connect→Protect** pipeline where each module feeds the next; the twin *forecasts* time-to-payment; link prediction surfaces the hidden money mule. |
| **Business Impact** | 25% | Shifts from post-complaint investigation to **pre-transfer** intervention; ₹1,776 cr / 9 months is the addressable harm; the citizen shield's low false-positive rate is what makes it adoptable. |
| **Technical Excellence** | 20% | Schema-first contract, pure-renderer frontend, **honest promotion gate** (serves the measurably-better model, says which), provenance on every score, 84 tests, the reproduced-and-fixed segfault. |
| **Scalability** | 15% | Optional DB (in-memory → Postgres), **multi-tenant orgs**, NetworkX→Neo4j swap, code-split frontend, rate limiting — the SaaS surface is already there. |
| **User Experience** | 15% | Awwwards landing, instrument-grade dashboards, the citizen shield built for a panicking non-technical user (big type, one-tap 1930, plain guidance). |

**The honesty story is a feature, not an apology:** every degradation is shown,
every score is cited, and the fine-tuned model is served *only if it beats the
baseline*. That rigor is exactly what a law-enforcement / financial-institution
buyer needs, and it is rare in a hackathon build.
