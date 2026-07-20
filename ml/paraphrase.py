#!/usr/bin/env python3
"""
PRESAGE — expand the hand-labelled gold set into a training corpus.

    python paraphrase.py --variants 20 --no-llm    # substitution only, instant
    python paraphrase.py --variants 20             # + local model rewrite

Two stages, in order of trustworthiness:

  1. Entity substitution (presage/entities.py) -- deterministic, offline,
     cannot fail. Swaps names, cities, banks, apps, amounts, identifiers.
  2. Local-model paraphrase -- reworders the sentences for real phrasing
     variety. Optional; skipped with --no-llm.

The safety property that makes stage 2 usable with a weak model
---------------------------------------------------------------
**The model never sees a label and never emits one.** It receives a numbered
list of utterance texts and must return the same number of rewritten lines.
Speakers, stages, victim states, and turn order are copied from the gold call,
which a human wrote. If the line count comes back wrong the variant is rejected
and the substitution-only version is kept.

This is what makes a 7B model safe here. It failed at free generation because it
invented incoherent stage sequences; it cannot do that when it is only allowed
to reword, and its output is discarded unless the shape matches exactly.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))

from presage.entities import substitute  # noqa: E402
from presage.hinglish import preserved  # noqa: E402
from presage.llm import GenerationError, get_backend  # noqa: E402

HERE = Path(__file__).parent
SEED_GLOB = str(HERE / "data" / "seed" / "*.jsonl")
DEFAULT_OUT = HERE / "data" / "raw" / "calls.jsonl"

def load_gold() -> list[dict]:
    """Load every hand-labelled call from data/seed/*.jsonl."""
    calls = []
    for path in sorted(glob.glob(SEED_GLOB)):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    calls.append(json.loads(line))
    return calls


REWRITE_SYSTEM = """You reword Hinglish phone-call transcripts for an Indian \
speech dataset.

CRITICAL LANGUAGE RULE: the input is romanised Hinglish -- Hindi written in \
English letters, mixed with English words. Your output MUST use the same \
language mix. You are NOT translating. Do NOT turn Hindi into English.

  input : "Sir aapke Aadhaar number par ek parcel detain hua hai"
  GOOD  : "Sir aapke Aadhaar pe jo parcel tha wo customs ne rok liya hai"
  BAD   : "Sir a parcel has been detained against your Aadhaar number"

The BAD example is a translation. Never produce that. If an input line is in \
Hindi, the rewrite stays in Hindi. If a line is already English, keep English.

Reword each line to mean the same thing with different word choice and \
sentence rhythm, in the same speaker's voice and emotional register. Keep \
every name, number, amount, bank and app EXACTLY as given.

Return JSON: {"lines": ["rewrite of line 1", "rewrite of line 2", ...]}
The array must have exactly as many entries as there were input lines. Never \
merge or split lines. No commentary."""


def build_rewrite_prompt(turns: list[dict]) -> str:
    lines = "\n".join(f"{i + 1}. {t['text']}" for i, t in enumerate(turns))
    return (
        f"Reword these {len(turns)} Hinglish lines, staying in Hinglish. "
        f'Return {{"lines": [...]}} with exactly {len(turns)} entries.\n\n{lines}'
    )


_NUMBERED = re.compile(r"^\s*(\d+)\s*[.|)]\s*(.+?)\s*$")
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def parse_rewrite(raw: str, expected: int) -> list[str]:
    """
    Extract exactly `expected` rewritten lines, or raise.

    Accepts the JSON array form (what a `format: json` backend produces), the
    numbered-object form small models emit instead, and plain numbered text.
    Strict on count: a mismatch means the model merged, split or dropped a
    line, which silently misaligns text against human labels. Rejecting is
    free -- the substituted variant is kept.
    """
    text = raw.strip()
    lines: list[str] | None = None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        if isinstance(data.get("lines"), list):
            lines = [str(x) for x in data["lines"]]
        else:
            numeric = {
                int(k): str(v) for k, v in data.items() if str(k).strip().isdigit()
            }
            if numeric:
                lines = [numeric.get(i, "") for i in range(1, expected + 1)]
    elif isinstance(data, list):
        lines = [str(x) for x in data]

    if lines is None:
        found: dict[int, str] = {}
        for line in text.splitlines():
            m = _NUMBERED.match(line)
            if m:
                idx = int(m.group(1))
                if 1 <= idx <= expected and idx not in found:
                    found[idx] = m.group(2).strip()
        if found:
            lines = [found.get(i, "") for i in range(1, expected + 1)]

    if lines is None:
        raise GenerationError("unparseable rewrite")

    lines = [re.sub(r"^\s*\|\s*", "", ln).strip() for ln in lines]

    if len(lines) != expected:
        raise GenerationError(f"got {len(lines)} lines, expected {expected}")
    if any(not ln for ln in lines):
        raise GenerationError("blank line in rewrite")
    if any(_DEVANAGARI.search(ln) for ln in lines):
        raise GenerationError("devanagari in output")
    return lines


async def rewrite_call(
    backend, client: httpx.AsyncClient, turns: list[dict], sem: asyncio.Semaphore
) -> list[dict] | None:
    """Reword turn texts in place. Returns None on any failure (caller keeps original)."""
    async with sem:
        for attempt in range(2):
            try:
                res = await backend.generate(
                    client, REWRITE_SYSTEM, build_rewrite_prompt(turns)
                )
                texts = parse_rewrite(res.text, len(turns))

                # Language gate. Structural validity is not enough: a model
                # that silently translates the call into English produces
                # perfectly-shaped, perfectly-labelled, useless data.
                ok, src_d, out_d = preserved([t["text"] for t in turns], texts)
                if not ok:
                    raise GenerationError(
                        f"translated to English (hinglish {src_d:.2f}->{out_d:.2f})"
                    )
                return [{**t, "text": new} for t, new in zip(turns, texts)]
            except (GenerationError, httpx.HTTPError, httpx.TimeoutException):
                if attempt:
                    return None
                await asyncio.sleep(1)
    return None


async def main() -> int:
    ap = argparse.ArgumentParser(description="Expand the gold set into a corpus.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--variants", type=int, default=20)
    ap.add_argument("--no-llm", action="store_true", help="substitution only")
    ap.add_argument("--merge-only", action="store_true", help="rebuild output from checkpoints")
    ap.add_argument("--backend", default="ollama")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--seed", type=int, default=20260720)
    args = ap.parse_args()

    gold = load_gold()
    if not gold:
        print(f"No gold calls found at {SEED_GLOB}", file=sys.stderr)
        return 1

    rewrites_path = args.out.parent / "rewrites.jsonl"
    args.out.parent.mkdir(parents=True, exist_ok=True)

    # Stage 1 -- deterministic, instant, cannot fail.
    variants: list[dict] = []
    for call in gold:
        base_id = call["seed"]["call_id"]
        for v in range(args.variants):
            rng = random.Random(f"{args.seed}:{base_id}:{v}")
            variants.append({
                "seed": {**call["seed"], "call_id": f"{base_id}_v{v:02d}",
                         "derived_from": base_id},
                "turns": substitute(call["turns"], rng),
                "source": "gold_substituted",
            })
    print(f"stage 1: {len(variants)} variants by entity substitution")

    # Load any rewrites from a previous (possibly interrupted) run.
    done: dict[str, list[dict]] = {}
    if rewrites_path.exists():
        for line in rewrites_path.read_text().splitlines():
            if line.strip():
                try:
                    rec = json.loads(line)
                    done[rec["call_id"]] = rec["turns"]
                except (json.JSONDecodeError, KeyError):
                    continue  # truncated final line from a kill
        print(f"resuming: {len(done)} rewrites already on disk")

    if not (args.no_llm or args.merge_only):
        try:
            backend = get_backend(args.backend)
        except GenerationError as e:
            print(f"backend unavailable ({e}) — substitution only", file=sys.stderr)
            args.no_llm = True

    if not (args.no_llm or args.merge_only):
        todo = [v for v in variants if v["seed"]["call_id"] not in done]
        print(f"stage 2: rewording {len(todo)} via {backend.name}/{backend.model}")
        sem = asyncio.Semaphore(args.concurrency)
        started = time.monotonic()
        ok = 0
        # Append per completion: a 4-hour run must survive a laptop sleeping.
        with rewrites_path.open("a") as ck:
            async with httpx.AsyncClient() as client:
                tasks = [asyncio.create_task(rewrite_call(backend, client, v["turns"], sem))
                         for v in todo]
                for i, (v, task) in enumerate(zip(todo, tasks), 1):
                    result = await task
                    if result:
                        cid = v["seed"]["call_id"]
                        done[cid] = result
                        ck.write(json.dumps({"call_id": cid, "turns": result},
                                            ensure_ascii=False) + "\n")
                        ck.flush()
                        ok += 1
                    if i % 10 == 0 or i == len(todo):
                        el = time.monotonic() - started
                        eta = el / i * (len(todo) - i) / 60
                        print(f"  {i}/{len(todo)} ok={ok} {el/60:.0f}m elapsed, ~{eta:.0f}m left",
                              flush=True)
        print(f"stage 2: {ok}/{len(todo)} reworded this run")

    # Merge: rewrites win where present, substitution elsewhere.
    for v in variants:
        cid = v["seed"]["call_id"]
        if cid in done:
            v["turns"] = done[cid]
            v["source"] = "gold_substituted_reworded"

    with args.out.open("w") as f:
        for v in variants:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")

    by_source: dict[str, int] = {}
    for v in variants:
        by_source[v["source"]] = by_source.get(v["source"], 0) + 1
    print(f"\nwrote {len(variants)} calls to {args.out}")
    for k, n in sorted(by_source.items()):
        print(f"  {k}: {n}")
    print("\nNext: python build_dataset.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
