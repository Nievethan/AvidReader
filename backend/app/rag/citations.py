"""Post-processing of model answers: citation markers, quote verification and
copied-text detection.

All checks are linear in the size of the answer plus the excerpts:
* markers: one regex pass over the answer
* quotes: each quote is a substring test against normalised excerpt text
* copying: a set of word 12-grams from the excerpts, then one pass over the
  answer's n-grams
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.integrations.interfaces import RetrievedPassage

_MARKER = re.compile(r"\[(S\d+(?:\s*,\s*S?\d+)*)\]")
_NUMBER = re.compile(r"\d+")
_QUOTE = re.compile(r"[\"“]([^\"”]{12,}?)[\"”]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9']+")
_SPACES = re.compile(r"\s+")
_DOUBLE_SPACE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")

MIN_QUOTE_WORDS = 4
COPY_NGRAM = 12
SNIPPET_CHARS = 240


@dataclass(frozen=True)
class CheckedAnswer:
    text: str
    cited: list[int]  # 0-based indexes into the sources, in first-cited order
    removed_markers: int
    unverified_quotes: int


def normalise(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return _SPACES.sub(" ", text).strip()


def _tidy(text: str) -> str:
    text = _DOUBLE_SPACE.sub(" ", text)
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text).strip()


def check_answer(text: str, sources: list[RetrievedPassage]) -> CheckedAnswer:
    """Keep only [S#] markers that point at a real source, collect the cited
    sources in order, and turn quotations that do not appear in any source
    into plain text so invented wording is never presented as a quote."""
    cited: list[int] = []
    seen: set[int] = set()
    removed = 0

    def keep_valid(match: re.Match) -> str:
        nonlocal removed
        valid = []
        for number in (int(n) for n in _NUMBER.findall(match.group(1))):
            if 1 <= number <= len(sources):
                valid.append(number)
                if number - 1 not in seen:
                    seen.add(number - 1)
                    cited.append(number - 1)
            else:
                removed += 1
        return "".join(f"[S{n}]" for n in valid)

    text = _MARKER.sub(keep_valid, text)

    haystack = [normalise(p.text) for p in sources]
    unverified = 0

    def verify(match: re.Match) -> str:
        nonlocal unverified
        quote = match.group(1)
        if len(quote.split()) < MIN_QUOTE_WORDS:
            return match.group(0)
        needle = normalise(quote).strip(" .,;:!?'\"")
        if any(needle in source for source in haystack):
            return match.group(0)
        unverified += 1
        return quote

    text = _QUOTE.sub(verify, text)
    return CheckedAnswer(text=_tidy(text), cited=cited, removed_markers=removed, unverified_quotes=unverified)


def remove_copied_sentences(text: str, sources: list[RetrievedPassage], n: int = COPY_NGRAM) -> tuple[str, int]:
    """Drop sentences that repeat a run of `n` or more words from the excerpts
    (used for story continuations, which must be original)."""
    copied: set[tuple[str, ...]] = set()
    for passage in sources:
        words = _WORD.findall(passage.text.lower())
        copied.update(tuple(words[i : i + n]) for i in range(len(words) - n + 1))
    kept, dropped = [], 0
    for sentence in _SENTENCE.split(text):
        words = _WORD.findall(sentence.lower())
        if any(tuple(words[i : i + n]) in copied for i in range(len(words) - n + 1)):
            dropped += 1
        else:
            kept.append(sentence)
    return " ".join(kept).strip(), dropped


def build_citations(cited: list[int], sources: list[RetrievedPassage]) -> list[dict]:
    citations = []
    for index in cited:
        passage = sources[index]
        snippet = " ".join(passage.text.split())
        if len(snippet) > SNIPPET_CHARS:
            snippet = snippet[: SNIPPET_CHARS - 1].rsplit(" ", 1)[0] + "…"
        citations.append(
            {
                "marker": f"S{index + 1}",
                "chunk_id": passage.chunk_id,
                "page_start": passage.page_start,
                "page_end": passage.page_end,
                "page": passage.page_start,  # convenience for the current frontend chip
                "chapter": passage.chapter,
                "source_location": passage.source_location,
                "snippet": snippet,
                "score": round(passage.relevance_score, 4) if passage.relevance_score is not None else None,
            }
        )
    return citations
