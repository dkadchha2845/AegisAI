# KAVACH / PRESAGE — Phase 1 Audit

**Auditor role:** Principal Engineer · Security Architect · Senior UI/UX · DevSecOps · Full-Stack Lead
**Date:** 21 Jul 2026
**Scope:** Full-repo audit against the ET AI Hackathon 2026 problem statement (Problem 6) + `module2.pdf` (FIGAE) + `module3.pdf` (CFSRP), before any code change.

---

## 0. Executive summary

KAVACH today is **Module 1 (RSSIE) only, and it is excellent** — a real-time scam-call
stage classifier with threat fusion, a Markov "digital twin" forecast, victim-coercion
tracking, trust-passport identity checks, number-spoofing intelligence, script-similarity,
OCR intake, an auditable evidence package (JSON + PDF), a curated coach, and a
schema-first React frontend that is a strict pure renderer. Track 2 (SaaS: optional DB,
single-org RBAC, case book, audit log) is built and off-by-default. Code quality is high:
explicit-degradation discipline, provenance on every score, a contract-drift guard, 16
backend regression tests, green CI.

**The three deliverables the PDFs demand but the repo does not yet have:**

| | Module | Status before this work |
|---|---|---|
| 1 | **RSSIE** — real-time scam detection | ✅ Complete |
| 2 | **FIGAE** — fraud network + geospatial intelligence | ❌ **Absent** |
| 3 | **CFSRP** — citizen shield + response | ⚠️ **Partial** — pieces exist (coach, evidence, report PDF) but no citizen-facing verification/response/vault surface |

Plus the user's explicit asks: an **awwwards-grade landing + real login screen**, **Track 3**
(corpus expansion + MuRIL retrain — the model still loses to the lexical baseline), and
**multi-tenant orgs/teams**.

The winning move is **not a rewrite**. Module 1's engine already produces exactly the
structured intelligence Modules 2 and 3 are specified to *consume*. The correct build is to
add two new backend packages (`intel/`, `shield/`) and two new frontend routes that fuse
into the existing contract-first, degradation-honest architecture — turning three strong
but separate ideas into the PDF's headline pipeline: **Detect → Connect → Protect.**

---

## 1. Architecture (as built)

```
┌───────────────────────── apps/web (React 18 + Vite + TS) ─────────────────────────┐
│  Pure renderer. Zero threat maths in React. Every number is a contract field.      │
│  Routes: / · /dashboard · /console · /guardian · /analyzer · /cases · /knowledge   │
│          · /model                                                                  │
│  GSAP ScrollTrigger · three.js ThreatField · ⌘K palette · light/dark · AuthContext │
└───────────────▲──────────────────────────────────────────────────────────────────┘
                │  REST + WebSocket (4 Hz StateFrame snapshots + discrete Events)
┌───────────────┴──────────────── services/api (FastAPI, py3.9+) ────────────────────┐
│  main.py  /api/health (live-vs-degraded per component) · startup warm-load          │
│  routes/  analyze · session · auth · reports                                        │
│  engine/  classifier(MuRIL+lexical) · threat.fuse() · twin · coercion · passport    │
│           · spoofing · scripts · upi · ocr · analyzer · session(state machine)      │
│           · report + report_pdf (evidence package)                                  │
│  rag/     store(BM25/dense) · coach(curated, verbatim)   knowledge/ 3 docs, 26 chunk│
│  auth/db/audit/models_db  (SQLAlchemy, in-memory default; pbkdf2+HS256; RBAC ladder)│
└───────────────▲──────────────────────────────────────────────────────────────────┘
                │  imports (single source of truth)
        schema/models.py  ◄── check_contract.py ──►  schema/types.ts
                │
        ml/  taxonomy · seeds · paraphrase · build_dataset · train(MuRIL) · eval_backends
             data/ committed corpus (338 calls) · artifacts/ (checkpoint gated on measured F1)
```

**Load-bearing invariants** (from `memory/architecture-invariants.md`, confirmed in code):
1. **Schema-first contract.** `schema/` is the only thing that crosses the wire; `check_contract.py` fails the build on Python↔TS enum drift.
2. **Pure renderer.** No thresholds/stage rules/threat maths in React.
3. **Snapshot vs edge.** `StateFrame` is idempotent; `Event` is a one-shot edge.
4. **Explicit degradation.** Every capability degrades to a working fallback and records a `degraded` tag; never a silent worse answer.
5. **False-positive discipline.** BENIGN is the broadest class; the corpus is ~40% legitimate calls.

## 2. Tech stack

| Layer | Tech |
|---|---|
| Frontend | React 18, Vite, TypeScript (strict), react-router, GSAP + ScrollTrigger, three.js, lucide-react |
| Backend | FastAPI, Pydantic v2, Uvicorn, httpx |
| Persistence | SQLAlchemy 2.0 (in-memory SQLite default; file/Postgres via `DATABASE_URL`) |
| Auth | stdlib pbkdf2-hmac-sha256 + HS256 (no bcrypt/PyJWT dep) |
| ML | PyTorch 2.2, Transformers 4.44 (MuRIL), scikit-learn, NumPy<2; **networkx 3.2.1 already installed** |
| Retrieval | sentence-transformers (optional) / BM25 fallback |
| Reporting | reportlab (lazy/optional) |
| CI | GitHub Actions — py3.9 + py3.12 backend, frontend typecheck + vite build |

## 3. Database schema (as built)

`User` (id, email, password_hash, role∈{viewer<analyst<admin}, disabled, created_at) ·
`CaseRecord` (report_id, session_id, created_by, caller_number, incident_type, peak_threat,
final_level, package_json) · `AuditEvent` (ts, actor, action, target, detail — append-only).
**Single-org.** No `Organization` table; no `org_id` FKs.

## 4. API flow · Auth flow (as built)

- **Analyze (stateless):** `POST /api/analyze/{text,upi,file,image}` → one `analyze_text()` engine → scored `AnalysisResult`.
- **Session (stateful):** `POST /api/session` → `Session` state machine → `StateFrame` @4 Hz over WS; REST twins for every action; `/report[.pdf]` evidence package.
- **Auth:** off by default (open mode returns seeded admin so RBAC decorators still resolve). `PRESAGE_AUTH=1` → bearer HS256 required; uniform 401 (no account-existence oracle); constant-time compares; login audited.

---

## 5. GAP ANALYSIS — what the PDFs require and the repo lacks

### 5A. Module 2 — FIGAE (entirely missing) — **P0**

The PDF specifies a full sub-system. None of it exists:

| FIGAE requirement | Status | Plan |
|---|---|---|
| Unified fraud repository (historical + Module 1 real-time) | ❌ | Seed repo JSON + ingest saved `CaseRecord`s |
| Fraud entity extraction (phone, UPI, wallet, bank, email, domain, amount, scam-type, fake-authority, city/district/state, timestamps) | ❌ | `intel/entities.py` |
| Knowledge graph (PDF says Neo4j) | ❌ | **networkx** (already installed; no external server — matches degradation discipline; Neo4j is an optional prod swap) |
| Community detection (Louvain/Leiden) | ❌ | networkx greedy-modularity / label-propagation |
| Link prediction, centrality | ❌ | networkx resource-allocation index; degree/betweenness |
| Campaign detection (shared script/infra/number/location) | ❌ | shared-entity clustering |
| Geospatial hotspots (state/district/city, temporal, regional risk) | ❌ | `intel/geo.py` + committed India centroid map |
| Fraud risk scoring (linked cases, loss, reused infra, spread, M1 threat, connectivity → LOW/MED/HIGH/CRITICAL) | ❌ | `intel/scoring.py` |
| AI investigation report generator (cluster → report; PDF shows FC-021 exemplar) | ❌ | `intel/report.py` (+ optional LLM prose, never scores) |
| Investigator dashboard (live stats, network graph, geo, timeline, entity search, reports) | ❌ | `/intel` route |
| Entity search (phone/UPI/wallet/email/case) | ❌ | `GET /api/intel/search` |

### 5B. Module 3 — CFSRP (partial) — **P0**

| CFSRP requirement | Status | Plan |
|---|---|---|
| Multi-channel citizen intake (verify number/message/UPI/upload) | ⚠️ analyzer exists, not framed for citizens | `/shield` route + `POST /api/shield/verify` |
| Threat verification layer (fuse M1 + M2 for a submitted artifact) | ❌ | `shield/verify.py` — analyzer + intel lookup |
| Personalized AI guidance (stage-aware protective actions) | ⚠️ coach exists | `shield/guidance.py` reuses coach + stage |
| Emergency response engine (helplines, one-tap, action checklist) | ❌ | `shield/response.py` + helplines directory |
| Evidence preservation / vault (persist citizen submissions) | ❌ | `CitizenReport` table + vault UI |
| Structured complaint generation (incident summary, timeline, entities, evidence, AI analysis) | ⚠️ evidence package exists for live sessions only | extend `report.py` to citizen submissions |
| Nearby hotspots (from Module 2 geo) | ❌ | reuse `intel/geo.py` |
| Fraud awareness (similar recent scams) | ❌ | feed from repository |
| Citizen dashboard (live threat status, guidance, timeline, vault, hotspots, awareness) | ❌ | `/shield` |

### 5C. User-requested product gaps

| Ask | Status | Plan |
|---|---|---|
| Awwwards-worthy landing | ⚠️ Home is solid but not "winning-landing" grade | Rebuild hero (Three.js + GSAP scroll storytelling, magnetic CTAs, pinned sequences) |
| Proper login screen | ❌ only an inline card in `/cases` | Dedicated `/login` route wired to AuthContext |
| Multi-tenant orgs/teams | ❌ single-org by choice | `Organization` model + `org_id` scoping, backward compatible |
| Track 3 corpus + retrain | ⚠️ P0 in STATUS — MuRIL 0.22 < lexical 0.37 on held-out | Expand corpus (offline template-grammar, no key needed) → retrain CPU → eval; promotion stays gated |

---

## 6. Security audit (OWASP Top 10 / API Top 10 / CWE)

**Already sound:** pbkdf2 (240k iters, per-user salt), constant-time compares, uniform login
error, no account oracle, HS256 with checked expiry, password hash never serialized
(`as_public`), CORS locked to 5173, upload cap 4 MB + extension allowlist, no secrets in
history (`.gitignore` + `.env.example`), append-only audit for consequential actions, no
raw SQL (SQLAlchemy ORM → no SQLi), no `eval`, LLM boundary can't touch scores.

**Findings to fix in this build:**

| Sev | Finding | CWE / OWASP | Fix |
|---|---|---|---|
| ⚠️ Med | **No rate limiting** on `/auth/login` or `/analyze/*` — brute-force + DoS | CWE-307 / API4 | in-process token-bucket limiter middleware |
| ⚠️ Med | **No security headers** (CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy) | OWASP A05 | `SecurityHeadersMiddleware` |
| ⚠️ Med | **`.env` with a live `GEMINI_API_KEY` is committed to the working tree** (gitignored, but present on disk) | CWE-798 | Confirm gitignored; note key rotation in report; never echo it |
| ⚠️ Low | **No login lockout/backoff** after repeated failures | CWE-307 | fold into limiter (per-email + per-IP) |
| ⚠️ Low | **`CORS allow_credentials=True` with `allow_methods/headers=["*"]`** | API7 | keep origins locked; document |
| ⚠️ Low | New multi-tenant surface risks **IDOR / broken object-level auth** on cross-org reads | API1 | every intel/shield/report query filtered by `org_id`; tests |
| ℹ️ Info | Citizen file uploads (vault) must not be executed/served inline | CWE-434 | store text/metadata only; no execution; size + type caps |
| ℹ️ Info | `PRESAGE_SECRET_KEY` unset → ephemeral dev key | CWE-321 | documented; enforced-mode warning already prints |

## 7. Performance

- **Frontend:** all routes eager-imported in `App.tsx` → one bundle with three.js + GSAP. **Fix:** `React.lazy` per route + Suspense (defers the WebGL/GSAP payload off the landing critical path).
- **Backend:** startup warm-load is good. New graph build (Module 2) must be **cached and rebuilt on write**, not per-request. Entity search must be indexed (dict lookups), not full scans.
- **DB:** add indexes on new `org_id`, `CitizenReport.token`, intel entity keys.

## 8. UI/UX

Strong instrument aesthetic (Satoshi + JetBrains Mono, restrained palette, threat ramp as the only saturated colour, honest status pill). Gaps for a winning submission: the landing is informative but not cinematic; there is no dedicated auth screen; the nav has no home for the two new modules; no command-centre "map" visual (judges reward the geospatial/graph views the PDF explicitly asks for). All addressed in the build plan.

---

## 9. Build plan (Phase 8) — priority, grouping, why

Executed in this order; each group is independently shippable and preserves backward compatibility.

1. **Contract + Module 2 backend (`intel/`)** — the missing headline. Consumes Module 1 evidence packages → graph, geo, scoring, investigation reports. *Why first:* Module 3 and the dashboards depend on it.
2. **Module 3 backend (`shield/`)** — citizen verification/guidance/response/vault/complaint. *Why:* closes Detect→Connect→**Protect**; low-FP citizen tool is an explicit evaluation axis.
3. **Multi-tenant orgs** — `Organization` + `org_id` scoping, default-org seeded (single-org unchanged). *Why before UI:* the new routes should be org-aware from day one.
4. **Frontend: landing + login + Intel dashboard + Shield** — the visible win. Lazy-loaded.
5. **Track 3** — corpus expansion + retrain, promotion stays gated on measured F1.
6. **Security hardening + perf** — limiter, headers, code-split, indexes, tests.
7. **Verify end-to-end + browser proof; final report + deck guide.**

**DB changes:** +`Organization`, +`org_id` on User/CaseRecord/AuditEvent, +`FraudCluster`/`IntelEntity` (or rebuildable-in-memory), +`CitizenReport`. All additive; in-memory default preserved.
**API changes:** +`/api/intel/*`, +`/api/shield/*`, +`/api/orgs/*`. No breaking changes to existing endpoints.
**Frontend changes:** +`/login`, +`/intel`, +`/shield`; Home rebuilt; nav extended; routes lazy-loaded. Pure-renderer discipline preserved.

**Non-negotiables carried forward:** schema-first, pure renderer, explicit degradation, false-positive discipline, provenance on every score, no secret in history, green checks before every push.
