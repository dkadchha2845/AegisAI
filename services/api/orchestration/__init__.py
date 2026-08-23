"""
LangGraph investigation graph.

Nodes are agents; edges are conditional on `InvestigationState`. A graph rather
than a pipeline because the work genuinely branches: an APK agent must not run
on an audio file, URL/threat-intel/graph lookups are independent and should run
concurrently, and a discovered domain may deserve its own bounded sub-investigation.

Every node runs under one policy — per-agent timeout, bounded retry on transient
errors only, and failure that degrades rather than aborts. A failing agent
appends to `state.degraded` and the investigation still returns an answer.

Determinism matters here beyond tidiness: identical state plus fixed seeds must
produce identical output, or the ablation study in Phase 9 measures noise.

Populated in Phase 1. See docs/ARCHITECTURE.md §2.
"""
