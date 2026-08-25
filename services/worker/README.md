# services/worker

Celery workers for analysis that must not run in the request path. Built in
task 1.8; see `docs/TASKS.md` for what was measured.

## Running one

```bash
.venv/bin/celery -A services.worker.celery_app worker -Q fast,slow,sandbox -c 4 --loglevel=info
```

or `make worker`, which is the same line. The API needs no restart to notice:
it probes the broker per submission (cached ten seconds) and switches to the
queue the moment one answers.

## Three queues by cost class

| Queue | For | Budget |
|---|---|---|
| `fast` | investigations over text, URLs and images; retries; cache warms | seconds |
| `slow` | audio, video, batch re-scoring | minutes |
| `sandbox` | **APK static analysis** — network-less container, read-only mount | minutes, isolated |

Which queue an investigation lands on is decided by
`services/api/jobs/routing.py`, from the filename and the declared MIME type —
the only things known at dispatch, because the magic-byte sniff happens on the
graph's classifier node, on the far side of the decision.

**That makes the cost class a scheduling hint, not a security boundary.** An APK
renamed `photo.jpg` runs on `fast`. Today that costs a worker slot and nothing
else, because `sandbox` is a queue name and not yet an isolated container. Task
2.8 brings the container, and when it does the isolation has to be enforced
where the sniffed type is known — inside the agent, or by re-dispatching after
the classifier node — and not by trusting the guess made at submission. See
`docs/ARCHITECTURE.md` §8.

## Without a broker

Nothing here is required. With no reachable Redis the API runs the graph on its
own event loop exactly as it did after task 1.6, and says so:
`execution.mode: in-process` on `/api/health`, and `queue:in_process` on the 202
that accepted the submission. What is lost in that mode is durability of the
*run* — a restart loses an investigation in flight — not the case file, which is
written to the evidence store before the graph starts.

## Crash safety

"A worker crash loses no work" is four settings in `celery_app.py`, not code:
`task_acks_late`, `task_reject_on_worker_lost`, `worker_prefetch_multiplier = 1`,
and a bounded retry budget with a dead-letter list underneath it. They are one
decision — changing any of them alone reintroduces the loss — and
`test_jobs_worker.py` asserts each by name with the reason attached.

Because a job can therefore run twice, everything a run writes is keyed on the
case id: the journal list, the state snapshot, and the evidence-store rows,
which `EvidenceStore.save` clears before rewriting. An agent that ever acquires
a side effect outside those keys — a takedown request, an alert to a bank —
needs its own idempotency key.

## Dead letters

A job that exhausts its retries is pushed onto `aegis:inv:dlq` (most recent 500)
rather than dropped, and the count is on `/api/health` under `execution`.

```bash
make dlq
```
