"""Cleaned book text saved at ingestion time, served to the reader.

One JSON file per book under `EXTRACTED_DIR`:
    {"kind": "pdf", "unit": "page", "total_pages": 250,
     "units": [{"index": 1, "title": null, "text": "..."}, ...]}

PDF units are pages (index = page number, every page kept so indexes line up
with the PDF); EPUB units are chapters (index = chapter number). Header
stripping needs the whole book, which is why the text is stored once instead
of re-extracting a page per request.
"""
from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from app.rag.models import ExtractedDocument

_CACHE_SIZE = 4  # recently read books kept parsed in memory


@dataclass(frozen=True)
class TextUnit:
    unit: str  # "page" | "chapter"
    index: int  # 1-based
    total: int
    title: str | None
    text: str


class ExtractedTextStore:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self._cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()

    def _path(self, book_id: str) -> Path:
        return self.directory / f"{book_id}.json"

    def save(self, book_id: str, doc: ExtractedDocument) -> None:
        unit = "page" if doc.kind == "pdf" else "chapter"
        units = [
            {
                "index": (section.page if unit == "page" else section.chapter) or position,
                "title": section.chapter_title,
                "text": section.text,
            }
            for position, section in enumerate(doc.sections, start=1)
        ]
        payload = {"kind": doc.kind, "unit": unit, "total_pages": doc.total_pages, "units": units}
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(book_id)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, target)  # atomic: readers never see a half-written file
        with self._lock:
            self._cache.pop(book_id, None)

    def _load(self, book_id: str) -> dict | None:
        path = self._path(book_id)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return None
        with self._lock:
            cached = self._cache.get(book_id)
            if cached and cached[0] == mtime:
                self._cache.move_to_end(book_id)
                return cached[1]
        data = json.loads(path.read_text(encoding="utf-8"))
        with self._lock:
            self._cache[book_id] = (mtime, data)
            self._cache.move_to_end(book_id)
            while len(self._cache) > _CACHE_SIZE:
                self._cache.popitem(last=False)
        return data

    def exists(self, book_id: str) -> bool:
        return self._path(book_id).exists()

    def get_unit(self, book_id: str, index: int) -> TextUnit | None:
        """The page/chapter with this 1-based index, or None if the book has
        no saved text. Raises IndexError when index is out of range."""
        data = self._load(book_id)
        if data is None:
            return None
        units = data["units"]
        if not 1 <= index <= len(units):
            raise IndexError(f"{data['unit'].capitalize()} {index} is out of range (1-{len(units)}).")
        item = units[index - 1]
        return TextUnit(unit=data["unit"], index=index, total=len(units), title=item["title"], text=item["text"])

    def delete(self, book_id: str) -> None:
        self._path(book_id).unlink(missing_ok=True)
        with self._lock:
            self._cache.pop(book_id, None)
