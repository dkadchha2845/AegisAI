"""
LLM adapter — explanation only, never scoring.

The boundary this file draws is the important part. A language model is
allowed to *rephrase* what the engine already decided, in the user's language,
at the reading level they need. It is never allowed to decide. The threat
score, the stage label, the trust verdict, and the coach line are all produced
by code and data that can be tested, versioned, and defended to a judge; an
LLM in that path would make every number unreproducible.

So the contract here is narrow: given a finished analysis, return prose. If
the backend is unavailable — no key, no daemon, no network, quota exhausted —
the caller falls back to the templated explanation and loses nothing but
fluency. Nothing in the request path may block on this.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from .config import settings

TIMEOUT_S = 12.0

SYSTEM = (
    "You explain fraud-detection results to a worried, non-technical person in "
    "India. You are given a finished analysis: a score, the signals that "
    "produced it, and cited sources. Explain what it means in plain language.\n"
    "\n"
    "Hard rules:\n"
    "- Never change, dispute, or re-derive the score or the verdict. Explain "
    "  the one you were given.\n"
    "- Never invent a signal, a source, or a fact that is not in the input.\n"
    "- Never tell the person to send money, share a code, or install anything.\n"
    "- Plain Hinglish or English, matching the input. Short sentences.\n"
    "- 3 sentences maximum. No preamble, no markdown, no bullet points."
)


class LLMUnavailable(RuntimeError):
    pass


def _gemini(prompt: str, system: str = SYSTEM) -> str:
    if not settings.gemini_key:
        raise LLMUnavailable("GEMINI_API_KEY not set")
    # The rolling alias, not a pinned version: Google retires pinned Gemini
    # names (1.5-flash, 2.0-flash both 404/429 now) and a dead default turns
    # every explanation into the template fallback. Pin via AEGIS_MODEL.
    model = settings.llm_model or "gemini-flash-lite-latest"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 320},
    }
    with httpx.Client(timeout=TIMEOUT_S) as client:
        r = client.post(url, params={"key": settings.gemini_key}, json=payload)
        r.raise_for_status()
        data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise LLMUnavailable(f"unexpected Gemini response: {exc}") from exc


def _ollama(prompt: str, system: str = SYSTEM) -> str:
    model = settings.llm_model or "qwen2.5:7b-instruct"
    with httpx.Client(timeout=TIMEOUT_S) as client:
        r = client.post(
            f"{settings.ollama_host}/api/chat",
            json={
                "model": model,
                "stream": False,
                "options": {"temperature": 0.3},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


def _anthropic(prompt: str, system: str = SYSTEM) -> str:
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMUnavailable("ANTHROPIC_API_KEY not set")
    with httpx.Client(timeout=TIMEOUT_S) as client:
        r = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.llm_model or "claude-haiku-4-5-20251001",
                "max_tokens": 400,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()


_BACKENDS = {"gemini": _gemini, "ollama": _ollama, "anthropic": _anthropic}

# A separate, tighter system prompt for the knowledge assistant. Same boundary
# principle as the explainer: the model may *phrase* an answer, but only from the
# retrieved advisory text it is handed — it must not add facts of its own, and it
# must refuse when the corpus does not cover the question. This is retrieval-
# grounded Q&A, never scoring.
ASSISTANT_SYSTEM = (
    "You are AegisAI's fraud-safety assistant for people in India. Answer the "
    "user's question using ONLY the numbered CONTEXT passages provided, which "
    "come from a curated corpus of RBI advisories and scam playbooks.\n"
    "\n"
    "Hard rules:\n"
    "- Use only the CONTEXT. Do not add facts, numbers, or claims that are not "
    "  in it.\n"
    "- If the CONTEXT does not answer the question, say so plainly and suggest "
    "  calling 1930 or visiting cybercrime.gov.in. Do not guess.\n"
    "- Never tell anyone to send money, share an OTP/PIN/CVV, or install "
    "  anything.\n"
    "- Cite the sources you used by their bracketed labels, e.g. [1], [2].\n"
    "- Plain, calm English or Hinglish matching the question. 2–4 short "
    "  sentences. No preamble, no markdown headings."
)


def available() -> bool:
    return settings.llm_backend in _BACKENDS


def answer_question(question: str, contexts: List[Dict[str, str]]) -> Optional[str]:
    """A retrieval-grounded answer to a knowledge-base question, or None if no
    LLM backend is configured / reachable.

    `contexts` is the already-retrieved passages: `[{"source", "text"}, ...]`.
    The caller has a non-LLM fallback (show the passages themselves), so this
    returning None must never break the feature — it just makes it extractive
    instead of conversational.
    """
    backend = _BACKENDS.get(settings.llm_backend)
    if backend is None or not contexts:
        return None
    numbered = "\n\n".join(
        f"[{i + 1}] {c.get('source', '')}\n{c.get('text', '')}"
        for i, c in enumerate(contexts)
    )
    prompt = (
        f"CONTEXT:\n{numbered}\n\n"
        f"QUESTION: {question.strip()}\n\n"
        "Answer using only the context above, and cite the passages you used."
    )
    try:
        # Same transport as the explainer, but handed the assistant's own system
        # prompt so it answers from context instead of explaining a verdict.
        return backend(prompt, system=ASSISTANT_SYSTEM)
    except Exception as exc:  # network, quota, malformed — all degrade to None
        print(f"[aegis] knowledge assistant unavailable: {exc}")
        return None


def explain(analysis: Dict[str, Any], language: str = "auto") -> Optional[str]:
    """Prose explanation of a finished analysis, or None if unavailable.

    Returning None rather than raising is deliberate: every caller has a
    templated fallback, and an explanation is a nice-to-have that must never
    turn a working verdict into a 500.
    """
    backend = _BACKENDS.get(settings.llm_backend)
    if backend is None:
        return None

    # Only the decided facts go in. Sending the raw transcript would invite
    # the model to form its own opinion about the call, which is exactly the
    # thing this boundary exists to prevent.
    brief = {
        "verdict": analysis.get("verdict"),
        "score": analysis.get("score"),
        "level": analysis.get("level"),
        "stages_seen": analysis.get("stages_seen", []),
        "drivers": [d.get("label") for d in analysis.get("drivers", [])],
        "findings": [
            {"label": f.get("label"), "detail": f.get("detail")}
            for f in analysis.get("findings", [])
        ][:5],
        "citations": analysis.get("citations", [])[:4],
        "language": language,
    }
    prompt = (
        "Explain this fraud analysis to the person who submitted it.\n\n"
        + json.dumps(brief, ensure_ascii=False, indent=2)
    )
    try:
        return backend(prompt)
    except Exception as exc:  # network, quota, malformed response — all equal
        print(f"[aegis] LLM explanation unavailable: {exc}")
        return None


def status() -> Dict[str, Any]:
    return {
        "backend": settings.llm_backend,
        "model": settings.llm_model,
        "configured": available(),
    }


def keys_present() -> List[str]:
    present = []
    if settings.gemini_key:
        present.append("gemini")
    return present
