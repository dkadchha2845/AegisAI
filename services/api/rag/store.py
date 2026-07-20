"""
Retrieval over the curated knowledge base.

Two backends behind one interface, chosen at load time:

  dense   sentence-transformers embeddings, cosine similarity
  lexical BM25 over tokenised chunks — no model, no download, no GPU

The lexical backend exists because the dense one needs a ~90MB model download
on first run, and the one thing this system cannot do is stall on first use
during a live demo. BM25 on a corpus this size (a few hundred chunks of
curated advisory text) is genuinely competitive; the dense model mainly wins
on paraphrase, which matters for the free-text analyzer and much less for the
coach lookups that are keyed by stage.

Everything returned carries its `source` — the document and heading it came
from. That is not decoration. `PassportCheck.source` and
`CoachSuggestion.sources` are contract fields precisely so the UI can always
show which document backed a claim, and an uncited answer is one a judge is
right to distrust.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..config import settings


@dataclass
class Chunk:
    id: str
    text: str
    #: Human-readable citation, e.g. "rbi-advisories.md § Digital arrest".
    source: str
    #: Front-matter tags, used to filter before ranking (stage:ISOLATION, etc).
    tags: list[str] = field(default_factory=list)
    doc: str = ""


@dataclass
class Hit:
    chunk: Chunk
    score: float


_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def load_chunks(directory: Path) -> list[Chunk]:
    """Split every markdown doc in `directory` on `##` headings.

    Heading-level chunking rather than fixed-size windows: these documents are
    written as one self-contained advisory per heading, so the headings are
    already the right semantic unit, and a 512-token window would slice them
    mid-rule.
    """
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        doc_tags: list[str] = []
        # Optional front matter: a `<!-- tags: a, b -->` line applying to the
        # whole document.
        fm = re.match(r"\s*<!--\s*tags:(.*?)-->", raw)
        if fm:
            doc_tags = [t.strip() for t in fm.group(1).split(",") if t.strip()]
            raw = raw[fm.end():]

        sections = re.split(r"^##\s+(.+)$", raw, flags=re.M)
        # re.split with one capture group yields [preamble, head1, body1, ...]
        preamble = sections[0].strip()
        if preamble:
            chunks.append(
                Chunk(
                    id=f"{path.stem}#0",
                    text=preamble,
                    source=f"{path.name} § intro",
                    tags=list(doc_tags),
                    doc=path.name,
                )
            )
        for i in range(1, len(sections), 2):
            heading = sections[i].strip()
            body = sections[i + 1].strip() if i + 1 < len(sections) else ""
            if not body:
                continue
            inline = re.findall(r"<!--\s*tags:(.*?)-->", body)
            tags = list(doc_tags)
            for group in inline:
                tags += [t.strip() for t in group.split(",") if t.strip()]
            body = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()
            chunks.append(
                Chunk(
                    id=f"{path.stem}#{i}",
                    text=f"{heading}\n{body}",
                    source=f"{path.name} § {heading}",
                    tags=tags,
                    doc=path.name,
                )
            )
    return chunks


class BM25Index:
    """Okapi BM25. ~60 lines, zero dependencies, deterministic."""

    K1 = 1.5
    B = 0.75

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.docs = [tokenize(c.text) for c in chunks]
        self.lengths = [len(d) for d in self.docs]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        self.tf = [Counter(d) for d in self.docs]
        df: Counter[str] = Counter()
        for doc in self.docs:
            df.update(set(doc))
        n = len(self.docs)
        self.idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def search(self, query: str, k: int = 4, tags: list[str] | None = None) -> list[Hit]:
        terms = tokenize(query)
        scored: list[Hit] = []
        for i, chunk in enumerate(self.chunks):
            # Tag filter is a hard gate, not a boost: a coach line indexed for
            # ISOLATION must never surface during a GREETING because it
            # happened to share vocabulary.
            if tags and not any(t in chunk.tags for t in tags):
                continue
            score = 0.0
            length = self.lengths[i] or 1
            for term in terms:
                freq = self.tf[i].get(term, 0)
                if not freq:
                    continue
                idf = self.idf.get(term, 0.0)
                norm = freq * (self.K1 + 1)
                denom = freq + self.K1 * (1 - self.B + self.B * length / (self.avg_len or 1))
                score += idf * norm / denom
            if score > 0:
                scored.append(Hit(chunk, round(score, 4)))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]


class DenseIndex:
    """sentence-transformers + cosine. Constructed only if the import and the
    model load both succeed; the caller falls back to BM25 otherwise."""

    def __init__(self, chunks: list[Chunk], model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # type: ignore

        self.chunks = chunks
        self.model = SentenceTransformer(model_name)
        self.matrix = self.model.encode(
            [c.text for c in chunks], normalize_embeddings=True, show_progress_bar=False
        )

    def search(self, query: str, k: int = 4, tags: list[str] | None = None) -> list[Hit]:
        import numpy as np  # type: ignore

        q = self.model.encode([query], normalize_embeddings=True)[0]
        sims = self.matrix @ q
        order = np.argsort(-sims)
        hits: list[Hit] = []
        for idx in order:
            chunk = self.chunks[int(idx)]
            if tags and not any(t in chunk.tags for t in tags):
                continue
            hits.append(Hit(chunk, round(float(sims[int(idx)]), 4)))
            if len(hits) >= k:
                break
        return hits


class KnowledgeBase:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or settings.knowledge_dir
        self.chunks = load_chunks(self.directory) if self.directory.exists() else []
        self.backend = "none"
        self.index: BM25Index | DenseIndex | None = None
        if not self.chunks:
            return
        if settings.prefer_dense_embeddings:
            try:
                self.index = DenseIndex(self.chunks)
                self.backend = "dense"
                return
            except Exception as exc:  # no torch, no model cache, offline
                print(f"[presage] dense RAG unavailable ({exc}); using BM25")
        self.index = BM25Index(self.chunks)
        self.backend = "bm25"

    def search(self, query: str, k: int = 4, tags: list[str] | None = None) -> list[Hit]:
        if self.index is None:
            return []
        return self.index.search(query, k=k, tags=tags)

    @property
    def degraded(self) -> list[str]:
        if self.index is None:
            return ["rag:unavailable"]
        if self.backend == "bm25":
            return ["rag:lexical"]
        return []


_kb: KnowledgeBase | None = None


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb
