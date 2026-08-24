# AegisAI — agent instructions

**The working rules live in [`CLAUDE.md`](./CLAUDE.md). Read that file.**

This file exists because several tools look for `AGENTS.md` by convention. It is
deliberately a pointer and not a copy.

It started as a copy, and that lasted about half an hour before the two files
disagreed: `CLAUDE.md` was corrected to stop naming a fixed test count, and this
one still named one — off by more than two hundred by the time anyone looked.
Duplicating the rules creates a second thing to keep true, and this repository
already treats documentation drift as a defect (see the three drifts recorded
against task 0.7 in [`docs/TASKS.md`](./docs/TASKS.md)). One source, one place
to fix.

## The short version

```bash
make gates      # the four gates: tests · contract · typecheck · build
make check      # the gates plus ruff and mypy
make up         # Postgres, Neo4j, Qdrant, Redis
make api        # the API on :8000
make web        # the frontend on :5173
```

Use `.venv/bin/python`, never system python.

A task is not done when the code exists. It is done when the acceptance criteria
pass, `make gates` is green, **and the behaviour has been exercised in the
running application** — the full checklist is in `CLAUDE.md`.

## Where to read next

| File | What it settles |
|---|---|
| [`CLAUDE.md`](./CLAUDE.md) | Invariants, gates, definition of done, security rules |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | The agent graph and the `InvestigationState` contract |
| [`docs/TASKS.md`](./docs/TASKS.md) | What is done, what is next, and the evidence for each |
| [`docs/adr/`](./docs/adr/) | Every deviation from the plan, with its justification |
