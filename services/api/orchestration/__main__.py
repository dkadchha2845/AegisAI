"""
Render the investigation graph without running it.

    .venv/bin/python -m services.api.orchestration            # Mermaid
    .venv/bin/python -m services.api.orchestration --summary  # which agents are live
    .venv/bin/python -m services.api.orchestration --exclude threat_intel

Acceptance criterion for task 1.3, and the thing that makes the architecture
legible in thirty seconds — paste the output into any Markdown renderer, or into
the paper. Task 7.3 renders the same graph live, per investigation, with node
status; this is the static picture of what *would* run.

It deliberately does not import any agent. The graph's shape comes from the
registry, so an empty registry renders the tier skeleton and a full one renders
the same skeleton — which is the point of building from the registry rather than
from a hand-written node list, and is worth being able to see.
"""

from __future__ import annotations

import argparse
import json
import sys

from services.api.orchestration.graph import graph_summary, render_mermaid


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m services.api.orchestration", description=__doc__)
    ap.add_argument(
        "--summary",
        action="store_true",
        help="print the registered agents by tier instead of the diagram",
    )
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="AGENT",
        help="omit an agent, as the Phase 9 ablations do; repeatable",
    )
    args = ap.parse_args(argv)

    if args.summary:
        print(json.dumps(graph_summary(), indent=2))
    else:
        print(render_mermaid(exclude=args.exclude))
    return 0


if __name__ == "__main__":
    sys.exit(main())
