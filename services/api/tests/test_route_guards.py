"""
Every route says how it is guarded (audit S-07).

`CLAUDE.md` said every route declares `require_permission(...)`. Twenty-five did
not, and nothing noticed, because "no guard" was the silent default. Now there
are four declared answers — a permission, any signed-in user, a resource
capability (a live session's token, a vault token), or `public(reason)` — and
this test reads each route's answer off FastAPI's own dependency tree.

Two failures it exists to produce:
  * a route with no guard at all;
  * a route that becomes public without anyone reviewing it — the public set
    is pinned below, so adding one means editing this file, in a diff a
    reviewer will see.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Set, Tuple

from fastapi.routing import APIRoute, APIWebSocketRoute

from services.api.main import app


def _calls(dependant: Any) -> Iterable[Any]:
    for dep in dependant.dependencies:
        yield dep.call
        yield from _calls(dep)


def _guards(route: Any) -> List[Tuple[Any, ...]]:
    found = [c.aegis_guard for c in _calls(route.dependant) if hasattr(c, "aegis_guard")]
    endpoint_guard = getattr(getattr(route, "endpoint", None), "aegis_guard", None)
    if endpoint_guard:
        found.append(endpoint_guard)
    return found


def _flatten(routes: Iterable[Any]) -> Iterable[Any]:
    """Every concrete route, however the installed FastAPI stores them.

    FastAPI 0.141 keeps an included router as one `_IncludedRouter` entry in
    `app.routes` and resolves its routes lazily (`effective_candidates()`).
    The first version of this test iterated `app.routes` directly, found only
    the two routes declared on the app, and passed while seeing none of the
    other seventy — so it walks into routers explicitly, by duck type, and the
    count below proves it reached them.
    """
    for r in routes:
        expand = getattr(r, "effective_candidates", None)
        if callable(expand):
            yield from _flatten(expand())
            # WebSocket routes are not among the HTTP candidates; they are
            # still on the router the wrapper was built from.
            original = getattr(r, "original_router", None)
            for sub in getattr(original, "routes", []):
                if isinstance(sub, APIWebSocketRoute):
                    yield sub
        elif isinstance(r, (APIRoute, APIWebSocketRoute)) or hasattr(r, "dependant"):
            yield r


def _api_routes() -> List[Any]:
    return [r for r in _flatten(app.routes) if str(getattr(r, "path", "")).startswith("/api")]


def test_the_walk_reaches_every_route() -> None:
    """73 routes at the time of writing (`docs/PRD.md` §9). A walk that finds
    fewer is not checking what it claims to."""
    assert len(_api_routes()) >= 73


def _key(route: Any) -> str:
    methods = sorted(getattr(route, "methods", None) or {"WS"})
    return f"{','.join(methods)} {route.path}"


#: The routes open to anonymous callers on purpose. Each declares its reason
#: with `public(...)` at the route; this list is the reviewed inventory.
EXPECTED_PUBLIC: Set[str] = {
    "GET /api/health",
    "GET /api/model/card",
    "POST /api/analyze/text",
    "POST /api/analyze/upi",
    "POST /api/analyze/file",
    "POST /api/analyze/image",
    "POST /api/analyze/audio",
    "GET /api/analyze/knowledge/search",
    "POST /api/analyze/knowledge/ask",
    "GET /api/analyze/knowledge/docs",
    "POST /api/auth/signup",
    "POST /api/auth/login",
    "POST /api/auth/password/forgot",
    "POST /api/auth/password/reset",
    "GET /api/auth/demo-accounts",
    "GET /api/auth/status",
    "GET /api/shield/helplines",
    "POST /api/shield/verify",
    "POST /api/shield/preserve",
    "GET /api/shield/awareness",
    "POST /api/session",
}


def test_every_route_declares_its_guard() -> None:
    unguarded = [_key(r) for r in _api_routes() if not _guards(r)]
    assert not unguarded, (
        "routes with no declared guard — add require_permission(...), "
        "get_current_user, a capability dependency, or public(reason): "
        + ", ".join(unguarded)
    )


def test_the_public_routes_are_exactly_the_reviewed_ones() -> None:
    public = {
        _key(r) for r in _api_routes()
        if any(g[0] == "public" for g in _guards(r))
    }
    assert public == EXPECTED_PUBLIC, (
        f"new public routes: {sorted(public - EXPECTED_PUBLIC)}; "
        f"no longer public: {sorted(EXPECTED_PUBLIC - public)}"
    )


def test_every_public_route_says_why() -> None:
    for route in _api_routes():
        for guard in _guards(route):
            if guard[0] == "public":
                assert len(guard[1]) > 20, f"{_key(route)}: a public route needs a real reason"


def test_no_session_route_is_open_by_id_alone() -> None:
    """The specific hole S-07 found: a live session's id is in every URL, so a
    route that needs only the id hands out someone's call transcript."""
    for route in _api_routes():
        if not route.path.startswith("/api/session/"):
            continue
        kinds = {g[0] for g in _guards(route)}
        assert kinds & {"capability", "permission"}, (
            f"{_key(route)} is reachable by session id alone"
        )
