# services/worker

Celery workers for analysis that must not run in the request path.

Three queues by cost class:

| Queue | For | Budget |
|---|---|---|
| `fast` | retries, cache warms, graph enrichment | seconds |
| `slow` | video keyframing, batch re-scoring | minutes |
| `sandbox` | **APK static analysis** — network-less container, read-only mount | minutes, isolated |

The `sandbox` queue is a security boundary, not a performance one: uploaded APKs
are analysed statically and **never executed**. See docs/ARCHITECTURE.md §8.

Populated in Phase 1.8.
