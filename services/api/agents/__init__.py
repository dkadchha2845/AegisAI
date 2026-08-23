"""
Specialised investigation agents.

An "agent" here is **not** necessarily an LLM. Most are deterministic: OCR, a
WHOIS lookup, androguard, a gradient-boosted model, a Cypher query. What makes
something an agent is that it implements the `Agent` protocol and returns an
`AgentResult` — a typed record carrying findings, confidence, the features it
contributes to the risk model, its latency, and its provenance.

That uniform shape is what makes three things possible at once: the orchestrator
can fan out over agents without knowing what they do, the UI can render any
agent's panel generically, and the paper can compute per-agent success rates and
inter-agent disagreement.

Populated in Phase 1 (base protocol + registry) and Phase 2 (the agents
themselves). See docs/ARCHITECTURE.md §3 and docs/TASKS.md phases 1-2.
"""
