"""
Prompts as versioned files (T-14, audit D-05).

**Why.** The explainer's and the assistant's prompts were string literals in
`llm.py`. An explanation could not be traced to the prompt that produced it,
and a reworded prompt left no mark except a diff. Each prompt is now one
`.prompt` file here with an `id` and a `version` in its header, and every LLM
answer records `<id>@<version>` beside the backend that produced it.

**Format.**

    ---
    id: explain
    version: 1
    purpose: one line
    ---
    === system ===
    <system prompt, verbatim>
    === user ===
    <user template, with {{placeholders}}>

The text between the markers is used byte for byte — including the runs of
spaces the original concatenated strings produced — so moving a prompt into a
file cannot change what a model is sent. `test_prompts.py` pins the rendered
output for a fixed input against a snapshot taken from the inline strings.

**Bump the version** whenever the text of a prompt changes. Placeholders are
filled by plain substitution, never `str.format`, so a brace in a prompt or in
evidence cannot be read as a field. Evidence is quoted into a placeholder by
the caller (`llm._untrusted`) before it gets here: this module never decides
what is data and what is instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict

DIR = Path(__file__).resolve().parent

_HEADER = re.compile(r"\A---\n(?P<meta>.*?)\n---\n=== system ===\n", re.S)
_USER_MARK = "\n=== user ===\n"
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


class PromptError(ValueError):
    """A prompt file that cannot be trusted to say what it is."""


@dataclass(frozen=True)
class Prompt:
    id: str
    version: int
    system: str
    user: str

    @property
    def ref(self) -> str:
        """`explain@1` — what an answer records about where it came from."""
        return f"{self.id}@{self.version}"

    def render(self, **values: str) -> str:
        """The user message, with every placeholder filled — and only those."""
        wanted = set(_PLACEHOLDER.findall(self.user))
        if wanted != set(values):
            raise PromptError(
                f"{self.ref}: placeholders {sorted(wanted)}, given {sorted(values)}"
            )
        # One pass over the template, so a placeholder-shaped string inside a
        # value (evidence can contain anything) is never substituted again.
        return _PLACEHOLDER.sub(lambda m: values[m.group(1)], self.user)


def parse(text: str, *, name: str) -> Prompt:
    m = _HEADER.match(text)
    if not m:
        raise PromptError(f"{name}: no '---' header followed by '=== system ==='")
    meta: Dict[str, str] = {}
    for line in m.group("meta").splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    if meta.get("id") != name:
        raise PromptError(f"{name}: header id is {meta.get('id')!r}")
    version = meta.get("version", "")
    if not version.isdigit() or int(version) < 1:
        raise PromptError(f"{name}: needs a positive integer `version`, got {version!r}")
    body = text[m.end():]
    if _USER_MARK not in body or not body.endswith("\n"):
        raise PromptError(f"{name}: needs '=== user ===' and a final newline")
    system, user = body[:-1].split(_USER_MARK, 1)
    return Prompt(id=name, version=int(version), system=system, user=user)


@lru_cache(maxsize=None)
def load(name: str) -> Prompt:
    """The prompt `name`, from `services/api/prompts/<name>.prompt`."""
    path = DIR / f"{name}.prompt"
    return parse(path.read_text(encoding="utf-8"), name=name)


__all__ = ["DIR", "Prompt", "PromptError", "load", "parse"]
