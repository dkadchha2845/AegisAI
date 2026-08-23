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

Populated in Phase 0.4 (compose stack) and Phase 3 (the migrations).
See docs/ARCHITECTURE.md §8 and docs/adr/0002-neo4j-with-networkx-fallback.md.
"""
