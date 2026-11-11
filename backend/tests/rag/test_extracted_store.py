import pytest

from app.rag.extracted_store import ExtractedTextStore
from app.rag.models import ExtractedDocument, Section


def pdf_doc(n=3):
    return ExtractedDocument("pdf", [Section(i, f"page {i + 1} text", page=i + 1) for i in range(n)], n)


def test_save_and_read_pdf_pages(tmp_path):
    store = ExtractedTextStore(tmp_path / "x")
    store.save("b", pdf_doc())
    unit = store.get_unit("b", 2)
    assert (unit.unit, unit.index, unit.total, unit.title, unit.text) == ("page", 2, 3, None, "page 2 text")
    assert store.exists("b")
    assert not (tmp_path / "x" / "b.tmp").exists()  # written atomically


def test_epub_chapters_keep_titles(tmp_path):
    store = ExtractedTextStore(tmp_path)
    doc = ExtractedDocument("epub", [Section(0, "one", chapter=1, chapter_title="Start"), Section(1, "two", chapter=2)], None)
    store.save("e", doc)
    assert store.get_unit("e", 1).title == "Start"
    assert store.get_unit("e", 2).unit == "chapter"


def test_missing_book_and_out_of_range(tmp_path):
    store = ExtractedTextStore(tmp_path)
    assert store.get_unit("nope", 1) is None
    store.save("b", pdf_doc(2))
    with pytest.raises(IndexError, match=r"Page 3 is out of range \(1-2\)"):
        store.get_unit("b", 3)
    with pytest.raises(IndexError):
        store.get_unit("b", 0)


def test_cache_is_refreshed_on_resave_and_bounded(tmp_path):
    store = ExtractedTextStore(tmp_path)
    store.save("b", pdf_doc(1))
    assert store.get_unit("b", 1).text == "page 1 text"
    assert store.get_unit("b", 1).text == "page 1 text"  # served from cache
    store.save("b", ExtractedDocument("pdf", [Section(0, "changed", page=1)], 1))
    assert store.get_unit("b", 1).text == "changed"
    for i in range(6):
        store.save(f"book{i}", pdf_doc(1))
        store.get_unit(f"book{i}", 1)
    assert len(store._cache) == 4


def test_delete(tmp_path):
    store = ExtractedTextStore(tmp_path)
    store.save("b", pdf_doc(1))
    store.get_unit("b", 1)
    store.delete("b")
    assert not store.exists("b") and store.get_unit("b", 1) is None
    store.delete("b")  # missing file is fine


def test_section_without_page_or_chapter_uses_its_position(tmp_path):
    store = ExtractedTextStore(tmp_path)
    store.save("b", ExtractedDocument("pdf", [Section(0, "a"), Section(1, "b")], 2))
    assert store.get_unit("b", 2).text == "b"
