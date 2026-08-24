"""
Backing-store adapters: PostgreSQL, Neo4j, Qdrant, Redis.

Each store is reached through an interface with a working fallback, so the
inherited invariant holds — a clean clone with no infrastructure still boots and
answers, in a measurably worse mode that /api/health reports:

    PostgreSQL -> SQLite            Neo4j  -> in-process NetworkX
    Qdrant     -> in-house TF-IDF   Redis  -> in-process dict/LRU

Tenant isolation (`org_id`) is enforced **here**, in the repository layer, not
in the routes. A route that forgets to scope a query is a bug; a repository that
cannot express an unscoped query is a design.

PostgreSQL is the first of the four to be real. Task 1.5 put the evidence store
here — `models.py` holds its six tables, `evidence.py` is the repository, and
`../migrations` moves an existing database forward. The other three still have
`in_use: false` on /api/health, and `probe.py` says so rather than implying
otherwise.

The tenant rule is worth restating because this is where it is implemented:
`EvidenceStore` binds one `org_id` at construction and no method accepts
another, so an unscoped query is not something a caller can write. Every table
in `models.py` carries a non-nullable `org_id`, with no exceptions —
`test_evidence_store.py` asserts both, structurally, so a seventh table cannot
become the one place the boundary does not exist.

See docs/ARCHITECTURE.md §7–§8 and docs/adr/0002-neo4j-with-networkx-fallback.md.
"""
