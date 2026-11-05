import re

import pytest

from app.rag.chunking import ChunkingConfig, chunk_document, estimate_tokens
from app.rag.cleaning import clean_document
from app.rag.extraction import extract_document
from app.rag.models import ExtractedDocument, Section


def sentence(i: int) -> str:  # 10 words -> 13 estimated tokens
    return f"Sentence number {i} walks along the quiet river bank today."


def paragraph(start: int, n: int) -> str:
    return " ".join(sentence(i) for i in range(start, start + n))


def doc_of(sections, kind="pdf"):
    return ExtractedDocument(kind, sections, total_pages=max((s.page or 0) for s in sections) or None)


def test_small_book_maps_pages_and_chapters(pdf_path):
    chunks = chunk_document("b1", clean_document(extract_document(pdf_path, "pdf")))
    assert [c.order_index for c in chunks] == list(range(len(chunks)))
    assert chunks[0].chunk_id == "b1:0" and chunks[0].book_id == "b1"
    assert {c.chapter for c in chunks} == {1, 2}
    assert chunks[0].chapter_title == "Part One: The Dragon"
    for c in chunks:
        assert (c.page_start <= 4 and c.page_end <= 4) or (c.page_start >= 5 and c.page_end >= 5)
    assert chunks[0].page_start == 1 and chunks[-1].page_end == 8


def test_no_chunk_crosses_a_chapter():
    sections = [Section(0, "Alpha one.", page=1, chapter=1), Section(1, "Beta two.", page=2, chapter=2)]
    chunks = chunk_document("b", doc_of(sections))
    assert [(c.chapter, c.text) for c in chunks] == [(1, "Alpha one."), (2, "Beta two.")]


def test_size_bound_and_overlap():
    config = ChunkingConfig(target_tokens=100, overlap_ratio=0.2)
    text = "\n\n".join(paragraph(i * 10, 6) for i in range(8))  # paragraphs of 78 tokens
    chunks = chunk_document("b", doc_of([Section(0, text, page=1, chapter=1)]), config)
    assert len(chunks) > 1
    assert all(0 < c.token_count <= 100 for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:]):
        last_sentence = re.split(r"(?<=\.)\s+", prev.text.strip())[-1]
        assert last_sentence in nxt.text


def test_zero_overlap_repeats_nothing():
    config = ChunkingConfig(target_tokens=100, overlap_ratio=0.0)
    assert config.overlap_tokens == 0
    text = "\n\n".join(paragraph(i * 10, 6) for i in range(6))
    chunks = chunk_document("b", doc_of([Section(0, text, page=1, chapter=1)]), config)
    joined = " ".join(c.text for c in chunks)
    assert all(joined.count(sentence(i)) == 1 for i in range(0, 60, 10))


def test_overlap_dropped_when_it_leaves_no_room():
    # 78-token paragraph, then a 91-token one: 78 + 91 > 100, and even the
    # 39-token overlap tail + 91 > 100, so the second chunk starts clean.
    config = ChunkingConfig(target_tokens=100, overlap_ratio=0.4)
    text = paragraph(0, 6) + "\n\n" + paragraph(100, 7)
    chunks = chunk_document("b", doc_of([Section(0, text, page=1, chapter=1)]), config)
    assert len(chunks) == 2
    assert chunks[1].text == paragraph(100, 7)


def test_no_overlap_when_no_sentence_fits_budget():
    long_sentence = " ".join(f"w{i}" for i in range(30)) + "."  # 39 tokens
    text = long_sentence + "\n\n" + long_sentence + "\n\n" + long_sentence
    config = ChunkingConfig(target_tokens=80, overlap_ratio=0.1)  # budget 8 tokens
    chunks = chunk_document("b", doc_of([Section(0, text, page=1, chapter=1)]), config)
    assert len(chunks) == 2
    assert chunks[1].text == long_sentence


def test_oversized_paragraph_and_unpunctuated_text_are_split():
    config = ChunkingConfig(target_tokens=60, overlap_ratio=0.1)
    giant = " ".join(f"word{i}" for i in range(400))  # no sentence breaks at all
    chunks = chunk_document("b", doc_of([Section(0, giant, page=1, chapter=1)]), config)
    assert len(chunks) > 3
    assert all(c.token_count <= 60 for c in chunks)
    assert {w for c in chunks for w in c.text.split()} == {f"word{i}" for i in range(400)}


def test_oversized_paragraph_split_on_sentences():
    config = ChunkingConfig(target_tokens=60, overlap_ratio=0.0)
    chunks = chunk_document("b", doc_of([Section(0, paragraph(0, 12), page=1, chapter=1)]), config)
    assert len(chunks) > 1
    assert all(c.text.endswith("today.") for c in chunks)  # cut on sentence boundaries


def test_pages_tracked_across_pages():
    sections = [Section(i, f"Page {i + 1} has one short line.", page=i + 1) for i in range(3)]
    chunks = chunk_document("b", doc_of(sections))  # no chapters -> one group
    assert len(chunks) == 1
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 3)
    assert chunks[0].source_location == "pages 1-3"
    assert chunks[0].position == 3


def test_overlap_keeps_earliest_page():
    config = ChunkingConfig(target_tokens=100, overlap_ratio=0.2)
    sections = [
        Section(0, paragraph(0, 6), page=1),
        Section(1, paragraph(10, 6), page=2),
    ]
    chunks = chunk_document("b", doc_of(sections), config)
    assert len(chunks) == 2
    assert (chunks[1].page_start, chunks[1].page_end) == (1, 2)  # overlap came from page 1


def test_epub_chunks_use_chapter_position(epub_path):
    chunks = chunk_document("e", clean_document(extract_document(epub_path, "epub")))
    assert [c.chapter for c in chunks] == [1, 2, 3]
    assert all(c.page_start is None and c.page_end is None for c in chunks)
    assert [c.position for c in chunks] == [1, 2, 3]
    assert chunks[1].source_location == "chapter 2"


def test_long_epub_chapter_splits_without_page_numbers():
    config = ChunkingConfig(target_tokens=100, overlap_ratio=0.2)
    text = "\n\n".join(paragraph(i * 10, 6) for i in range(5))
    chunks = chunk_document("e", doc_of([Section(0, text, page=None, chapter=1)], kind="epub"), config)
    assert len(chunks) > 1
    assert all(c.page_start is None and c.chapter == 1 for c in chunks)


def test_empty_and_blank_content_is_skipped():
    sections = [Section(0, "", page=1), Section(1, "First para.\n\n   \n\nSecond para.", page=2)]
    chunks = chunk_document("b", doc_of(sections))
    assert len(chunks) == 1
    assert chunks[0].page_start == 2
    assert chunks[0].text == "First para.\n\nSecond para."


def test_empty_document_gives_no_chunks():
    assert chunk_document("b", doc_of([Section(0, "  ", page=1)])) == []


def test_hash_depends_only_on_text():
    a = chunk_document("x", doc_of([Section(0, "Real text here.", page=2)]))[0]
    b = chunk_document("y", doc_of([Section(0, "Real text here.", page=9)]))[0]
    assert a.text_hash == b.text_hash


def test_config_validation_and_token_estimate():
    with pytest.raises(ValueError, match="target_tokens"):
        ChunkingConfig(target_tokens=5)
    with pytest.raises(ValueError, match="overlap_ratio"):
        ChunkingConfig(overlap_ratio=0.9)
    with pytest.raises(ValueError, match="overlap_ratio"):
        ChunkingConfig(overlap_ratio=-0.1)
    assert ChunkingConfig().overlap_tokens == 48
    assert estimate_tokens("") == 0
    assert estimate_tokens("one two three") == 4


def test_overlap_tail_can_span_several_small_units():
    config = ChunkingConfig(target_tokens=100, overlap_ratio=0.4)  # 40-token overlap budget
    small = [sentence(i) for i in range(5)]  # five 13-token paragraphs = 65 tokens
    big = paragraph(100, 4)  # 52 tokens: 65 + 52 > 100, but 39 (3 sentences) + 52 fits
    text = "\n\n".join(small + [big])
    chunks = chunk_document("b", doc_of([Section(0, text, page=1, chapter=1)]), config)
    assert len(chunks) == 2
    assert chunks[1].text == " ".join(small[2:]) + "\n\n" + big


def test_whole_short_chunk_is_too_big_to_reuse_as_overlap():
    config = ChunkingConfig(target_tokens=100, overlap_ratio=0.4)
    text = "\n\n".join([sentence(0), sentence(1), paragraph(100, 7)])  # 13 + 13 + 91 tokens
    chunks = chunk_document("b", doc_of([Section(0, text, page=1, chapter=1)]), config)
    assert len(chunks) == 2
    assert chunks[1].text == paragraph(100, 7)  # 26 + 91 > 100, so no overlap
