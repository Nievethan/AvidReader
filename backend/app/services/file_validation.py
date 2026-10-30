"""Upload validation: real content checks, not just trusting extensions."""
from __future__ import annotations

import re
import zipfile
from io import BytesIO

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str) -> str:
    """Strip any path components and unsafe characters. Never trust a
    client-supplied filename as a filesystem path."""
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    base = _SAFE_NAME_RE.sub("_", base).strip("._") or "upload"
    return base[-255:]


def detect_file_type(raw: bytes) -> str | None:
    """Inspect file contents (not the extension/MIME header) to decide
    pdf vs epub. Returns None if neither signature matches."""
    if raw.startswith(b"%PDF-"):
        return "pdf"

    if raw[:2] == b"PK":
        try:
            with zipfile.ZipFile(BytesIO(raw)) as zf:
                mimetype_bytes = zf.read("mimetype")
        except (KeyError, zipfile.BadZipFile):
            return None
        if mimetype_bytes.strip() == b"application/epub+zip":
            return "epub"

    return None
