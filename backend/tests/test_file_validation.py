from __future__ import annotations

from app.services.file_validation import detect_file_type, sanitize_filename
from tests.conftest import make_minimal_epub_bytes, make_minimal_pdf_bytes


def test_detect_file_type_recognizes_real_pdf():
    assert detect_file_type(make_minimal_pdf_bytes()) == "pdf"


def test_detect_file_type_recognizes_real_epub():
    assert detect_file_type(make_minimal_epub_bytes()) == "epub"


def test_detect_file_type_rejects_plain_text():
    assert detect_file_type(b"just some text") is None


def test_detect_file_type_rejects_zip_without_epub_mimetype():
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("not_mimetype.txt", "hello")
    assert detect_file_type(buffer.getvalue()) is None


def test_detect_file_type_rejects_corrupt_zip():
    assert detect_file_type(b"PK\x03\x04garbage-not-a-real-zip") is None


def test_sanitize_filename_strips_path_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\config") == "config"


def test_sanitize_filename_strips_unsafe_characters():
    assert sanitize_filename("my book! (final) <v2>.pdf") == "my_book_final_v2_.pdf"


def test_sanitize_filename_never_empty():
    assert sanitize_filename("...") == "upload"
