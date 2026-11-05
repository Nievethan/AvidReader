import bs4
import ebooklib
import pymupdf
import pytest
from ebooklib import epub

from app.rag import extraction
from app.rag.extraction import (
    ExtractionError,
    ScannedDocumentError,
    _page_chapter_map,
    extract_document,
)
from app.rag.models import TocEntry
from tests.rag.conftest import build_blank_pdf, build_pdf


# ---- helpers: fake PyMuPDF / ebooklib objects ------------------------------


class FakePage:
    def __init__(self, blocks=None, error=None):
        self._blocks, self._error = blocks or [], error

    def get_text(self, mode, sort=False):
        if self._error:
            raise self._error
        return self._blocks


def text_block(text, block_type=0):
    return (0, 0, 0, 0, text, 0, block_type)


class FakeDoc:
    def __init__(self, pages, needs_pass=False, toc=None, toc_error=None):
        self._pages = pages
        self.needs_pass = needs_pass
        self.page_count = len(pages)
        self._toc, self._toc_error = toc or [], toc_error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getitem__(self, index):
        return self._pages[index]

    def get_toc(self, simple=True):
        if self._toc_error:
            raise self._toc_error
        return self._toc


def patch_pdf_open(monkeypatch, doc):
    monkeypatch.setattr(pymupdf, "open", lambda path: doc)


LONG = "x" * 80


class FakeEpubItem:
    def __init__(self, content, item_type=ebooklib.ITEM_DOCUMENT):
        self._content, self._type = content, item_type

    def get_type(self):
        return self._type

    def get_content(self):
        return self._content


class FakeBook:
    def __init__(self, spine, items):
        self.spine, self._items = spine, items

    def get_item_with_id(self, item_id):
        return self._items.get(item_id)


def patch_epub(monkeypatch, book):
    monkeypatch.setattr(epub, "read_epub", lambda path, options=None: book)


# ---- dispatch ----------------------------------------------------------------


def test_extract_document_dispatches_and_normalises_type(pdf_path, epub_path):
    assert extract_document(pdf_path, ".PDF").kind == "pdf"
    assert extract_document(epub_path, "epub").kind == "epub"


def test_unknown_type_rejected(tmp_path):
    with pytest.raises(ExtractionError, match="Unsupported"):
        extract_document(tmp_path / "x.docx", "docx")


# ---- PDF -----------------------------------------------------------------------


def test_pdf_pages_and_text(pdf_path):
    doc = extract_document(pdf_path, "pdf")
    assert doc.total_pages == 8
    assert [s.page for s in doc.sections] == list(range(1, 9))
    assert [s.order_index for s in doc.sections] == list(range(8))
    assert "dragon Ignis" in doc.sections[0].text
    assert "Orrin" in doc.sections[4].text


def test_pdf_toc_assigns_chapters(pdf_path):
    doc = extract_document(pdf_path, "pdf")
    assert [t.title for t in doc.toc] == ["Part One: The Dragon", "Part Two: The Sea"]
    assert [s.chapter for s in doc.sections] == [1, 1, 1, 1, 2, 2, 2, 2]
    assert doc.sections[5].chapter_title == "Part Two: The Sea"


def test_pdf_without_toc_has_no_chapters(tmp_path):
    doc = extract_document(build_pdf(tmp_path / "n.pdf", with_toc=False), "pdf")
    assert doc.toc == []
    assert all(s.chapter is None and s.chapter_title is None for s in doc.sections)


def test_scanned_pdf_is_detected(tmp_path):
    with pytest.raises(ScannedDocumentError, match="scanned"):
        extract_document(build_blank_pdf(tmp_path / "scan.pdf"), "pdf")


def test_scanned_error_is_an_extraction_error():
    assert issubclass(ScannedDocumentError, ExtractionError)


def test_unreadable_pdf_raises_extraction_error(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    with pytest.raises(ExtractionError, match="Could not open PDF"):
        extract_document(bad, "pdf")


def test_password_protected_pdf(monkeypatch, tmp_path):
    patch_pdf_open(monkeypatch, FakeDoc([FakePage()], needs_pass=True))
    with pytest.raises(ExtractionError, match="password"):
        extract_document(tmp_path / "x.pdf", "pdf")


def test_pdf_with_zero_pages(monkeypatch, tmp_path):
    patch_pdf_open(monkeypatch, FakeDoc([]))
    with pytest.raises(ExtractionError, match="no pages"):
        extract_document(tmp_path / "x.pdf", "pdf")


def test_page_read_failure_reports_page_number(monkeypatch, tmp_path):
    pages = [FakePage([text_block(LONG)]), FakePage(error=RuntimeError("boom"))]
    patch_pdf_open(monkeypatch, FakeDoc(pages))
    with pytest.raises(ExtractionError, match="page 2"):
        extract_document(tmp_path / "x.pdf", "pdf")


def test_image_and_blank_blocks_are_ignored(monkeypatch, tmp_path):
    page = FakePage([text_block(LONG), text_block("IMAGE", block_type=1), text_block("   \n")])
    patch_pdf_open(monkeypatch, FakeDoc([page]))
    doc = extract_document(tmp_path / "x.pdf", "pdf")
    assert doc.sections[0].text == LONG


def test_broken_toc_does_not_fail_extraction(monkeypatch, tmp_path):
    patch_pdf_open(monkeypatch, FakeDoc([FakePage([text_block(LONG)])], toc_error=RuntimeError("bad outline")))
    doc = extract_document(tmp_path / "x.pdf", "pdf")
    assert doc.toc == []


def test_invalid_toc_entries_are_dropped(monkeypatch, tmp_path):
    toc = [[1, "Good", 1], [1, "Past the end", 99], [1, "Before start", 0], [1, "   ", 1]]
    patch_pdf_open(monkeypatch, FakeDoc([FakePage([text_block(LONG)])], toc=toc))
    doc = extract_document(tmp_path / "x.pdf", "pdf")
    assert doc.toc == [TocEntry(level=1, title="Good", page=1)]


def test_page_chapter_map_front_matter_and_duplicates():
    toc = [
        TocEntry(1, "Ch A", 3),
        TocEntry(1, "Ch A again", 3),  # same page: first wins
        TocEntry(1, "Ch B", 5),
        TocEntry(2, "Nested section", 4),  # deeper level ignored
    ]
    mapping = _page_chapter_map(toc, 6)
    assert mapping == [(0, None), (0, None), (1, "Ch A"), (1, "Ch A"), (2, "Ch B"), (2, "Ch B")]


def test_page_chapter_map_uses_shallowest_level():
    toc = [TocEntry(2, "Only deep", 1), TocEntry(3, "Deeper", 2)]
    assert _page_chapter_map(toc, 2) == [(1, "Only deep"), (1, "Only deep")]


def test_page_chapter_map_without_toc():
    assert _page_chapter_map([], 3) == [(None, None)] * 3


# ---- EPUB ----------------------------------------------------------------------


def test_epub_spine_is_chapters_and_nav_is_skipped(epub_path):
    doc = extract_document(epub_path, "epub")
    assert doc.total_pages is None and doc.toc == []
    assert [s.chapter for s in doc.sections] == [1, 2, 3]
    assert [s.order_index for s in doc.sections] == [0, 1, 2]
    assert [s.chapter_title for s in doc.sections] == ["Chapter One", "Chapter Two", "Chapter Three"]
    assert all(s.page is None for s in doc.sections)
    assert "lighthouse keeper" in doc.sections[0].text
    assert "None ever came." in doc.sections[0].text


def test_invalid_epub(tmp_path):
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"nope")
    with pytest.raises(ExtractionError, match="Could not open EPUB"):
        extract_document(bad, "epub")


def test_epub_edge_cases(monkeypatch, tmp_path):
    items = {
        "plain-id": FakeEpubItem(b"<html><body><h2>Two</h2><p>Plain id spine entry.</p></body></html>"),
        "tuple-id": FakeEpubItem(
            b"<html><head><style>p{}</style><script>var x=1;</script></head><body>"
            b"<blockquote><p>Nested quote text.</p></blockquote><p></p><p>Tail.</p></body></html>"
        ),
        "image": FakeEpubItem(b"binary", item_type=ebooklib.ITEM_IMAGE),
        "empty": FakeEpubItem(b"<html><body><div>no block tags</div></body></html>"),
        "bad": FakeEpubItem(b"BAD"),
    }
    spine = ["plain-id", ("tuple-id", "yes"), "missing-id", ("image", "no"), ("empty", "yes"), ("bad", "yes")]
    patch_epub(monkeypatch, FakeBook(spine, items))

    real_soup = bs4.BeautifulSoup

    def soup(content, features):
        if content == b"BAD":
            raise ValueError("unparseable")
        return real_soup(content, features)

    monkeypatch.setattr(bs4, "BeautifulSoup", soup)

    doc = extraction.extract_epub(tmp_path / "x.epub")
    assert [s.chapter for s in doc.sections] == [1, 2]
    assert doc.sections[0].chapter_title == "Two"
    assert doc.sections[1].chapter_title is None  # no heading
    assert doc.sections[1].text == "Nested quote text.\n\nTail."  # nested block counted once; script/style dropped


def test_epub_nav_item_is_skipped(monkeypatch, tmp_path):
    nav = epub.EpubNav()
    nav.get_type = lambda: ebooklib.ITEM_DOCUMENT  # some EPUBs report nav as a document
    nav.get_content = lambda: b"<html><body><p>Table of contents entry</p></body></html>"
    chapter = FakeEpubItem(b"<html><body><p>Real story text.</p></body></html>")
    patch_epub(monkeypatch, FakeBook(["nav", "ch"], {"nav": nav, "ch": chapter}))
    doc = extraction.extract_epub(tmp_path / "x.epub")
    assert [s.text for s in doc.sections] == ["Real story text."]


def test_epub_without_text_is_rejected(monkeypatch, tmp_path):
    patch_epub(monkeypatch, FakeBook([("a", "yes")], {"a": FakeEpubItem(b"<html><body></body></html>")}))
    with pytest.raises(ExtractionError, match="no readable text"):
        extraction.extract_epub(tmp_path / "x.epub")
