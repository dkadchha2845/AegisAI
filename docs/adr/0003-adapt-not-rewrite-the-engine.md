# ADR-0003 — Adapt the inherited engine into agents; do not rewrite it

**Status:** Accepted · **Date:** 2026-08-23

## Context
AegisAI's architecture is agent-based. The inherited KAVACH engine is a linear
pipeline of ~50 modules covering stage classification, coercion indexing, threat
fusion, the Digital Twin forecast, identity passport checks, spoofing intel and
script similarity. It carries 84 passing tests and a fine-tuned MuRIL checkpoint
at macro-F1 0.767 on a zero-leak held-out-archetype split.

The tempting move is to rewrite it "properly" as agents.

## Decision
Wrap each engine capability in a **thin adapter** that implements the `Agent`
protocol and emits `AgentResult`. Engine internals are not modified.

## Rationale
1. **The tests are the asset.** 84 tests encode months of false-positive
   tuning that is not recoverable from reading the code. A rewrite discards
   that evidence and cannot prove equivalence.
2. **The checkpoint is expensive.** The MuRIL model's promotion was gated on
   measured F1, and it was once suppressed for weeks by a stale benchmark file.
   Its serving path should not be disturbed casually.
3. **Adapters make migration incremental and reversible.** Old path and new
   orchestrator can run side by side and be compared (which is itself
   Experiment 3's setup).
4. **It is the fastest route to M1** — the agent skeleton gets seven real agents
   on day one instead of stubs.

## Consequences
- Some adapters will look thin and slightly awkward. Acceptable.
- Engine internals keep their original vocabulary (`StateFrame`, stages). The
  adapter translates; the contract stays clean.
- Genuine refactoring of engine internals is allowed **later**, one module at a
  time, with the 84 tests as the guard.

## Acceptance guard
All 84 inherited tests must pass **unmodified** after adaptation. If a test has
to change, the adaptation is wrong.
