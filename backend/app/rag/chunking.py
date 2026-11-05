"""Step 3b: token-aware, paragraph-aligned chunking.

Rules
* a chunk never crosses a chapter (so spoiler filtering and citations stay
  accurate); documents without chapters (PDF with no TOC) are one group
* paragraphs are kept whole when they fit; oversized paragraphs are split on
  sentences, oversized sentences on words
* each new chunk starts with ~overlap_ratio of the previous chunk's trailing
  sentences so an idea on a boundary is not cut in half
* every chunk has token_count <= target_tokens

There is no tokenizer dependency: tokens are estimated as 1.3 x words, which
is close to BPE/WordPiece for English prose. 400 is a starting default;
Step 9 should compare 250 / 400 / 600.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.rag.models import Chunk, ExtractedDocument, Section

TOKENS_PER_WORD = 1.3 # tokens are estimated as 1.3 x words, which is close to BPE/WordPiece for English prose
# 400 tokens is, around 300 words, which is a reasonable chunk size for LLMs to process in one go.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 400 # max size of each chunk in tokens; 400 is a starting default
    overlap_ratio: float = 0.12 # 12% repeated from the previous chunk

    def __post_init__(self) -> None:
        if self.target_tokens < 20:
            raise ValueError("target_tokens must be >= 20")
        if not 0 <= self.overlap_ratio < 0.5:
            raise ValueError("overlap_ratio must be in [0, 0.5)")

    @property
    def overlap_tokens(self) -> int:
        return int(self.target_tokens * self.overlap_ratio)

#estimate the number of tokens in a text based on the number of words
def estimate_tokens(text: str) -> int:
    words = len(text.split())
    return math.ceil(words * TOKENS_PER_WORD) if words else 0


@dataclass(frozen=True)
class _Unit:
    text: str
    page_lo: int | None
    page_hi: int | None

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


def chunk_document(book_id: str, doc: ExtractedDocument, config: ChunkingConfig | None = None) -> list[Chunk]:
    config = config or ChunkingConfig()
    chunks: list[Chunk] = []
    for group in _chapter_groups(doc.sections):
        units = [u for s in group for u in _section_units(s, config.target_tokens)]
        for chunk_units in _pack(units, config):
            order_index = len(chunks)
            text = "\n\n".join(u.text for u in chunk_units)
            pages_lo = [u.page_lo for u in chunk_units if u.page_lo is not None]
            pages_hi = [u.page_hi for u in chunk_units if u.page_hi is not None]
            chunks.append(
                Chunk(
                    chunk_id=f"{book_id}:{order_index}",
                    book_id=book_id,
                    order_index=order_index,
                    text=text,
                    page_start=min(pages_lo) if pages_lo else None,
                    page_end=max(pages_hi) if pages_hi else None,
                    chapter=group[0].chapter,
                    chapter_title=group[0].chapter_title,
                    token_count=estimate_tokens(text),
                )
            )
    return chunks

#organize sections into groups by chapter, so that chunks never cross chapter boundaries
def _chapter_groups(sections: list[Section]) -> list[list[Section]]:
    groups: list[list[Section]] = []
    for section in sections:
        if not section.text.strip(): 
            continue
        if groups and groups[-1][0].chapter == section.chapter:  # same chapter as the current group: join it
            groups[-1].append(section)
        else: # chapter changed: start a new group
            groups.append([section])
    return groups

#breaks each section into units, which are either whole paragraphs or split paragraphs if they exceed the target token count
def _section_units(section: Section, target: int) -> list[_Unit]:
    units: list[_Unit] = []
    for paragraph in section.text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for piece in _split_oversized(paragraph, target):
            units.append(_Unit(piece, section.page, section.page))
    return units


#handle oversized paragraphs by splitting them into sentences, and if necessary, splitting sentences into words to ensure they fit within the target token count
def _split_oversized(paragraph: str, target: int) -> list[str]:
    if estimate_tokens(paragraph) <= target:
        return [paragraph]
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in _split_sentences(paragraph):
        for part in _split_words(sentence, target):
            tokens = estimate_tokens(part)
            if current and current_tokens + tokens > target:
                pieces.append(" ".join(current))
                current, current_tokens = [], 0
            current.append(part)
            current_tokens += tokens
    pieces.append(" ".join(current))  # `current` always holds at least the last part
    return pieces


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _split_words(sentence: str, target: int) -> list[str]:
    if estimate_tokens(sentence) <= target:
        return [sentence]
    words = sentence.split()
    step = max(1, int(target / TOKENS_PER_WORD))
    return [" ".join(words[i : i + step]) for i in range(0, len(words), step)]

# It takes all the paragraph units and combines them into chunks without exceeding the configured token limit.
def _pack(units: list[_Unit], config: ChunkingConfig) -> list[list[_Unit]]:
    chunks: list[list[_Unit]] = []
    current: list[_Unit] = []
    current_tokens = 0
    for unit in units:
        tokens = unit.tokens
        if current and current_tokens + tokens > config.target_tokens:
            chunks.append(current)
            current = _overlap_tail(current, config.overlap_tokens)
            current_tokens = sum(u.tokens for u in current)
            if current_tokens + tokens > config.target_tokens:
                current, current_tokens = [], 0  # no room: drop the overlap
        current.append(unit)
        current_tokens += tokens
    chunks.append(current)  # groups are never empty, so neither is `current`
    return chunks


def _overlap_tail(units: list[_Unit], budget: int) -> list[_Unit]:
    """Trailing whole sentences of the finished chunk, up to `budget` tokens,
    merged into one unit so it renders as a single paragraph."""
    if budget <= 0:
        return []
    taken: list[tuple[str, int | None]] = []
    used = 0
    done = False
    for unit in reversed(units):
        for sentence in reversed(_split_sentences(unit.text)):
            tokens = estimate_tokens(sentence)
            if used + tokens > budget:
                done = True
                break
            taken.append((sentence, unit.page_lo))
            used += tokens
        if done:
            break
    if not taken:
        return []
    taken.reverse()
    pages = [p for _, p in taken if p is not None]
    return [_Unit(" ".join(s for s, _ in taken), min(pages) if pages else None, max(pages) if pages else None)]

# Sample Chunnk Structre:
# Chunk(
#     chunk_id="ml_textbook:15",
#     book_id="ml_textbook",
#     order_index=15,
#     text=(
#         "Gradient descent is an optimization algorithm used "
#         "to minimize the loss function in machine learning. "
#         "It works by iteratively adjusting the model's weights "
#         "to reduce the difference between predicted and actual "
#         "values."
#     ),
#     page_start=25,
#     page_end=26,
#     chapter=3,
#     chapter_title="Optimization Algorithms",
#     token_count=estimate_tokens(text)
# )
