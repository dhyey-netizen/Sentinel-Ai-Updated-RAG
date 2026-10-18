"""Runbook retrieval (the RAG component).

Operator-written Markdown runbooks are split into heading-based chunks and ranked with BM25 against
a query built from the incident. Retrieved chunks are *reference material* for next-step and
remediation suggestions. They are never evidence about the incident and never affect confidence.

Why BM25 and not embeddings/a vector DB: the corpus is a handful of short, keyword-rich runbooks,
BM25 is deterministic, dependency-free and unit-testable, and it needs no second model in 6 GB of
VRAM. If the runbook set grows or phrasing diverges from log vocabulary, swap ``search`` for an
embedding retriever (e.g. Ollama ``nomic-embed-text``) behind the same interface.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("sentinel_ai.knowledge")

MAX_CHUNK_CHARS = 900
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORD_TEXT = (
    "a an and are as at be been by for from has have in into is it its of on or that the their "
    "this to was were will with not no than then so if we you our can may should such when which "
    "while who what why how also any all each both more most other some only same too very"
)
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens, stopwords removed, with a light plural/tense stemmer."""
    tokens = []
    for tok in _TOKEN_RE.findall(text.lower()):
        if tok in _STOPWORDS or len(tok) < 2:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if len(tok) > len(suffix) + 3 and tok.endswith(suffix):
                tok = tok[: -len(suffix)]
                break
        tokens.append(tok)
    return tokens


@dataclass(frozen=True)
class RunbookChunk:
    id: str
    source: str  # file stem, e.g. "pool-exhaustion"
    heading: str
    text: str


@dataclass(frozen=True)
class Retrieved:
    chunk: RunbookChunk
    score: float


def _split_long(text: str, limit: int) -> list[str]:
    """Split on blank lines so no chunk exceeds ``limit`` (nothing is dropped)."""
    pieces: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", text.strip()):
        if current and len(current) + len(para) + 2 > limit:
            pieces.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(source: str, markdown: str) -> list[tuple[str, str]]:
    """Return ``(heading, text)`` pairs: one per ``##`` section (title section if present)."""
    title = source
    sections: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = (line[3:].strip(), [])
            sections.append(current)
        elif line.startswith("# "):
            title = line[2:].strip()
        elif current is not None:
            current[1].append(line)
    out: list[tuple[str, str]] = []
    for heading, body in sections:
        text = "\n".join(body).strip()
        if text:
            out.extend((heading, piece) for piece in _split_long(text, MAX_CHUNK_CHARS))
    return [(f"{title} / {h}", t) for h, t in out]


class RunbookIndex:
    """In-memory BM25 index over runbook chunks."""

    def __init__(self, chunks: list[RunbookChunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self._k1, self._b = k1, b
        # heading words are indexed too, so "Diagnosis"/title terms help matching
        self._tf = [Counter(tokenize(f"{c.heading} {c.text}")) for c in chunks]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = (sum(self._len) / len(chunks)) if chunks else 0.0
        df: Counter[str] = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(chunks)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def __len__(self) -> int:
        return len(self.chunks)

    @classmethod
    def from_dir(cls, directory: Path | str) -> RunbookIndex:
        """Load ``*.md`` runbooks. A missing directory or unreadable file yields fewer chunks."""
        path = Path(directory)
        if not path.is_dir():
            return cls([])
        chunks: list[RunbookChunk] = []
        for file in sorted(path.glob("*.md")):
            try:
                markdown = file.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                log.warning("skipping unreadable runbook %s (%s)", file.name, type(exc).__name__)
                continue
            for heading, text in chunk_markdown(file.stem, markdown):
                chunks.append(RunbookChunk(f"K{len(chunks) + 1}", file.stem, heading, text))
        return cls(chunks)

    def search(
        self,
        query: str,
        k: int = 3,
        min_relative: float = 0.5,
        min_score: float = 3.0,
        max_per_source: int = 2,
    ) -> list[Retrieved]:
        """Top-``k`` chunks by BM25.

        Weak matches are dropped: a chunk must score at least ``min_score`` (absolute floor, so a
        vague query returns nothing rather than noise) and ``min_relative`` x the best score.
        At most ``max_per_source`` chunks come from one runbook so a single file cannot crowd out
        others. The floor is corpus-dependent; it was tuned on the bundled synthetic runbooks.
        """
        terms = Counter(tokenize(query))
        if not terms or not self.chunks:
            return []
        scored: list[Retrieved] = []
        for chunk, tf, length in zip(self.chunks, self._tf, self._len, strict=True):
            score = 0.0
            for term in terms:
                f = tf.get(term, 0)
                if f:
                    norm = 1 - self._b + self._b * length / (self._avg or 1.0)
                    score += self._idf[term] * f * (self._k1 + 1) / (f + self._k1 * norm)
            if score >= min_score:
                scored.append(Retrieved(chunk, score))
        scored.sort(key=lambda r: (-r.score, r.chunk.id))
        if not scored:
            return []
        best = scored[0].score
        picked: list[Retrieved] = []
        per_source: Counter[str] = Counter()
        for r in scored:
            if len(picked) >= k:
                break
            if r.score < min_relative * best or per_source[r.chunk.source] >= max_per_source:
                continue
            per_source[r.chunk.source] += 1
            picked.append(r)
        return picked

    def search_runbooks(self, query: str, max_runbooks: int = 2) -> list[Retrieved]:
        """Parent-document retrieval: rank *sections*, return every section of the best runbooks.

        A log-derived query resembles a runbook's Symptoms section, but the guidance that helps
        (Diagnosis, Remediation) lives in sibling sections, so whole runbooks are returned, best
        first, each section carrying its runbook's best matching score.
        """
        hits = self.search(query, k=len(self.chunks), max_per_source=len(self.chunks))
        best: dict[str, float] = {}
        for hit in hits:  # sorted best-first, so the first hit per source is its best
            best.setdefault(hit.chunk.source, hit.score)
        return [
            Retrieved(chunk, best[source])
            for source in list(best)[:max_runbooks]
            for chunk in self.chunks
            if chunk.source == source
        ]
