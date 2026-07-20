"""
Coach — retrieval over a curated library, never generation.

`CoachSuggestion.line` is the sentence a frightened person is told to say out
loud, mid-call, to someone impersonating the police. That is not a place for a
language model to improvise. Every line comes from `coach_library.json`, which
is human-reviewed, and is delivered verbatim.

The LLM's role, if one is configured at all, is bounded to *ranking* — picking
which pre-approved line best fits the last few turns. If it is unavailable,
unreachable, or returns anything other than an index into the candidate list,
the stage-ordered default is used and nothing is lost but a little precision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import settings
from .store import get_kb

LIBRARY_PATH = settings.knowledge_dir / "coach_library.json"


@dataclass
class CoachOut:
    line: str
    tactic: str
    why: str
    sources: list[str] = field(default_factory=list)
    urgency: str = "info"


class CoachLibrary:
    def __init__(self, path: Path | None = None):
        self.path = path or LIBRARY_PATH
        self.by_stage: dict[str, list[CoachOut]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        blob = json.loads(self.path.read_text(encoding="utf-8"))
        for entry in blob.get("lines", []):
            out = CoachOut(
                line=entry["line"],
                tactic=entry["tactic"],
                why=entry["why"],
                sources=list(entry.get("sources", [])),
                urgency=entry.get("urgency", "info"),
            )
            self.by_stage.setdefault(entry["stage"], []).append(out)

    def suggest(
        self,
        stage: str,
        *,
        escalation: int = 0,
        victim_state: str = "UNKNOWN",
    ) -> CoachOut | None:
        """Pick a line for the current stage.

        `escalation` walks further down the stage's list each time the same
        stage produces another suggestion — repeating the identical sentence
        after it visibly failed is worse than saying nothing.
        """
        candidates = self.by_stage.get(stage)
        if not candidates:
            return None

        # A complying victim is further along than the stage alone implies;
        # skip straight to the firmest line available for the stage.
        if victim_state == "COMPLIANT":
            escalation = max(escalation, len(candidates) - 1)

        chosen = candidates[min(escalation, len(candidates) - 1)]

        # Attach live citations from the knowledge base on top of the ones
        # authored into the library. Same mechanism the Trust Passport uses,
        # so a judge asking "where did that come from?" gets one answer.
        hits = get_kb().search(chosen.tactic + " " + chosen.why, k=2)
        extra = [h.chunk.source for h in hits if h.chunk.source not in chosen.sources]
        return CoachOut(
            line=chosen.line,
            tactic=chosen.tactic,
            why=chosen.why,
            sources=chosen.sources + extra[:1],
            urgency=chosen.urgency,
        )


_library: CoachLibrary | None = None


def get_coach() -> CoachLibrary:
    global _library
    if _library is None:
        _library = CoachLibrary()
    return _library
