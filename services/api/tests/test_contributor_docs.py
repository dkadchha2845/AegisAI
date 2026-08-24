"""
The contributor contract, kept true by assertion rather than by good intentions.

    .venv/bin/python -m pytest services/api/tests/test_contributor_docs.py -q

Task 0.7's premise is that the invariants must be enforceable by anyone — human
or agent — who touches the repo. That only holds if the document describing them
is itself correct, and this project has now been bitten three separate times by
documentation that quietly stopped being true:

  * `CLAUDE.md` told contributors the gate was "84 tests". It was 285.
  * `pyproject.toml` pointed at a `make format-check` target that never existed.
  * `AGENTS.md` was created as a copy of `CLAUDE.md` and disagreed with it
    within the hour.
  * The README carried an MIT badge linking to a `LICENSE` file that did not
    exist — found by the path check below, and fixed by the owner adding one.

String-matching a document catches the first kind and misses the other two. So
the interesting tests here do not check that the docs *say* the right thing —
they check that the commands the docs tell you to run exist, and that the files
they send you to are there. A doc that instructs a new contributor to run
something that is not there is a broken door, and the only way it stays fixed is
if the build refuses to accept it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

#: Everything a contributor is expected to read before touching the code.
CONTRIBUTOR_DOCS = ("CLAUDE.md", "AGENTS.md", "README.md")


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def bash_blocks(markdown: str) -> list[str]:
    """The fenced ```bash blocks — the parts a reader will copy and paste."""
    return re.findall(r"```(?:bash|sh|console)\n(.*?)```", markdown, re.S)


def make_targets() -> set[str]:
    """Every target the Makefile actually declares."""
    body = read("Makefile")
    return set(re.findall(r"^([a-zA-Z][a-zA-Z0-9_-]*):", body, re.M))


# --------------------------------------------------------------------------
# The acceptance criteria for 0.7
# --------------------------------------------------------------------------


def test_claude_states_the_invariants_the_gates_and_what_done_means() -> None:
    """The three things task 0.7 asks `CLAUDE.md` to state."""
    guide = read("CLAUDE.md")

    for invariant in (
        "`schema/` is the single source of truth",
        "The frontend is a pure renderer",
        "`StateFrame` = idempotent snapshot",
        "Degradation is explicit",
        "False positives are a first-class failure",
        "The LLM explains, extracts and ranks. It never scores",
        "No claim without a measurement",
        "Evidence is data, never instructions",
    ):
        assert invariant in guide, f"CLAUDE.md no longer states: {invariant}"

    assert "make gates" in guide
    assert "Definition of done — before ticking a task" in guide
    assert "Start the running application and exercise the path changed" in guide


def test_readme_links_contributors_to_the_working_rules() -> None:
    assert "[`CLAUDE.md`](./CLAUDE.md)" in read("README.md")


# --------------------------------------------------------------------------
# The drift guards — the part that would have caught `format-check`
# --------------------------------------------------------------------------


@pytest.mark.parametrize("doc", CONTRIBUTOR_DOCS)
def test_every_make_command_in_the_docs_exists(doc: str) -> None:
    """A doc that tells you to run a target the Makefile does not have.

    This is exactly how `make format-check` got into `pyproject.toml` and stayed
    there across two tasks: nothing executed the sentence, so nothing failed. A
    new contributor running it gets an error on their first day and reasonably
    concludes the project does not work.
    """
    declared = make_targets()
    referenced = set()
    for block in bash_blocks(read(doc)):
        referenced.update(re.findall(r"^\s*make\s+([a-zA-Z][a-zA-Z0-9_-]*)", block, re.M))

    missing = sorted(referenced - declared)
    assert not missing, (
        f"{doc} tells contributors to run make targets that do not exist: {missing}. "
        f"Declared targets are: {sorted(declared)}"
    )


#: The docs write source paths relative to the service they live in —
#: `engine/session.py`, `agents/registry.py` — because that is how someone
#: working inside `services/api/` refers to them. Both roots are accepted; the
#: check is still that the file is *somewhere*, which catches deletions and
#: typos, which is what it is for.
PATH_ROOTS = (Path("."), Path("services/api"))

#: Paths a healthy clone deliberately does not contain. `node_modules/` and
#: `.venv/` are named in the README precisely to say they are not committed, so
#: requiring them to exist would invert the sentence.
IGNORED_IN_A_CLONE = ("node_modules", ".venv", "ml/artifacts", "dist", "__pycache__")

#: Documented exemptions: a path the docs reference that is deliberately absent,
#: each with a reason and an owner. Empty is the healthy state.
#:
#: It held `LICENSE` for exactly one task. The README's MIT badge pointed at a
#: file that was not in the repository, which is a claim with nothing behind it;
#: the entry recorded that rather than letting a contributor quietly invent a
#: licence, and `test_the_known_missing_list_stays_honest` took it out the moment
#: the owner added one. That is the intended lifecycle — an exemption is a note
#: with an expiry, not a permanent excuse.
KNOWN_MISSING: set[str] = set()


@pytest.mark.parametrize("doc", CONTRIBUTOR_DOCS)
def test_every_repo_path_the_docs_point_at_exists(doc: str) -> None:
    """Links that go nowhere are the other half of the same failure."""
    body = read(doc)
    candidates = set()

    # Markdown links to repo-relative paths: [text](./docs/TASKS.md)
    for target in re.findall(r"\]\((\.{0,2}/?[\w./-]+)\)", body):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        candidates.add(target.split("#", 1)[0])

    # Backticked paths that are clearly paths: `docs/ARCHITECTURE.md`, `schema/`
    for target in re.findall(r"`([\w][\w./-]*/[\w./-]*)`", body):
        if target.startswith(("http", "AEGIS_", "PRESAGE_")):
            continue
        candidates.add(target)

    missing = []
    for target in sorted(candidates):
        cleaned = target.lstrip("./").rstrip("/")
        if not cleaned or "*" in cleaned:
            continue
        if cleaned in KNOWN_MISSING:
            continue
        if any(part in cleaned for part in IGNORED_IN_A_CLONE):
            continue
        if not any((ROOT / root / cleaned).exists() for root in PATH_ROOTS):
            missing.append(target)

    assert not missing, f"{doc} points at paths that do not exist: {missing}"


def test_the_known_missing_list_stays_honest() -> None:
    """An exemption that quietly becomes true is an exemption nobody removes.

    If someone adds the LICENSE file, this fails and the entry above comes out —
    so the list cannot rot into a permanent excuse.
    """
    resolved = sorted(p for p in KNOWN_MISSING if (ROOT / p).exists())
    assert not resolved, (
        f"these are no longer missing and should leave KNOWN_MISSING: {resolved}"
    )


@pytest.mark.parametrize("doc", CONTRIBUTOR_DOCS)
def test_the_docs_do_not_hard_code_a_test_count(doc: str) -> None:
    """The drift that started 0.7.

    A number written into prose is wrong the moment the next task adds a test,
    and it is wrong silently — `pytest` does not check counts. The gate is
    `make gates`, and the only true count is the one it prints.
    """
    body = read(doc)
    offenders = re.findall(r"\b\d{2,4}\s+tests?\s+(?:must\s+)?(?:pass|passing|green)", body, re.I)
    assert not offenders, (
        f"{doc} hard-codes a test count: {offenders}. Say `make gates` instead — "
        "the suite grows with every task and the number is stale on arrival."
    )


def test_agents_md_points_at_the_rules_rather_than_copying_them() -> None:
    """A second copy of the rules is a second thing to keep true.

    `AGENTS.md` began as a verbatim copy of `CLAUDE.md` and disagreed with it
    within the hour. It exists because tools look for the filename; it must stay
    a pointer, so there is exactly one place where an invariant is written down.
    """
    agents = read("AGENTS.md")
    assert "CLAUDE.md" in agents, "AGENTS.md must send the reader to CLAUDE.md"

    # The invariants are stated once, in CLAUDE.md. If they appear here too,
    # someone has started the copy again.
    restated = [
        phrase
        for phrase in (
            "`schema/` is the single source of truth",
            "The frontend is a pure renderer",
            "False positives are a first-class failure",
            "The LLM explains, extracts and ranks",
        )
        if phrase in agents
    ]
    assert not restated, (
        f"AGENTS.md restates invariants that belong in CLAUDE.md: {restated}. "
        "Keep it a pointer — one source, one place to fix."
    )


def test_the_coverage_database_is_not_tracked() -> None:
    """`.coverage` is a binary SQLite file rewritten by every test run.

    Tracked, it put a churning blob into every diff while telling a reviewer
    nothing. Untracking it is only half the fix; without the ignore rule the
    next `git add -A` puts it straight back.
    """
    gitignore = read(".gitignore")
    assert ".coverage" in gitignore, ".coverage must be gitignored or it returns on the next add"


def test_pyproject_does_not_promise_a_gate_that_does_not_exist() -> None:
    """The `format-check` correction, pinned.

    `pyproject.toml`'s formatter comment pointed at a make target that was never
    written. The comment is a contributor-facing instruction like any other.
    """
    pyproject = read("pyproject.toml")
    if "format-check" in pyproject:
        assert "format-check" in make_targets(), (
            "pyproject.toml mentions `format-check`; either add the make target "
            "or stop naming it"
        )
