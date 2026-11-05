from app.rag.cleaning import clean_document, clean_paragraph
from app.rag.extraction import extract_document
from app.rag.models import ExtractedDocument, Section


def pdf_doc(texts):
    sections = [Section(i, t, page=i + 1) for i, t in enumerate(texts)]
    return ExtractedDocument("pdf", sections, len(sections))


def test_repeated_headers_and_page_numbers_removed(pdf_path):
    cleaned = clean_document(extract_document(pdf_path, "pdf"))
    for section in cleaned.sections:
        assert "TEST BOOK" not in section.text
        assert "Page " not in section.text
        assert section.text  # real content survives


def test_hyphenation_rejoined_in_pdf(pdf_path):
    cleaned = clean_document(extract_document(pdf_path, "pdf"))
    assert "international treaty" in cleaned.sections[2].text
    assert "inter-" not in cleaned.sections[2].text


def test_section_metadata_is_preserved(pdf_path):
    raw = extract_document(pdf_path, "pdf")
    cleaned = clean_document(raw)
    assert len(cleaned.sections) == len(raw.sections)
    assert [(s.page, s.chapter, s.order_index) for s in cleaned.sections] == [
        (s.page, s.chapter, s.order_index) for s in raw.sections
    ]
    assert cleaned.toc == raw.toc and cleaned.total_pages == raw.total_pages


def test_hyphen_joining_rules():
    assert clean_paragraph("an inter-\nnational deal") == "an international deal"
    assert clean_paragraph("the Anglo-\nSaxon king") == "the Anglo-Saxon king"
    assert clean_paragraph("well-known fact") == "well-known fact"


def test_reflow_whitespace_and_controls():
    assert clean_paragraph("one\ntwo   three\x00­four") == "one two threefour"
    assert clean_paragraph("ﬁnal ﬂight") == "final flight"  # ligatures


def test_too_few_pages_for_header_detection():
    doc = pdf_doc([f"HEADER\n\nbody {i}" for i in range(3)])
    assert "HEADER" in clean_document(doc).sections[0].text


def test_unique_edge_lines_are_kept():
    openings = ["Alpha opens here", "Beta begins now", "Gamma starts there", "Delta kicks off", "Epsilon leads in", "Zeta sets out"]
    doc = pdf_doc([f"{opening}\n\nbody text {i}" for i, opening in enumerate(openings)])
    cleaned = clean_document(doc)
    assert cleaned.sections[0].text.startswith("Alpha opens here")


def test_lines_differing_only_by_digits_count_as_the_same_header():
    bodies = ["apples grow", "boats float", "clouds drift", "dogs bark", "eagles soar", "foxes hide"]
    doc = pdf_doc([f"Chapter title {i}\n\n{body}" for i, body in enumerate(bodies)])
    assert clean_document(doc).sections[0].text == "apples grow"


def test_long_repeated_lines_are_not_treated_as_headers():
    long_line = "This sentence repeats on every page but is far too long to be a running header. " * 3
    doc = pdf_doc([f"{long_line}\n\nbody {i}" for i in range(6)])
    assert long_line.strip() in clean_document(doc).sections[0].text


def test_repeated_line_in_page_middle_is_kept():
    doc = pdf_doc([f"a {i}\n\nb {i}\n\nc {i}\n\nmiddle\n\nd {i}\n\ne {i}\n\nf {i}" for i in range(6)])
    assert "middle" in clean_document(doc).sections[0].text


def test_page_that_is_only_header_becomes_empty():
    texts = ["RUNNING HEAD\n\nreal text page one", "RUNNING HEAD", "RUNNING HEAD\n\nreal text page three"] + [
        f"RUNNING HEAD\n\nbody {i}" for i in range(3)
    ]
    cleaned = clean_document(pdf_doc(texts))
    assert cleaned.sections[1].text == ""
    assert cleaned.sections[0].text == "real text page one"


def test_epub_is_not_header_stripped(epub_path):
    doc = extract_document(epub_path, "epub")
    assert clean_document(doc).sections[0].text == doc.sections[0].text


def test_nothing_repeated_means_nothing_stripped():
    names = ["apples", "boats", "clouds", "dogs", "eagles"]
    texts = [f"{n} open\n\n{n} close" for n in names]
    cleaned = clean_document(pdf_doc(texts))
    assert [s.text for s in cleaned.sections] == [f"{n} open\n\n{n} close" for n in names]
