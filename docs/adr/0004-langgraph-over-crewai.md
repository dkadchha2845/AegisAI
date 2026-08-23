# ADR-0004 — LangGraph for orchestration

**Status:** Accepted · **Date:** 2026-08-23 · **Confirms:** master §22

## Context
Agent orchestration needs branching, shared state, parallel fan-out, retries,
timeouts, bounded recursion and reproducible traces. Candidates: LangGraph,
CrewAI, a hand-rolled asyncio DAG.

## Decision
LangGraph.

## Rationale
1. **Most AegisAI "agents" are not LLMs.** OCR, WHOIS, androguard, XGBoost and
   Cypher queries are deterministic functions. CrewAI's role-playing,
   conversation-driven abstraction models them awkwardly. LangGraph's
   state-machine framing fits a mixed deterministic/LLM system naturally.
2. **Explicit state.** `InvestigationState` *is* the graph state. One contract,
   no hidden agent memory.
3. **Reproducibility.** Deterministic execution with fixed seeds is what makes
   the ablation study (Phase 9.3) valid. Emergent conversational delegation is
   the opposite of what a research harness needs.
4. **Checkpointing** gives crash-resume and time-travel debugging for free.
5. **A hand-rolled DAG** would end up reimplementing LangGraph badly, and adds
   no research value.

## Consequences
- Python 3.11+ required → Task 0.2 becomes a blocker.
- LangChain-ecosystem dependency weight. Mitigated by using LangGraph's core
  graph primitives only, and keeping the LLM behind our own `LLMBackend`
  protocol so no provider or chain abstraction leaks into agent code.

## Guard
No agent may import a LangChain LLM wrapper directly. All model access goes
through `LLMBackend` (master §22: do not hard-code around one provider).
