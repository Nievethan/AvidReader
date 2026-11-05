"""Step 2: text extraction with page/chapter metadata.

PDF  -> one Section per page (chapter from the PDF's table of contents if it
        has one, otherwise None). Boundary unit is the page.
EPUB -> one Section per non-empty spine item; chapter == its 1-based number
        in reading order, page is None. Boundary unit is the chapter.

Output is *raw*: PDF text keeps block structure ("\\n\\n" between blocks,
"\\n" between lines) so `cleaning` can strip headers/footers and reflow.
"""
from __future__ import annotations

import logging
import warnings
from pathlib import Path

from app.rag.models import ExtractedDocument, Section, TocEntry

logger = logging.getLogger(__name__)

# Below this average, a PDF is treated as scanned/image-only (no OCR yet).
MIN_AVG_CHARS_PER_PAGE = 50
MIN_EPUB_SECTION_CHARS = 1

_BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "dt", "dd", "figcaption"]


class ExtractionError(Exception):
    """The file could not be read as the declared type."""


class ScannedDocumentError(ExtractionError):
    """The PDF has (almost) no text layer. Ingestion should report
    status="unsupported"; OCR is out of scope for now."""

# Detemring the file type: checks for 
def extract_document(path: str | Path, file_type: str) -> ExtractedDocument:
    kind = file_type.lower().lstrip(".")
    if kind == "pdf":
        return extract_pdf(path)
    if kind == "epub":
        return extract_epub(path)
    raise ExtractionError(f"Unsupported file type: {file_type!r}")


# ---- PDF -------------------------------------------------------------------


def extract_pdf(path: str | Path) -> ExtractedDocument:
    import pymupdf

    try:
        doc = pymupdf.open(str(path)) # try to `open` the PDF file using pymupdf
    except Exception as exc:
        raise ExtractionError(f"Could not open PDF: {exc}") from exc

    with doc:
        if doc.needs_pass:
            raise ExtractionError("PDF is password protected.")
        total_pages = doc.page_count
        if total_pages == 0:
            raise ExtractionError("PDF has no pages.")

        toc = _read_pdf_toc(doc, total_pages) # tries to read the table of contents (TOC) of the PDF
        page_chapters = _page_chapter_map(toc, total_pages)

        sections: list[Section] = []
        total_chars = 0
        for index in range(total_pages):
            try:
                blocks = doc[index].get_text("blocks", sort=True)
            except Exception as exc:
                raise ExtractionError(f"Could not read PDF page {index + 1}: {exc}") from exc
            # block tuple: (x0, y0, x1, y1, text, block_no, block_type); 0 == text
            text = "\n\n".join(b[4].strip() for b in blocks if b[6] == 0 and b[4].strip())
            total_chars += len(text.strip())
            chapter, title = page_chapters[index]
            sections.append(
                Section(order_index=index, text=text, page=index + 1, chapter=chapter, chapter_title=title)
            )

    if total_chars / total_pages < MIN_AVG_CHARS_PER_PAGE:
        raise ScannedDocumentError(
            "This PDF has little or no selectable text (it looks scanned). "
            "Scanned PDFs are not supported yet."
        )
    return ExtractedDocument(kind="pdf", sections=sections, total_pages=total_pages, toc=toc)


def _read_pdf_toc(doc, total_pages: int) -> list[TocEntry]:
    try:
        raw = doc.get_toc(simple=True)
    except Exception:  # a broken outline must not fail the whole ingestion
        logger.warning("Could not read PDF table of contents", exc_info=True)
        return []
    entries = []
    for level, title, page in raw:
        if 1 <= page <= total_pages and str(title).strip():
            entries.append(TocEntry(level=int(level), title=str(title).strip(), page=int(page)))
    return entries


def _page_chapter_map(toc: list[TocEntry], total_pages: int) -> list[tuple[int | None, str | None]]:
    """Per page (0-based): (chapter number, chapter title). Chapters are the
    top-level TOC entries. Pages before the first entry are chapter 0
    (front matter). With no TOC, every page is (None, None)."""
    top = sorted((e for e in toc if e.level == min((t.level for t in toc), default=1)), key=lambda e: e.page)
    if not top:
        return [(None, None)] * total_pages
    # Several entries on one page: keep the first.
    starts: list[TocEntry] = []
    for entry in top:
        if not starts or entry.page != starts[-1].page:
            starts.append(entry)

    result: list[tuple[int | None, str | None]] = []
    chapter, title, next_idx = 0, None, 0
    for page in range(1, total_pages + 1):
        while next_idx < len(starts) and starts[next_idx].page <= page:
            chapter, title = next_idx + 1, starts[next_idx].title
            next_idx += 1
        result.append((chapter, title))
    return result


# ---- EPUB ------------------------------------------------------------------


def extract_epub(path: str | Path) -> ExtractedDocument:
    import ebooklib
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    from ebooklib import epub

    try:
        book = epub.read_epub(str(path), options={"ignore_ncx": True})
    except Exception as exc:
        raise ExtractionError(f"Could not open EPUB: {exc}") from exc

    sections: list[Section] = []
    for item_ref in book.spine:
        item_id = item_ref[0] if isinstance(item_ref, tuple) else item_ref
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        if isinstance(item, epub.EpubNav):  # the table-of-contents page, not story text
            continue
        try:
            with warnings.catch_warnings():
                # XHTML parsed with the HTML parser is fine for text extraction.
                warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
                soup = BeautifulSoup(item.get_content(), "lxml")
        except Exception:
            logger.warning("Skipping unparseable EPUB item %s", item_id, exc_info=True)
            continue
        for tag in soup(["script", "style"]):
            tag.decompose()

        paragraphs = []
        for el in soup.find_all(_BLOCK_TAGS):
            if el.find(_BLOCK_TAGS):  # only leaf blocks, avoids duplicate text
                continue
            text = " ".join(el.get_text().split())
            if text:
                paragraphs.append(text)
        text = "\n\n".join(paragraphs)
        if len(text) < MIN_EPUB_SECTION_CHARS:
            continue

        heading = soup.find(["h1", "h2", "h3"])
        title = " ".join(heading.get_text().split()) if heading else None
        number = len(sections) + 1
        sections.append(
            Section(order_index=len(sections), text=text, page=None, chapter=number, chapter_title=title or None)
        )

    if not sections:
        raise ExtractionError("EPUB contains no readable text.")
    return ExtractedDocument(kind="epub", sections=sections, total_pages=None, toc=[])


# Section(
#     order_index=24,
#     text=(
#         "Chapter 3: Optimization Algorithms\n\n"
#         "Gradient descent is an optimization algorithm used "
#         "to minimize the loss function in machine learning.\n\n"
#         "It works by adjusting the model's weights to "
#         "reduce prediction errors."
#     ),
#     page=25,
#     chapter=3,
#     chapter_title="Optimization Algorithms"
# )

# ExtractedDocument(
#     kind="pdf",
#     total_pages=3,
#     sections=[
#         Section(
#             order_index=0,
#             text="Introduction to machine learning...",
#             page=1,
#             chapter=1,
#             chapter_title="Introduction"
#         ),
#         Section(
#             order_index=1,
#             text="Supervised learning uses labeled data...",
#             page=2,
#             chapter=2,
#             chapter_title="Supervised Learning"
#         ),
#         Section(
#             order_index=2,
#             text="Gradient descent minimizes loss...",
#             page=3,
#             chapter=3,
#             chapter_title="Optimization Algorithms"
#         )
#     ],
#     toc=[
#         TocEntry(level=1, title="Introduction", page=1),
#         TocEntry(level=1, title="Supervised Learning", page=2),
#         TocEntry(level=1, title="Optimization Algorithms", page=3)
#     ]
# )
