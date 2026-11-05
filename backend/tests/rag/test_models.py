from app.rag.models import Chunk


def make_chunk(**overrides) -> Chunk:
    values = dict(
        chunk_id="b:0", book_id="b", order_index=0, text="hello world",
        page_start=None, page_end=None, chapter=None, chapter_title=None, token_count=3,
    )
    values.update(overrides)
    return Chunk(**values)


def test_position_prefers_last_page():
    assert make_chunk(page_start=4, page_end=6, chapter=2).position == 6


def test_position_falls_back_to_chapter_then_zero():
    assert make_chunk(chapter=3).position == 3
    assert make_chunk().position == 0


def test_source_location_variants():
    assert make_chunk(page_start=5, page_end=5).source_location == "page 5"
    assert make_chunk(page_start=5, page_end=7).source_location == "pages 5-7"
    assert make_chunk(chapter=2).source_location == "chapter 2"
    assert make_chunk(order_index=4).source_location == "section 5"


def test_text_hash_is_stable_and_content_based():
    assert make_chunk().text_hash == make_chunk(chunk_id="other").text_hash
    assert make_chunk().text_hash != make_chunk(text="different").text_hash
    assert len(make_chunk().text_hash) == 64
