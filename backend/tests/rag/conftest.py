"""Generated fixtures for RAG tests -- nothing copyrighted is committed."""
from __future__ import annotations

from pathlib import Path

import pytest

PAGE_TEXTS = {
    1: ["The dragon Ignis guarded the mountain pass above the village of Harrow.",
        "Every winter the villagers left bread at the stone altar to keep the dragon calm."],
    2: ["Mira, the baker's daughter, climbed the pass alone and spoke to the dragon.",
        "Ignis told her the true reason he guarded the pass: a sleeping river beneath the rock."],
    3: ["The elders signed an inter-\nnational treaty with the coastal kingdom of Valmar.",
        "The treaty promised grain in exchange for iron from the mountain mines."],
    4: ["Mira discovered the treaty was a lie and that Valmar planned to flood the valley.",
        "She ran back to Harrow to warn the elders before the first frost."],
    5: ["The sea captain Orrin sailed the ship Gannet out of the harbour at dawn.",
        "Orrin carried a sealed letter from the queen of Valmar to the northern ports."],
    6: ["A storm split the Gannet's mast and Orrin lost the letter to the waves.",
        "He swore to the crew that the letter would never reach the northern ports."],
    7: ["The crew mutinied and Orrin was left on a barren island with one barrel of water.",
        "There he met a hermit who knew the secret of the sleeping river."],
    8: ["Orrin and the hermit returned to Harrow just as the flood gates opened.",
        "Mira and Ignis stopped the water together and the valley was saved."],
}


def build_pdf(path: Path, *, with_toc: bool = True, headers: bool = True, pages: dict | None = None) -> Path:
    import pymupdf

    pages = pages or PAGE_TEXTS
    doc = pymupdf.open()
    for number, paragraphs in pages.items():
        page = doc.new_page()
        if headers:
            page.insert_text((72, 40), "THE TEST BOOK - A NOVEL", fontsize=9)
            page.insert_text((300, 780), f"Page {number}", fontsize=9)
        y = 100
        for paragraph in paragraphs:
            page.insert_textbox(pymupdf.Rect(72, y, 540, y + 120), paragraph, fontsize=11)
            y += 150
    if with_toc:
        doc.set_toc([[1, "Part One: The Dragon", 1], [1, "Part Two: The Sea", 5]])
    doc.save(str(path))
    doc.close()
    return path


def build_blank_pdf(path: Path, n_pages: int = 3) -> Path:
    import pymupdf

    doc = pymupdf.open()
    for _ in range(n_pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


def build_epub(path: Path, chapters: list[tuple[str, list[str]]]) -> Path:
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-book")
    book.set_title("Test Book")
    book.set_language("en")
    items = []
    for i, (title, paragraphs) in enumerate(chapters, start=1):
        item = epub.EpubHtml(title=title, file_name=f"ch{i}.xhtml", lang="en")
        body = "".join(f"<p>{p}</p>" for p in paragraphs)
        item.content = f"<html><body><h1>{title}</h1>{body}</body></html>"
        book.add_item(item)
        items.append(item)
    book.toc = tuple(items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    epub.write_epub(str(path), book)
    return path


@pytest.fixture()
def pdf_path(tmp_path) -> Path:
    return build_pdf(tmp_path / "book.pdf")


@pytest.fixture()
def epub_path(tmp_path) -> Path:
    return build_epub(
        tmp_path / "book.epub",
        [
            ("Chapter One", ["The lighthouse keeper counted the ships every evening.", "None ever came."]),
            ("Chapter Two", ["A ship finally appeared on the horizon carrying a stranger."]),
            ("Chapter Three", ["The stranger revealed that the lighthouse was built on a wreck."]),
        ],
    )
