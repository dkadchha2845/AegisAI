# Deploying AegisAI

Putting the frontend and the backend on one domain, with TLS, on a single
server. Read [`AUTH.md`](AUTH.md) for what the environment variables here mean.

Roughly 45 minutes end to end, most of it waiting for `pip install`.

---

## The shape of it

```
                    ┌──────────────────────────────────────────┐
   your domain      │  Caddy  :443                             │
   ───────────────▶ │    ├── /api/*  ──▶ uvicorn 127.0.0.1:8000│
   aegisai.in       │    └── /*      ──▶ /srv/aegisai/web (SPA)│
                    └──────────────────────────────────────────┘
                                          │
                              ┌───────────┴───────────┐
                         PostgreSQL              Redis + worker
                         (required)               (optional)
```

**One origin, not two.** The SPA and the API share a scheme and a host, so
every request the browser makes is same-origin. That is worth doing
deliberately:

- no CORS configuration to keep in step with reality,
- no preflight round trip before every write,
- the session token is never sent cross-site,
- one certificate, one DNS record, one thing to renew.

The alternative — the SPA on Vercel and the API on Render — needs two hosts,
`AEGIS_CORS_ORIGINS` maintained by hand, and a cross-site token. It is a fine
shape for a large team and the wrong one for this.

**What you need.** A VPS with **2 vCPU and 4 GB RAM** runs this comfortably
without the fine-tuned model. With the model, give it **8 GB** — the checkpoint
is 915 MB on disk and wants room in memory beside torch. Hetzner CX22 (~€4/mo),
DigitalOcean 4 GB (~$24/mo) and Oracle Cloud's always-free ARM tier all work.
Ubuntu 24.04 throughout below.

---

## 1. Point the domain at the server

Do this first — DNS takes time to propagate, and Caddy cannot get a certificate
until it resolves.

In **GoDaddy → My Products → your domain → DNS → Manage Zones**:

| Type | Name | Value | TTL |
|---|---|---|---|
| `A` | `@` | your server's IPv4 | 600 |
| `A` | `www` | your server's IPv4 | 600 |

Delete any existing `A` or `CNAME` on `@` or `www` first — GoDaddy parks new
domains on its own forwarding record, and a leftover one silently wins.

> **Do not turn on GoDaddy's "Domain Forwarding".** It answers on port 80 with a
> redirect, so Caddy's certificate challenge never reaches your server and TLS
> issuance fails with an error that does not mention forwarding.

Check it from your laptop before going further:

```bash
dig +short aegisai.in A
```

That must print your server's IP. If it prints nothing, wait — GoDaddy is
usually minutes, occasionally an hour.

---

## 2. Prepare the server

SSH in as root, then:

```bash
adduser --system --group --home /srv/aegisai aegis
apt update && apt install -y python3.12 python3.12-venv python3-pip git \
    postgresql postgresql-contrib redis-server curl
```

Python **3.12 or newer** is required — see task 0.2. `python3 --version` on
Ubuntu 24.04 is already 3.12.

---

## 3. Create the database

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE aegis LOGIN PASSWORD 'pick-something-long-here';
CREATE DATABASE aegis OWNER aegis;
\q
```

Keep that password — it goes into `DATABASE_URL` in step 5. Postgres listens on
loopback only by default on Ubuntu, which is what you want; nothing needs to
reach it from outside the box.

---

## 4. Get the code and build both halves

```bash
mkdir -p /srv/aegisai/{app,web,evidence}
chown -R aegis:aegis /srv/aegisai
sudo -u aegis git clone https://github.com/dkadchha2845/AegisAI.git /srv/aegisai/app
cd /srv/aegisai/app
```

**Backend:**

```bash
sudo -u aegis python3 -m venv .venv
sudo -u aegis .venv/bin/pip install -r services/api/requirements.txt
sudo -u aegis .venv/bin/pip install 'psycopg[binary]>=3.2' 'argon2-cffi>=23.1'
```

Those last two are optional in the repo and both wanted here. `psycopg` is the
PostgreSQL driver — SQLAlchemy loads a driver for the URL it is given, and
without it `DATABASE_URL` fails at startup. `argon2-cffi` upgrades password
hashing from pbkdf2 to argon2id; existing hashes keep verifying and each account
is re-hashed the next time its owner signs in. `/api/health` reports which is
serving under `auth.password_hash`.

**Frontend** — needs Node only to build; the server never runs it:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt install -y nodejs
cd /srv/aegisai/app/apps/web
sudo -u aegis npm ci
sudo -u aegis env VITE_API_BASE= npm run build
cp -r dist/* /srv/aegisai/web/
chown -R aegis:aegis /srv/aegisai/web
```

> `VITE_API_BASE=` — **empty, and it matters.** It is what makes the built
> bundle call `/api/...` on whatever host served it instead of
> `http://localhost:8000`. Leave it out and the deployed site tries to reach
> your laptop. It is read at *build* time, not at runtime, so changing it later
> means rebuilding.

---

## 5. Configure

```bash
sudo -u aegis cp infra/deploy/env.production.example /srv/aegisai/app/.env
sudo -u aegis chmod 600 /srv/aegisai/app/.env
sudo -u aegis .venv/bin/python -c "import secrets; print(secrets.token_hex(32))"
sudo -u aegis nano /srv/aegisai/app/.env
```

Fill in the four required values: `AEGIS_SECRET_KEY` (the line you just
generated), `DATABASE_URL` (with the password from step 3),
`AEGIS_ADMIN_EMAIL`, `AEGIS_ADMIN_PASSWORD`. Leave `AEGIS_AUTH=1` as it comes.

**`AEGIS_AUTH=1` is the line that matters most.** Without it the API acts as the
seeded owner for any request with no token — correct for a laptop demo, an open
door on the public internet. Setting it also stops the demo roster being seeded,
so nothing ships with a known password.

---

## 6. Create the schema, then the first account

```bash
cd /srv/aegisai/app
sudo -u aegis bash -c 'set -a; . .env; set +a; .venv/bin/alembic upgrade head'
```

The owner account is created from `AEGIS_ADMIN_*` on the first boot. Everything
else you provision from the running app, or from the CLI:

```bash
sudo -u aegis bash -c 'set -a; . .env; set +a; .venv/bin/python -m services.api.seed users'
```

> **Migrating a database you already have?** Bring it forward *before* starting
> the API — `create_all` adds tables and never columns, so the API refuses to
> boot on a schema behind the code and tells you which command to run. A
> database built by `create_all` with no revision history needs
> `alembic stamp 0002` first. See [`AUTH.md`](AUTH.md) §1.

---

## 7. Optional: the fine-tuned model

Skip this and the API serves the lexical classifier and says so on
`/api/health` (`clf:lexical_fallback`). That is a real, honest degradation, not
a broken deployment — but on English/Hinglish scam scoring the checkpoint
measured **macro-F1 0.767 against the lexical model's 0.375**, so it is worth
the disk.

`ml/artifacts/` is gitignored, so copy it from a machine that has it. Only
`stage-classifier/` and the two JSON files are needed at serve time —
`_train/` is 2.7 GB of training scratch and is not:

```bash
rsync -avz --exclude '_train' ml/artifacts/ root@YOUR_SERVER:/srv/aegisai/artifacts/
```

Then set `AEGIS_ARTIFACTS=/srv/aegisai/artifacts` in `.env`, and
`chown -R aegis:aegis /srv/aegisai/artifacts`. Serving the checkpoint needs
`pip install torch transformers` (~2 GB of wheels) and is why the 8 GB box is
the recommendation.

---

## 8. Start the API

```bash
cp infra/deploy/aegis-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now aegis-api
systemctl status aegis-api --no-pager
```

The first start takes up to a minute: the lifespan hook warms the classifier,
the retriever and every agent before accepting a request, because an agent that
warms lazily is one that times out for whoever arrives first after a restart.

```bash
curl -s localhost:8000/api/health | python3 -m json.tool | head -20
```

Optionally the Celery worker, which takes investigations off the request path.
Without it the graph runs in the API process — identical results, one at a time:

```bash
cp infra/deploy/aegis-worker.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now aegis-worker
```

---

## 9. Caddy, and TLS

Caddy obtains and renews a Let's Encrypt certificate by itself. There is no
certbot step and no cron job.

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy

cp /srv/aegisai/app/infra/deploy/Caddyfile /etc/caddy/Caddyfile
sed -i 's/aegisai\.in/YOUR-DOMAIN.in/g' /etc/caddy/Caddyfile
systemctl reload caddy
```

Open the firewall if one is on:

```bash
ufw allow 80,443/tcp && ufw allow OpenSSH && ufw --force enable
```

Port 80 has to stay open — Let's Encrypt uses it for the challenge, and Caddy
redirects it to 443 afterwards.

---

## 10. Verify

```bash
curl -s https://YOUR-DOMAIN.in/api/health | python3 -m json.tool | head -25
```

Four things to read, in order:

| Field | Must say | If it doesn't |
|---|---|---|
| `auth.enforced` | `true` | `AEGIS_AUTH=1` is missing — **anyone can act as the owner** |
| `database.persistent` | `true` | `DATABASE_URL` is not being read; check `.env` permissions |
| `evidence_storage.persistent` | `true` | set `AEGIS_EVIDENCE_DIR` |
| `degraded` | `[]`, or only tags you chose | see below |

`clf:lexical_fallback` means step 7 was skipped. `queue:no_workers` means the
worker unit is not installed. Both are choices; neither is a fault.

Then in a browser, on the real domain:

1. The landing page loads over `https://` with a valid certificate.
2. **Get started** → create an account → it lands on the citizen dashboard.
3. Sign out → the navbar shows Sign in / Get started again.
4. Press back → it bounces to `/login`.
5. Type `/admin/dashboard` → it bounces too.
6. **Live Protection** → the WebSocket connects. This is the one thing a
   same-origin deployment used to break, so check it specifically: open the
   browser console and confirm no `SyntaxError` on `new WebSocket`.
7. Sign in as your admin account → `/admin/dashboard` → the roster loads.

The sign-in screen shows **no demo accounts**, because `AEGIS_AUTH=1` means
none were seeded and `/api/auth/demo-accounts` returns an empty list.

---

## Deploying a change

```bash
cd /srv/aegisai/app
sudo -u aegis git pull
sudo -u aegis .venv/bin/pip install -r services/api/requirements.txt
sudo -u aegis bash -c 'set -a; . .env; set +a; .venv/bin/alembic upgrade head'
cd apps/web && sudo -u aegis npm ci && sudo -u aegis env VITE_API_BASE= npm run build
cp -r dist/* /srv/aegisai/web/ && chown -R aegis:aegis /srv/aegisai/web
systemctl restart aegis-api
```

Migrate **before** restarting, for the reason in step 6.

---

## Backups

The database is the only thing that cannot be rebuilt from git.

```bash
cat > /etc/cron.daily/aegis-backup <<'SH'
#!/bin/sh
d=/srv/aegisai/backups; mkdir -p "$d"
sudo -u postgres pg_dump aegis | gzip > "$d/aegis-$(date +%F).sql.gz"
find "$d" -name 'aegis-*.sql.gz' -mtime +30 -delete
SH
chmod +x /etc/cron.daily/aegis-backup
```

Back up `/srv/aegisai/evidence` too — those are the bytes of uploaded
artefacts, and a case without them is a case that outlived its own evidence.

---

## Where this stops

Stated plainly, per invariant 7.

- **One box, no redundancy.** A restart is downtime of a few seconds; a disk
  failure is a restore from backup. Fine for a capstone and a pilot, not an SLA.
- **No CDN.** The SPA is 1.6 MB and Caddy serves it compressed from one region.
  Users far from that region will feel it.
- **`ProtectSystem=full` is not a sandbox.** The APK agent's stated design is a
  network-less container with a read-only mount; this deployment does not
  provide one, so do not enable APK analysis on it.
- **Rate limiting is in-process.** Two API workers means two independent
  limiters, each with the full allowance. It is sized to stop a script, not a
  distributed one.
- **No log aggregation, no metrics, no alerting.** `journalctl -u aegis-api`
  and `/api/health` are what you have.
