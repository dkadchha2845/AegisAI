#!/usr/bin/env python3
"""
AegisAI — synthetic call generator.

Generates a diverse corpus of labelled scam and legitimate call transcripts in
romanised Hinglish, for training the stage classifier and fitting the Digital
Twin's transition model.

    python generate_calls.py --check            # verify the backend works
    python generate_calls.py --dry-run          # inspect prompts, no calls
    python generate_calls.py --limit 5          # smoke test
    python generate_calls.py                    # full run (~330 calls)

Backend is chosen with AEGIS_LLM (gemini | ollama | anthropic). The default,
gemini, runs on Google AI Studio's free tier. See aegis/llm.py.

The run is resumable: completed calls are appended to the output JSONL as they
finish, and re-running skips any call_id already present. Interrupt it, restart
it, top it up with a larger --limit -- nothing is regenerated or lost. Free
tiers have daily quotas, so expect to run this across more than one sitting.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

import httpx


from aegis_core.llm import GenerationError, get_backend, parse_turns, probe  # noqa: E402
from aegis_core.schema import VICTIM_STATES  # noqa: E402
from aegis_core.seeds import Seed, build_seeds  # noqa: E402
from aegis_core.taxonomy import LABELS, prompt_block  # noqa: E402

DEFAULT_OUT = Path(__file__).parent / "data" / "raw" / "calls.jsonl"


SYSTEM = f"""You generate realistic training data for an Indian scam-call \
detection system. Your transcripts train a classifier that protects elderly \
and vulnerable people from financial fraud, so realism is what makes the \
system work.

You are writing what a speech-to-text engine would output from a real phone \
call: romanised Hinglish, no Devanagari, no stage directions, no narration, no \
speaker names inside the text. Real speech -- interruptions, repetition, filler \
words (haan, achha, arre, matlab, wo), incomplete sentences, people talking \
past each other.

## Stage labels

Label every turn with exactly one stage:

{prompt_block()}

## Rules

1. Label VICTIM turns with the stage of the *exchange*, not the victim's own \
intent. If the caller is inducing fear and the victim replies "sir maine to \
kuch nahi kiya", that turn is FEAR_INDUCTION.
2. Stages do not have to advance monotonically. Real scammers loop back -- \
re-applying fear after resistance, repeating isolation before payment. Let \
them.
3. Not every call reaches PAYMENT_EXECUTION. Honour the specified outcome. A \
corpus where isolation always leads to payment teaches the forecasting model a \
falsehood.
4. Vary the numbers, names, case IDs, banks, cities, and amounts in every \
call. Never reuse "Inspector Sharma" or Rs 4,50,000 unless asked to.
5. For BENIGN calls: label every turn BENIGN. These are legitimate calls that \
deliberately share surface vocabulary with scams -- "verify", "account", \
"urgent", "KYC" -- but involve no coercion, no secrecy, and no pressure to \
transfer money to an unfamiliar account. They are the hardest and most \
valuable examples in the corpus.
6. victim_state is "NA" on every CALLER turn, and a genuine emotional read on \
every VICTIM turn.

## Output format

Return a single JSON object and nothing else. No markdown fences, no \
commentary before or after.

{{"turns": [{{"speaker": "CALLER", "text": "...", "stage": "GREETING", \
"victim_state": "NA"}}, {{"speaker": "VICTIM", "text": "...", "stage": \
"GREETING", "victim_state": "CALM"}}]}}

speaker must be exactly "CALLER" or "VICTIM".
stage must be exactly one of: {", ".join(LABELS)}.
victim_state must be exactly one of: {", ".join(VICTIM_STATES)}."""


def user_prompt(seed: Seed) -> str:
    kind = "scam call" if seed.is_scam else "legitimate (non-scam) call"
    return f"""Generate one {kind}.

Archetype: {seed.archetype_name}
Premise: {seed.premise}
Victim: {seed.victim}
Caller style: {seed.style}
Language: {seed.language}
Length: {seed.length}
Outcome: {seed.outcome}

Make this call specifically shaped by the details above -- the victim's age and \
tech literacy should change how they respond, and the caller's style should \
change their sentence rhythm, not just their word choice."""


def load_done(path: Path) -> set[str]:
    """Read already-generated call_ids so a re-run resumes rather than repeats."""
    if not path.exists():
        return set()
    done = set()
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["seed"]["call_id"])
            except (json.JSONDecodeError, KeyError):
                continue  # partial final line from an interrupted run
    return done


async def generate_one(
    backend,
    client: httpx.AsyncClient,
    seed: Seed,
    sem: asyncio.Semaphore,
    max_attempts: int = 4,
) -> dict | None:
    """Generate and validate a single call. Returns None if it fails."""
    async with sem:
        for attempt in range(max_attempts):
            try:
                res = await backend.generate(client, SYSTEM, user_prompt(seed))
                turns = parse_turns(res.text)
                return {
                    "seed": seed.as_dict(),
                    "turns": turns,
                    "backend": backend.name,
                    "model": backend.model,
                    "usage": {
                        "input_tokens": res.input_tokens,
                        "output_tokens": res.output_tokens,
                    },
                }
            except GenerationError as e:
                last = str(e)
                # Free-tier quota is per-minute; wait it out rather than
                # burning the remaining attempts in two seconds.
                delay = 30.0 if "rate_limited" in last else 2**attempt
                if attempt == max_attempts - 1:
                    print(f"  drop {seed.call_id}: {last}", file=sys.stderr)
                    return None
                await asyncio.sleep(delay + random.random())
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                if attempt == max_attempts - 1:
                    print(f"  drop {seed.call_id}: {e}", file=sys.stderr)
                    return None
                await asyncio.sleep(2**attempt + random.random())
    return None


async def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the AegisAI synthetic corpus.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--backend", default=None, help="gemini | ollama | anthropic")
    ap.add_argument("--model", default=None, help="override the backend's default model")
    ap.add_argument("--scam", type=int, default=220)
    ap.add_argument("--benign", type=int, default=110)
    ap.add_argument("--limit", type=int, default=None, help="cap this run")
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--seed", type=int, default=20260720)
    ap.add_argument("--dry-run", action="store_true", help="print prompts, no calls")
    ap.add_argument("--check", action="store_true", help="one round-trip, then exit")
    args = ap.parse_args()

    seeds = build_seeds(n_scam=args.scam, n_benign=args.benign, seed=args.seed)

    if args.dry_run:
        print(f"{len(seeds)} seeds. First 2 prompts:\n")
        for s in seeds[:2]:
            print("=" * 70)
            print(user_prompt(s))
        print("=" * 70)
        print(f"\nSystem prompt: {len(SYSTEM)} chars")
        return 0

    try:
        backend = get_backend(args.backend, args.model)
    except GenerationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.check:
        print(f"backend={backend.name} model={backend.model}")
        try:
            print("reply:", await probe(backend))
            print("OK — backend reachable.")
            return 0
        except Exception as e:
            print(f"FAILED: {e}", file=sys.stderr)
            return 1

    concurrency = args.concurrency or backend.suggested_concurrency
    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(args.out)
    todo = [s for s in seeds if s.call_id not in done]
    if args.limit:
        todo = todo[: args.limit]

    if not todo:
        print(f"Nothing to do — {len(done)} calls already in {args.out}")
        return 0

    print(
        f"backend={backend.name} model={backend.model}\n"
        f"{len(done)} done, generating {len(todo)} (concurrency {concurrency})"
    )

    sem = asyncio.Semaphore(concurrency)
    started = time.monotonic()
    ok = tok_in = tok_out = 0

    # Append-as-you-go: a crash or a quota wall costs the in-flight calls,
    # not the whole run.
    async with httpx.AsyncClient() as client:
        with args.out.open("a") as f:
            tasks = [
                asyncio.create_task(generate_one(backend, client, s, sem)) for s in todo
            ]
            for i, fut in enumerate(asyncio.as_completed(tasks), 1):
                rec = await fut
                if rec:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    ok += 1
                    tok_in += rec["usage"]["input_tokens"]
                    tok_out += rec["usage"]["output_tokens"]
                if i % 10 == 0 or i == len(todo):
                    rate = i / max(time.monotonic() - started, 1e-6) * 60
                    print(
                        f"  {i}/{len(todo)}  ok={ok}  "
                        f"{time.monotonic() - started:.0f}s  ({rate:.0f}/min)"
                    )

    print(
        f"\n{ok}/{len(todo)} generated in {time.monotonic() - started:.0f}s\n"
        f"tokens: {tok_in:,} in / {tok_out:,} out\n"
        f"corpus: {args.out}  (total {len(done) + ok} calls)"
    )
    if ok < len(todo):
        print(
            f"{len(todo) - ok} failed. Re-run to fill the gaps — completed calls "
            "are skipped automatically."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
