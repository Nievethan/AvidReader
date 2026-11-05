"""Step 3a: basic text cleaning.

* strip running headers/footers/page numbers (PDF only): short paragraphs at
  the top/bottom of a page whose digit-normalised text recurs on many pages
* rejoin words hyphenated across line breaks ("inter-\\nnational")
* reflow hard-wrapped lines into paragraphs, collapse whitespace
* drop control characters and soft hyphens, NFKC-normalise (ligatures etc.)

Known trade-off: a genuine compound split at a line break ("well-\\nknown")
is rejoined as "wellknown". Hyphen + lowercase continuation is the heuristic.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import replace

from app.rag.models import ExtractedDocument, Section

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHEN_BREAK = re.compile(r"([^\W\d_])[-‐]\s*\n\s*([^\W\d_])")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")

_EDGE_BLOCKS = 2  # look at the first/last N paragraphs of each page
_MAX_HEADER_CHARS = 120
_MIN_PAGES_FOR_HEADER_DETECTION = 4


def clean_document(doc: ExtractedDocument) -> ExtractedDocument:
    paragraphs = [_split_paragraphs(s.text) for s in doc.sections]
    if doc.kind == "pdf":
        paragraphs = _strip_repeated_edges(paragraphs)

    sections: list[Section] = []
    for section, paras in zip(doc.sections, paragraphs):
        cleaned = [p for p in (clean_paragraph(p) for p in paras) if p]
        sections.append(replace(section, text="\n\n".join(cleaned)))
    return replace(doc, sections=sections)


def clean_paragraph(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("­", "")
    text = _CONTROL_CHARS.sub("", text)
    text = _HYPHEN_BREAK.sub(_join_hyphenated, text)
    return " ".join(text.split())


def _join_hyphenated(match: re.Match) -> str:
    before, after = match.group(1), match.group(2)
    if after.islower():
        return before + after  # "inter-\nnational" -> "international"
    return f"{before}-{after}"  # "Anglo-\nSaxon" keeps its hyphen


def _split_paragraphs(text: str) -> list[str]:
    return [p for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]


def _edge_key(paragraph: str) -> str:
    return re.sub(r"\d+", "#", " ".join(paragraph.split())).lower()


def _strip_repeated_edges(pages: list[list[str]]) -> list[list[str]]:
    n_pages = len(pages)
    if n_pages < _MIN_PAGES_FOR_HEADER_DETECTION:
        return pages

    def edge_indexes(paras: list[str]) -> set[int]:
        last = len(paras) - 1
        return set(range(min(_EDGE_BLOCKS, len(paras)))) | set(range(max(0, last - _EDGE_BLOCKS + 1), last + 1))

    counts: Counter[str] = Counter()
    for paras in pages:
        keys = {
            _edge_key(paras[i])
            for i in edge_indexes(paras)
            if len(paras[i]) <= _MAX_HEADER_CHARS
        }
        counts.update(k for k in keys if k)

    threshold = max(3, math.ceil(0.3 * n_pages))
    repeated = {k for k, c in counts.items() if c >= threshold}
    if not repeated:
        return pages

    stripped = []
    for paras in pages:
        edges = edge_indexes(paras)
        stripped.append(
            [p for i, p in enumerate(paras) if not (i in edges and len(p) <= _MAX_HEADER_CHARS and _edge_key(p) in repeated)]
        )
    return stripped
