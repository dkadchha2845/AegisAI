# infra/

| Directory | Holds |
|---|---|
| `compose/` | Docker Compose stacks — Postgres, Neo4j, Qdrant, Redis |
| `deploy/` | Production config — Caddyfile, systemd units, `.env` template. See [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md) |
| `docker/` | Dockerfiles for the API, the worker, and the sandbox image |
| `seeds/` | Deterministic seed data so a fresh stack is demoable immediately |

Kubernetes is deliberately absent. The master context calls for it only if
deployment scale actually requires it, and it does not.

See docs/TASKS.md 0.4 and 10.3.
