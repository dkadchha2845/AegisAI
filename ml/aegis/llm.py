"""
AegisAI — pluggable LLM backend for offline data generation.

Three backends, selected by the AEGIS_LLM environment variable:

    gemini     Google AI Studio free tier. No card, ~1500 requests/day.
               Genuinely good at romanised Hinglish. The default.
    ollama     Fully local, fully offline, unlimited. No signup, no quota.
               Weaker Hinglish than Gemini but it never runs out.
    anthropic  Paid. Best quality. Here if a budget ever appears.

Why an interface instead of just picking one
--------------------------------------------
Free tiers have quotas and quotas run out at inconvenient hours. Switching
providers must be one environment variable, not an afternoon of rewriting. The
same reasoning applies to ASR later: swap the provider, keep the pipeline.

Structured output is deliberately handled client-side (parse + validate) rather
than relying on each provider's schema-enforcement dialect. Provider schema
support varies and the dialects differ; a shared validator behaves identically
across all three and gives us one place to reject malformed generations.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass

import httpx

from .schema import VICTIM_STATES
from .taxonomy import LABELS


class GenerationError(RuntimeError):
    """Raised when a backend returns something we cannot use."""


@dataclass
class Result:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------


class GeminiBackend:
    """
    Google AI Studio free tier.

    Get a key at https://aistudio.google.com/apikey -- Google account, no card.
    Free-tier model names change; override with AEGIS_MODEL if the default
    has moved on. AI Studio's model list is the authority, not this file.
    """

    name = "gemini"
    # Verified against this key's /v1beta/models listing. Flash tier is the
    # free-tier workhorse; 3.5 is the newest and has the best instruction
    # following, which is what keeps the stage labels honest. gemini-2.5-flash
    # is the stable fallback if 3.5 is throttled.
    default_model = "gemini-3.5-flash"
    # Free tier is rate-limited per minute. Keep concurrency low and let the
    # 429 backoff in generate_calls.py absorb the rest.
    suggested_concurrency = 2

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("AEGIS_MODEL", self.default_model)
        self.key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.key:
            raise GenerationError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey (Google account, no card)."
            )
        self.url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )

    async def generate(self, client: httpx.AsyncClient, system: str, prompt: str) -> Result:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                # High temperature is correct here: we are buying diversity,
                # not accuracy. The schema validator catches the cost of it.
                "temperature": 1.0,
                "maxOutputTokens": 8192,
            },
        }
        # The key goes in a header, never the query string: httpx puts the
        # full URL into every exception message, so a `?key=...` param leaks
        # the secret into logs and stack traces on the first transient 503.
        r = await client.post(
            self.url,
            headers={"x-goog-api-key": self.key},
            json=body,
            timeout=180.0,
        )
        if r.status_code == 429:
            raise GenerationError("rate_limited")
        if r.status_code in (500, 503):
            # Flash tiers get transiently overloaded; treat as retryable.
            raise GenerationError(f"overloaded_{r.status_code}")
        r.raise_for_status()
        data = r.json()

        try:
            cand = data["candidates"][0]
        except (KeyError, IndexError):
            raise GenerationError(f"no candidate: {json.dumps(data)[:300]}")
        if cand.get("finishReason") in {"SAFETY", "RECITATION", "BLOCKLIST"}:
            raise GenerationError(f"blocked: {cand.get('finishReason')}")
        if cand.get("finishReason") == "MAX_TOKENS":
            raise GenerationError("truncated")

        text = "".join(p.get("text", "") for p in cand["content"]["parts"])
        usage = data.get("usageMetadata", {})
        return Result(
            text=text,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
        )


class OllamaBackend:
    """
    Fully local. No key, no quota, no network.

        brew install ollama && ollama serve
        ollama pull qwen2.5:7b-instruct

    qwen2.5 is the best 7B option for code-mixed Indic text and fits
    comfortably in 16GB. Set AEGIS_MODEL to try another.
    """

    name = "ollama"
    default_model = "qwen2.5:7b-instruct"
    # Local inference is serial on one GPU; more concurrency just queues.
    suggested_concurrency = 2

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("AEGIS_MODEL", self.default_model)
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    async def generate(self, client: httpx.AsyncClient, system: str, prompt: str) -> Result:
        body = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            # num_ctx is the whole window (prompt + output), so num_predict
            # must leave room for the ~1.7k-token system prompt. Setting both
            # to 8192 would let a long call run the window out mid-JSON and
            # produce an unparseable truncation.
            "options": {"temperature": 1.0, "num_ctx": 8192, "num_predict": 4096},
        }
        try:
            r = await client.post(f"{self.host}/api/generate", json=body, timeout=600.0)
        except httpx.ConnectError:
            raise GenerationError(
                f"Cannot reach Ollama at {self.host}. Start it with `ollama serve`."
            )
        r.raise_for_status()
        data = r.json()
        return Result(
            text=data.get("response", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )


class AnthropicBackend:
    """Paid. Kept so the pipeline can trade money for quality if that changes."""

    name = "anthropic"
    default_model = "claude-opus-4-8"
    suggested_concurrency = 6

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("AEGIS_MODEL", self.default_model)
        if not (
            os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        ):
            raise GenerationError("ANTHROPIC_API_KEY is not set.")
        import anthropic  # imported lazily so the free path needs no SDK

        self._client = anthropic.AsyncAnthropic()

    async def generate(self, client: httpx.AsyncClient, system: str, prompt: str) -> Result:
        from .schema import OUTPUT_CONFIG

        resp = await self._client.messages.create(
            model=self.model,
            max_tokens=8000,
            system=system,
            output_config={"effort": "medium", **OUTPUT_CONFIG},
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "refusal":
            raise GenerationError("refused")
        if resp.stop_reason == "max_tokens":
            raise GenerationError("truncated")
        text = next(b.text for b in resp.content if b.type == "text")
        return Result(text, resp.usage.input_tokens, resp.usage.output_tokens)


BACKENDS = {
    "gemini": GeminiBackend,
    "ollama": OllamaBackend,
    "anthropic": AnthropicBackend,
}


def get_backend(name: str | None = None, model: str | None = None):
    name = (name or os.environ.get("AEGIS_LLM", "gemini")).lower()
    if name not in BACKENDS:
        raise GenerationError(
            f"Unknown backend {name!r}. Choose from: {', '.join(BACKENDS)}"
        )
    return BACKENDS[name](model=model)


# --------------------------------------------------------------------------
# Shared parsing + validation
# --------------------------------------------------------------------------

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)
_LABELS = set(LABELS)
_STATES = set(VICTIM_STATES)


def parse_turns(raw: str) -> list[dict]:
    """
    Extract and validate the turn list from a backend's raw text.

    Every generation is validated here regardless of backend, so a weaker
    local model cannot quietly poison the corpus with invalid labels. A
    rejected generation is cheap; a mislabelled one costs you accuracy you
    will never be able to explain.
    """
    text = _FENCE.sub("", raw).strip()
    if not text:
        raise GenerationError("empty response")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Small models sometimes wrap the object in prose. Recover the
        # outermost JSON object rather than discarding an otherwise fine call.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise GenerationError(f"not JSON: {text[:120]}")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            raise GenerationError(f"not JSON: {e}")

    if isinstance(data, list):  # some models return the bare array
        data = {"turns": data}
    if not isinstance(data, dict) or "turns" not in data:
        raise GenerationError("missing 'turns'")

    turns = data["turns"]
    if not isinstance(turns, list) or len(turns) < 6:
        raise GenerationError(f"only {len(turns) if isinstance(turns, list) else 0} turns")

    clean: list[dict] = []
    for i, t in enumerate(turns):
        if not isinstance(t, dict):
            raise GenerationError(f"turn {i} is not an object")
        speaker = str(t.get("speaker", "")).upper().strip()
        stage = str(t.get("stage", "")).upper().strip()
        text_ = str(t.get("text", "")).strip()
        state = str(t.get("victim_state", "NA")).upper().strip()

        if speaker not in {"CALLER", "VICTIM"}:
            raise GenerationError(f"turn {i}: bad speaker {speaker!r}")
        if stage not in _LABELS:
            raise GenerationError(f"turn {i}: bad stage {stage!r}")
        if not text_:
            raise GenerationError(f"turn {i}: empty text")
        if state not in _STATES:
            state = "NA"
        # A CALLER turn carrying an emotional read is a label error, not a
        # feature -- normalise rather than reject the whole call for it.
        if speaker == "CALLER":
            state = "NA"

        clean.append(
            {"speaker": speaker, "text": text_, "stage": stage, "victim_state": state}
        )

    if not any(t["speaker"] == "CALLER" for t in clean):
        raise GenerationError("no caller turns")
    if not any(t["speaker"] == "VICTIM" for t in clean):
        raise GenerationError("no victim turns")
    return clean


async def probe(backend) -> str:
    """One cheap round-trip, so setup problems surface before a 300-call run."""
    async with httpx.AsyncClient() as client:
        res = await backend.generate(
            client,
            "Reply with JSON only.",
            'Return exactly: {"ok": true}',
        )
    return res.text.strip()[:200]


if __name__ == "__main__":
    b = get_backend()
    print(f"backend={b.name} model={b.model}")
    print("reply:", asyncio.run(probe(b)))
