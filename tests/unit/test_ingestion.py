import io
import zipfile
from pathlib import Path

import docx
import pytest
from fastapi import HTTPException

from app.ingestion import parser
from app.ingestion.chunker import TextChunker
from app.ingestion.validation import sanitize_filename, validate_upload

CORPUS = Path(__file__).resolve().parents[2] / "evaluation" / "datasets" / "corpus"


# ---------- chunking ----------
def test_chunker_respects_size_and_overlap():
    text = " ".join(f"Sentence number {i} talks about vectors and retrieval." for i in range(200))
    chunks = TextChunker(chunk_size=300, chunk_overlap=60).chunk_document([{"text": text, "page_number": 3}])
    assert len(chunks) > 5
    assert all(len(c["text_content"]) <= 300 for c in chunks)
    assert all(c["page_number"] == 3 for c in chunks)
    # consecutive chunks share some text (overlap)
    assert any(chunks[i]["text_content"].split()[-1] in chunks[i + 1]["text_content"] for i in range(len(chunks) - 1))
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_chunker_tracks_markdown_sections_but_not_code_comments():
    md = "# Install\nRun pip install.\n```bash\n# not a heading\necho hi\n```\n## Usage\nCall the API."
    chunks = TextChunker(chunk_size=200, chunk_overlap=0).chunk_document([{"text": md, "page_number": 1, "markdown": True}])
    sections = {c["section"] for c in chunks}
    assert "Install" in sections and "Usage" in sections and "not a heading" not in sections
    pdf_like = TextChunker(chunk_size=200, chunk_overlap=0).chunk_document([{"text": "# comment in code\nx = 1", "page_number": 1}])
    assert pdf_like[0]["section"] is None


def test_chunker_rejects_bad_config():
    with pytest.raises(ValueError):
        TextChunker(chunk_size=100, chunk_overlap=100)


def test_chunker_never_splits_inside_words_when_avoidable():
    text = "alpha beta gamma delta " * 100
    for c in TextChunker(chunk_size=120, chunk_overlap=20).chunk_document([{"text": text, "page_number": 1}]):
        assert all(w in {"alpha", "beta", "gamma", "delta"} for w in c["text_content"].split())


# ---------- parsing ----------
def test_parse_pdf_corpus_extracts_pages_and_strips_running_headers():
    blocks = parser.parse((CORPUS / "vellum_masterclass.pdf").read_bytes(), "pdf")
    assert len(blocks) == 14
    joined = "\n".join(b["text"] for b in blocks)
    assert "all-MiniLM-L6-v2" in joined  # hyphen kept across line breaks
    assert "Interview Masterclass Guide\nfile:///" not in joined
    assert "" not in joined


def test_parse_docx_includes_headings_and_tables():
    d = docx.Document()
    d.add_heading("Quarterly Report", level=1)
    d.add_paragraph("Revenue grew.")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text, t.cell(1, 0).text, t.cell(1, 1).text = "Region", "Sales", "EMEA", "42"
    buf = io.BytesIO()
    d.save(buf)
    blocks = parser.parse(buf.getvalue(), "docx")
    text = blocks[0]["text"]
    assert "# Quarterly Report" in text and "EMEA | 42" in text and blocks[0]["markdown"]


def test_parse_csv_rows_become_key_value_records():
    data = "name,role\nAda,engineer\nLinus,maintainer\n".encode()
    blocks = parser.parse(data, "csv")
    assert "name: Ada; role: engineer" in blocks[0]["text"]
    assert blocks[0]["section"] == "Rows 1-2"


@pytest.mark.parametrize("raw", ["café naïve".encode("utf-8"), "café naïve".encode("cp1252"), b"\xef\xbb\xbfcaf\xc3\xa9"])
def test_parse_text_encodings(raw):
    assert "caf" in parser.parse(raw, "txt")[0]["text"]


def test_parse_errors_are_meaningful():
    with pytest.raises(parser.ParseError, match="PDF"):
        parser.parse(b"%PDF-1.4 garbage that is not a pdf", "pdf")
    with pytest.raises(parser.ParseError, match="No extractable text"):
        parser.parse(b"   \n  ", "txt")
    with pytest.raises(parser.ParseError):
        parser.parse(b"PK\x03\x04not a zip", "docx")


# ---------- upload validation ----------
@pytest.mark.parametrize("name,expected", [
    ("../../etc/passwd", "passwd"), ("..\\..\\windows\\win.ini", "win.ini"), ("<script>alert(1)</script>.pdf", "script_.pdf"), ("<img src=x onerror=alert(1)>.txt", "_img src=x onerror=alert(1)_.txt"),
    ("report\x00.pdf", "report_.pdf"), ("", "document"), ("a" * 300 + ".pdf", "a" * 146 + ".pdf"),
])
def test_sanitize_filename(name, expected):
    assert sanitize_filename(name) == expected


def test_validate_upload_magic_bytes_and_types():
    assert validate_upload("a.pdf", "application/pdf", b"%PDF-1.7\n...") == "pdf"
    assert validate_upload("a.md", "text/markdown", b"# Title") == "md"
    with pytest.raises(HTTPException) as e:
        validate_upload("evil.exe", "application/octet-stream", b"MZ\x90\x00")
    assert e.value.status_code == 415
    with pytest.raises(HTTPException):
        validate_upload("fake.pdf", "application/pdf", b"MZ\x90\x00 not a pdf")  # extension/content mismatch
    with pytest.raises(HTTPException):
        validate_upload("bin.txt", "text/plain", b"abc\x00\x01\x02")  # binary disguised as text
    with pytest.raises(HTTPException) as e:
        validate_upload("a.pdf", "text/html", b"%PDF-1.7")
    assert e.value.status_code == 415


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_validate_docx_rejects_zip_bomb_traversal_and_macros():
    base = {"[Content_Types].xml": "<x/>", "word/document.xml": "<x/>"}
    with pytest.raises(HTTPException, match="zip bomb"):
        validate_upload("b.docx", "application/octet-stream", _zip({**base, "word/big.xml": b"0" * (30 * 1024 * 1024)}))
    with pytest.raises(HTTPException, match="unsafe"):
        validate_upload("t.docx", "application/octet-stream", _zip({**base, "../evil.txt": "x"}))
    with pytest.raises(HTTPException, match="Macro"):
        validate_upload("m.docx", "application/octet-stream", _zip({**base, "word/vbaProject.bin": "x"}))
    with pytest.raises(HTTPException, match="valid Word"):
        validate_upload("n.docx", "application/octet-stream", _zip({"hello.txt": "x"}))
