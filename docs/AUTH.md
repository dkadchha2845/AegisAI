# Authentication, database and access control

Everything about who can sign in to AegisAI, what each role may do, and where
that is written down. Read [`ARCHITECTURE.md`](ARCHITECTURE.md) for the system
around it.

---

## The short version

| | |
|---|---|
| **Database** | PostgreSQL in a durable deployment, SQLite for the zero-setup demo. One SQLAlchemy code path, chosen by `DATABASE_URL`. No second store was introduced — no Supabase, no Prisma, no Firebase. |
| **Schema changes** | Alembic. `make migrate` against a durable `DATABASE_URL`; head is `0003`. |
| **Authentication** | Email + password. Passwords hashed with **argon2id** when `argon2-cffi` is installed and **pbkdf2-hmac-sha256 (240 000 iterations)** otherwise; both verify forever and an older hash is upgraded on the owner's next sign-in. |
| **Sessions** | HS256 JWT in `Authorization: Bearer`, each carrying a `jti` backed by a row in `user_sessions`. Signing out revokes the row, so a dead token is dead server-side, not merely forgotten by the browser. |
| **Authorisation** | A permission catalogue (`services/api/permissions.py`) mapped to seven roles, enforced on every route by `require_permission`. |
| **Seeded accounts** | Every account that existed before this work still signs in with the same password and the same role. |

---

## 1. Database

**PostgreSQL**, through SQLAlchemy, with SQLite as the zero-setup fallback. This
is what the project already used and it has not changed — §17 of the
specification asks not to introduce a second database architecture, and none was.

```bash
# durable Postgres (the compose stack)
export DATABASE_URL=postgresql+psycopg://aegis:aegis_dev_only@127.0.0.1/aegis

# durable SQLite, a single file
export DATABASE_URL=sqlite:///aegis.db

# unset — a per-process temp file, deleted at exit, reported as db:ephemeral
```

`DATABASE_URL` is the only switch. With none set, `services/api/db.py` invents a
temp file so a clean clone boots with no setup at all, and `/api/health` reports
`db:ephemeral` so nothing pretends to be durable that is not.

> Set `AEGIS_EVIDENCE_DIR` whenever you set `DATABASE_URL`. Otherwise the case
> outlives its own uploaded screenshots, and `/api/health` raises
> `blobs:ephemeral` for exactly that mismatch.

### Tables

Added by revision **0003**:

| Table | What it holds |
|---|---|
| `roles` | The role catalogue — name, description, ladder rank. |
| `permissions` | Every capability code, with the sentence a UI shows. |
| `role_permissions` | Which role holds which permission. |
| `user_sessions` | One row per issued token: `jti`, owner, expiry, revocation, last seen, IP, user agent. **The token itself is never stored.** |
| `password_resets` | Single-use reset grants, stored as a SHA-256 digest of the token. |

Modified by **0003**:

| Table | Columns added |
|---|---|
| `users` | `role_id`, `full_name`, `phone`, `avatar_url`, `email_verified`, `updated_at`, `last_login_at` |
| `audit_events` | `actor_user_id`, `resource_type`, `resource_id`, `success`, `ip`, `user_agent` |

Unchanged, and listed because they are the relationships §10 asks about:
`organizations`, `case_records`, `citizen_reports`, and the six evidence-store
tables from task 1.5 (`investigations`, `evidence_items`, `agent_results`,
`findings`, `entities`, `case_entities`).

### Why `users.role` is still a string

It is what the token carries, what every existing query filters on, and what
`as_public()` has always returned. `roles.name` is unique, so the string *is* a
key; `users.role_id` carries the numeric foreign key beside it for the relational
reads a schema diagram and a SQL console want. `auth.set_user_role()` is the only
writer of the pair, so the two cannot drift, and `seed_rbac()` repairs any row
whose `role_id` is missing or stale on every boot.

---

## 2. Roles

Seven, and the four inherited ones are unchanged in both name and capability.

| Role | For | Lands on |
|---|---|---|
| `citizen` | A member of the public. | `/dashboard` |
| `viewer` | Read-only desk (inherited). | `/dashboard` |
| `researcher` | Academic / evaluation access. | `/research/dashboard` |
| `analyst` | Fraud analyst (inherited). | `/dashboard` |
| `police` | Authorised investigator. | `/police/dashboard` |
| `admin` | Organisation administrator (inherited). | `/admin/dashboard` |
| `owner` | Platform superadmin (inherited). | `/admin/dashboard` |

### Why this stopped being a ladder

`models_db.py` used to say: *"Roles are a strict hierarchy … when a capability
appears that does not fit the ladder, this becomes a permissions table."* Two now
do not fit.

- A **citizen** may create an investigation and read their own, and may not read
  anyone else's — simultaneously above and below `viewer`.
- A **researcher** may read aggregate statistics and model evaluation and must
  never read a case — beside the ladder, not on it.

`ROLE_RANK` survives for the one question that genuinely is ordinal: **who may
promote whom**. The relative order of the four inherited roles is unchanged, so
every check written against them answers exactly as it did.

---

## 3. Permissions

The catalogue lives in [`services/api/permissions.py`](../services/api/permissions.py)
as a Python literal — a security review can read the whole grant top to bottom,
and nothing with a database connection can edit it. The `roles` /
`permissions` / `role_permissions` tables are that map projected into SQL, and
`seed_rbac()` **reconciles** them on every boot: a grant added in code appears,
and a grant removed in code disappears.

| Code | |
|---|---|
| `INVESTIGATION_CREATE` | Start an investigation by submitting evidence. |
| `INVESTIGATION_READ_OWN` | Read investigations you created. |
| `INVESTIGATION_READ_ASSIGNED` | Read investigations assigned to you. |
| `INVESTIGATION_READ_ALL` | Read every investigation in your organisation. |
| `INVESTIGATION_UPDATE` | Change a case's status or add notes. |
| `INVESTIGATION_DELETE` | Erase a case and the bytes of its evidence. |
| `EVIDENCE_UPLOAD` / `EVIDENCE_READ` | Attach and read artefacts. |
| `ANALYZE_USE` | Run the analyzer. |
| `LIVE_SESSION_USE` | Run a live protected call. |
| `THREAT_INTEL_READ` | Aggregate statistics and hotspots. |
| `THREAT_INTEL_MANAGE` | Rebuild and curate the fraud graph. |
| `GRAPH_READ` | The knowledge graph — clusters, entities, link prediction. |
| `REPORT_CREATE` | Save an evidence package. |
| `REPORT_READ_OWN` / `REPORT_READ_ASSIGNED` / `REPORT_READ_ALL` | Read case files. |
| `USER_MANAGE` | Create, disable and edit accounts. |
| `ROLE_MANAGE` | Change which role a user holds. |
| `ORG_MANAGE` | Create organisations and see across them. |
| `AUDIT_READ` | Read the audit log. |
| `AGENT_CONFIG` | Read agent configuration and system settings. |
| `RESEARCH_READ` | Anonymised datasets, model evaluation, fraud trends. |

The split that carries the most weight: **`THREAT_INTEL_READ` is aggregate and
`GRAPH_READ` is entity-level.** A citizen holds the first — those are the "what
is going around" figures the landing page has always shown everybody — and never
the second, because clusters, centrality over reused phone numbers and entity
search are personal data about specific accounts.

`permissions.py` refuses to import if a role is granted a code that does not
exist, or if a code is granted to nobody.

---

## 4. Sign-in, sessions and sign-out

### Two modes

`AEGIS_AUTH` chooses:

- **open (default)** — a request with **no `Authorization` header** acts as the
  seeded owner, so the demo runs with no login while every route still declares
  the RBAC it *would* enforce. A presented token is honoured for who it names.
- **enforced (`AEGIS_AUTH=1`)** — every protected route requires a valid token.

A **presented-and-refused** credential is a 401 in *both* modes. It used to fall
through to the open-mode identity, which meant that in the default configuration
logging out, rotating a token and being demoted all left the dead token
working — as the **owner**, because that is who the fallback returns. Open mode
means "no login is required"; it cannot also mean "a rejected credential is
upgraded to the highest one in the system". Found by running the flow, not by
the suite; pinned by
[`test_auth.py::test_a_refused_token_is_never_upgraded_to_the_open_mode_owner`](../services/api/tests/test_auth.py).

### Why the token is a bearer header and not an HttpOnly cookie

§4 prefers cookies, and explicitly allows keeping JWT where replacing it would
be an unnecessary architectural change. It would be:

- The investigation progress stream is authenticated SSE read through `fetch()`
  precisely so no credential ends up in a URL — see the note in
  [`routes/investigations.py`](../services/api/routes/investigations.py).
- The API is cross-origin from the SPA in every deployment shape this project
  has, and `allow_credentials` with a wildcard origin is not a combination any
  browser honours.
- A cookie would add a CSRF surface to every mutating route in order to remove
  an XSS surface that the strict CSP in `security.py` already narrows.

What a cookie would genuinely have bought — **revocation** — is bought instead by
the `user_sessions` table.

**The residual risk, stated:** the token is readable by script injected into the
SPA's origin. It is bounded by a 12-hour expiry (`AEGIS_TOKEN_TTL`), by
server-side revocation, and by rotation on refresh, and it is not a substitute
for a cookie. If this ever ships publicly, moving to an HttpOnly cookie plus a
double-submit CSRF token is the change to make, and it is a change to
`get_current_user`, `api.ts` and the SSE reader — nothing else.

### What ends a session

| Action | Effect |
|---|---|
| `POST /api/auth/logout` | Revokes this session. |
| `POST /api/auth/refresh` | Revokes this session and opens a new one — a stolen token is good for one TTL, not forever. |
| `DELETE /api/auth/sessions` | Revokes every session *except* the caller's. |
| Password change or reset | Revokes every other session. |
| An admin changing a role | Revokes every session that user holds. |
| An admin disabling an account | Revokes every session, and refuses the next sign-in with a 403 that says why. |

Expired rows older than a week are swept at boot. The **audit trail** of who
signed in and out lives in `audit_events`, which is append-only and never swept.

---

## 5. Passwords

- **argon2id** (19 MiB, t=2, p=1 — OWASP's second recommended configuration)
  when `argon2-cffi` is importable; **pbkdf2-hmac-sha256 at 240 000 iterations**
  otherwise. `/api/health` reports which is serving under `auth.password_hash`.
- Both schemes verify forever — the stored string says which wrote it — so the
  two installs interoperate on one database.
- A password verified against the older scheme is **re-hashed with the current
  one during login**. Installing `argon2-cffi` therefore upgrades every account
  as its owner next signs in: no migration, no reset.
- Strength is enforced **server-side** on every path that sets a password
  (`auth.password_problem`): at least 10 characters, at least 5 distinct
  characters, not on a common list, and not containing your own name or email.
  The meter on the sign-up page runs the same rules for feedback and is trusted
  by nothing.

To enable argon2id:

```bash
.venv/bin/pip install 'argon2-cffi>=23.1'
```

### Reset and change

- `POST /api/auth/password/change` — needs the current password.
- `POST /api/auth/password/forgot` — mints a single-use token. **The response is
  byte-identical whether or not the address has an account**, because an
  endpoint that says "no such user" is an account-existence oracle that needs no
  password to query.
- `POST /api/auth/password/reset` — redeems it. Single use, and the row is
  marked used *before* the password is written, so a token cannot be replayed
  even if the write fails.

There is **no mail transport in this project.** The token is written to the API's
**stdout**, where an operator with shell access can complete a reset. For local
work, `AEGIS_DEV_PASSWORD_RESET=1` additionally returns it in the response body;
the reset screen then renders it inside a block labelled DEVELOPMENT MODE.

> **The dev flag is an enumeration oracle by construction.** With it on, a real
> account gets a `dev_token` in the response and an unknown address does not.
> There is no way to hand out working tokens without revealing which addresses
> have accounts. It is off by default and refused outright when `AEGIS_AUTH=1`.

---

## 6. Existing accounts — what was preserved

Nothing was deleted, renamed or re-passworded. Specifically:

- `admin@aegis.local` / `changeme` — still the seeded platform **owner**, still
  what open mode acts as, still the account the sign-in screen offers.
- `supervisor@aegis.local` (admin), `analyst@aegis.local` (analyst),
  `viewer@aegis.local` (viewer), `mh.admin@aegis.local` (admin, second tenant),
  `mh.analyst@aegis.local` (analyst, second tenant) — all unchanged, same
  password, same role, same organisation.
- The four inherited roles hold **exactly** the capability set the ladder gave
  them, which is asserted rather than assumed:
  [`test_permissions.py::test_the_inherited_roles_keep_exactly_what_the_ladder_gave_them`](../services/api/tests/test_permissions.py).

Three accounts were **added** so each audience in the specification has one:
`citizen@aegis.local`, `police@aegis.local`, `researcher@aegis.local`.

All demo accounts share `AEGIS_DEMO_PASSWORD` (default `changeme`) and **none of
them are created when `AEGIS_AUTH=1`** — a real deployment ships no
known-password accounts.

---

## 7. Commands

```bash
make migrate                              # alembic upgrade head (needs DATABASE_URL)
make migrate-status                       # which revision, and what is available
make seed                                 # roles, permissions, org, owner, demo roster
make users                                # the roster and its roles
make set-password EMAIL=citizen@aegis.local   # reset a dev credential; prints it once
make db-shell                             # sqlite3 or psql on DATABASE_URL
```

The same tool has two more subcommands, for a fresh enforced deployment where
there is nobody to sign in as yet:

```bash
.venv/bin/python -m services.api.seed create ops@agency.gov.in admin --name "Ops Lead"
.venv/bin/python -m services.api.seed promote ops@agency.gov.in owner
```

Seeding is **idempotent** — running it twice creates nothing and changes
nothing. `set-password` and `promote` both revoke the account's sessions, so the
change takes effect immediately rather than whenever the old token expires.

### Retrieving or resetting a demo password

The passwords are configuration, not source. In order of preference:

1. `echo $AEGIS_DEMO_PASSWORD` — or the default, `changeme`.
2. `make set-password EMAIL=…` — generates a strong one and prints it **once**.
3. `POST /api/auth/password/forgot` with `AEGIS_DEV_PASSWORD_RESET=1`, or read
   the token from the API log.

There is no way to read an existing password back. That is the point of storing
a hash.

---

## 8. Viewing the database

### PostgreSQL — pgAdmin

Start the stack (`make up`), then connect pgAdmin to:

| Field | Value |
|---|---|
| Host | `127.0.0.1` |
| Port | `5432` (or `AEGIS_PG_PORT`) |
| Database | `aegis` (or `AEGIS_PG_DB`) |
| Username / password | `AEGIS_PG_USER` / `AEGIS_PG_PASSWORD` — dev-only values live in `.env.example`; **production credentials belong in neither** |

Then navigate **Servers → PostgreSQL → Databases → aegis → Schemas → public →
Tables** and open `users`, `roles`, `permissions`, `role_permissions`,
`user_sessions`, `investigations`, `audit_events`.

### PostgreSQL or SQLite — a terminal

```bash
make db-shell
```

It reads `DATABASE_URL`, picks `psql` or `sqlite3`, and prints the engine, host
and database name — **never the URL**, which carries a password.

Useful queries:

```sql
-- who can manage users, straight from the tables
SELECT r.name, p.code
FROM roles r
JOIN role_permissions rp ON rp.role_id = r.id
JOIN permissions p ON p.id = rp.permission_id
WHERE p.code = 'USER_MANAGE';

-- the roster (never select password_hash; there is nothing to see)
SELECT id, email, full_name, role, org_id, disabled, last_login_at FROM users;

-- live sessions
SELECT u.email, s.created_at, s.last_seen_at, s.ip
FROM user_sessions s JOIN users u ON u.id = s.user_id
WHERE s.revoked_at IS NULL AND s.expires_at > CURRENT_TIMESTAMP;

-- failed sign-ins in the last day
SELECT ts, actor, ip, detail FROM audit_events
WHERE action = 'login.failed' ORDER BY ts DESC LIMIT 50;
```

Prisma Studio and the Supabase dashboard are not applicable — this project uses
neither, and §17 asks not to introduce one for the sake of a viewer.

---

## 9. Routes

New:

```
POST   /api/auth/signup            create a CITIZEN account and sign in
POST   /api/auth/logout            revoke this session
POST   /api/auth/refresh           rotate the token
PATCH  /api/auth/me                edit your own name / phone
GET    /api/auth/sessions          your live sessions
DELETE /api/auth/sessions          sign out everywhere else
POST   /api/auth/password/change   current password -> new password
POST   /api/auth/password/forgot   mint a single-use reset token
POST   /api/auth/password/reset    redeem it
GET    /api/auth/roles             the role catalogue and its permissions
GET    /api/auth/status            what this deployment's auth is (unauthenticated)
GET    /api/auth/demo-accounts     the seeded roster — empty when AEGIS_AUTH=1
PATCH  /api/auth/users/{id}        change a role, enable/disable
GET    /api/investigations         the case list, scoped to what you may see
GET    /api/research/overview      aggregates and model evaluation (RESEARCH_READ)
```

Modified: every previously `require_role`-gated route now declares
`require_permission`. `GET /api/reports` and `GET /api/reports/{id}` narrow to
the caller's own rows unless they hold `REPORT_READ_ALL`; every
`/api/investigations/{id}` read does the same on `created_by`.

Frontend routes added: `/signup`, `/forgot-password`, `/reset-password`,
`/police/dashboard`, `/research/dashboard`, `/admin/dashboard` (with `/admin`
redirecting to it). `/dashboard` renders the right dashboard for the caller's
capabilities rather than duplicating four pages.

---

## 10. Environment variables

| Variable | Default | |
|---|---|---|
| `DATABASE_URL` | unset | SQLAlchemy URL. Unset ⇒ ephemeral temp SQLite. |
| `AEGIS_SECRET_KEY` | unset | HMAC signing key. Unset ⇒ a per-process key; tokens die with the process. **Set this in production.** |
| `AEGIS_AUTH` | `0` | `1` enforces authentication on every protected route. |
| `AEGIS_TOKEN_TTL` | `43200` | Session lifetime, seconds. |
| `AEGIS_ADMIN_EMAIL` / `AEGIS_ADMIN_PASSWORD` | `admin@aegis.local` / `changeme` | The seeded owner. |
| `AEGIS_DEMO_PASSWORD` | `changeme` | Shared password for the demo roster (open mode only). |
| `AEGIS_SIGNUP` | `true` | Whether public sign-up is accepted. |
| `AEGIS_PASSWORD_RESET_TTL` | `3600` | Reset-token lifetime, seconds. |
| `AEGIS_DEV_PASSWORD_RESET` | `false` | Return the reset token in the response. Development only; refused when `AEGIS_AUTH=1`. |
| `AEGIS_CORS_ORIGINS` | Vite's two | Comma-separated browser origins allowed to call the API. |
| `AEGIS_RATELIMIT` | `true` | The in-process limiter. |
| `AEGIS_EVIDENCE_DIR` | unset | Where uploaded bytes go. Set it whenever `DATABASE_URL` is set. |

**Never in the browser bundle:** `DATABASE_URL`, `AEGIS_SECRET_KEY`, and every
password above. Vite only inlines `VITE_*`; the SPA reads exactly one variable,
`VITE_API_BASE`, which is a URL.

---

## 11. Security measures

- **Passwords** — argon2id / pbkdf2-hmac-sha256, per-user salt, never plaintext,
  never in a response (`User.as_public()` is the only projection any route
  returns), never in the audit log, never in a log line.
- **No account-existence oracle** — a wrong email and a wrong password return the
  same 401 after verifying against a real hash, and `forgot` answers identically
  for both.
- **Brute-force backoff** (CWE-307) — five failures for one email+IP locks that
  identifier for five minutes.
- **Rate limiting** — sign-in, sign-up, refresh and every password route share
  the tightest bucket: 10 requests per minute per IP.
- **Revocable sessions** — see §4.
- **The role is read from the database on every request**, never from the token,
  so a demotion takes effect immediately.
- **No privilege escalation path** — sign-up has no `role` field at all and
  always creates a citizen; nobody may create or promote to a role at or above
  their own; nobody may change their own role or status; `PATCH /api/auth/me`
  accepts a name and a phone and has no other fields to write.
- **Ownership, in the query** — `REPORT_READ_ALL` / `INVESTIGATION_READ_ALL`
  decide scope, and the narrowing is a `WHERE` clause, not a filter over rows
  already loaded. A case you may not read **404s**, not 403s, so an id cannot be
  probed for existence.
- **Tenancy** — enforced in the repository layer (`orgs.scope_query`,
  `EvidenceStore`), not in the route.
- **Audit log** — append-only, records failures as well as successes, carries IP
  and user agent, and holds no secret of any kind.
- **Hardening headers** — CSP `default-src 'none'`, `X-Frame-Options: DENY`,
  `nosniff`, `Referrer-Policy: no-referrer` on every response.
- **CORS** — an explicit origin allow-list, never `*`.
- **Backend-first** — every frontend guard is mirrored by a
  `require_permission` on the route behind it. The client hides doors; the
  server closes them.

The security audit in §38–39 of the specification is executed as tests, one case
per line: [`services/api/tests/test_rbac.py`](../services/api/tests/test_rbac.py).

---

## 12. Limitations and TODOs

Stated rather than glossed, per invariant 7.

1. **The token lives in `localStorage`.** See §4 for why, what bounds it, and
   what the change would be.
2. **No email verification.** `users.email_verified` exists and is false for
   everyone; no route gates on it. There is no mail transport to verify with, so
   the column records the absence rather than claiming a check that never
   happened.
3. **No mail transport at all**, so password reset is completed from the server
   log or the dev flag. That flag is an enumeration oracle by construction (§5).
4. **Permissions are per-role, not per-user.** There are no per-user grants and
   no deny rules, so "this one analyst may also read the audit log" needs a new
   role.
5. **`INVESTIGATION_READ_ASSIGNED` has no assignment table yet.** It is granted
   to `police` and currently behaves like `READ_ALL` within the organisation. A
   real case-assignment model is Phase 7 work; the permission exists so the
   route does not have to be rewritten when it lands.
6. **No cross-organisation view of investigations, even for an owner** — task
   1.5 chose that deliberately and this change did not undo it.
7. **The research surface is aggregation, not differential privacy.** Clusters
   below three cases are withheld; that is a threshold, not a formal guarantee,
   and this project does not claim one.
8. **No MFA, no OAuth, no social sign-in.** The sign-in screen shows no social
   buttons because there is no social login behind them.
