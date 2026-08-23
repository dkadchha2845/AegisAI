# ADR-0002 — Adopt Neo4j, retain NetworkX as the offline fallback

**Status:** Accepted · **Date:** 2026-08-23 · **Aligns with:** master §14

## Context
The inherited intel layer uses in-process NetworkX: community detection,
centrality, link prediction, cluster risk. It works and is tested. But it is
rebuilt per process and cannot support cross-case memory, concurrent writes, or
a graph large enough to be interesting.

## Decision
Migrate to Neo4j behind the existing `intel/repository.py` interface. Keep the
NetworkX implementation as a registered fallback selected automatically when
Neo4j is unreachable.

## Rationale
1. **Cross-case memory (master §15) is impossible without persistence.** The
   "this UPI ID appeared in 3 prior investigations" capability is a headline
   feature and a research claim (C3/RQ3).
2. **Cypher is demonstrable.** A live query during a viva is worth more than a
   diagram.
3. **The interface already exists**, so this is a swap, not a redesign — the
   inherited repository abstraction was built for exactly this.
4. **The fallback preserves the inherited invariant** that a clean clone boots
   and answers with no infrastructure. Losing that would make the demo fragile
   and violate "degradation is explicit".

## Consequences
- Docker becomes a hard dependency for the full experience (Task 0.4).
- Two implementations to keep in sync — mitigated by running the **same test
  suite against both backends** (Task 3.1 acceptance criterion).
- Neo4j GDS licensing must be checked before relying on its algorithms.

## Revisit if
Neo4j GDS licensing blocks the analytics, in which case NetworkX stays primary
for analytics with Neo4j as the store — and the paper says so.
