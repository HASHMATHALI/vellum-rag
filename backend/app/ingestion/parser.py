"""Text extraction for PDF, DOCX, TXT, Markdown and CSV.

Each parser returns a list of blocks: {"text": str, "page_number": int, "section": Optional[str]}.
Headings are kept as Markdown "#" lines so the chunker can track sections.
"""
import csv
import io
import logging
import re
import unicodedata
from collections import Counter
from typing import Dict, List

from app.config.settings import settings

logger = logging.getLogger(__name__)
Block = Dict[str, object]


class ParseError(ValueError):
    pass


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\x00", "")
    text = re.sub("[-​﻿]", "", text)  # private-use icon glyphs, zero-width chars
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Join words split across a line break but keep the hyphen ("all-MiniLM-L6-\nv2" must stay "L6-v2").
    text = re.sub(r"(\w)-\n(\w)", r"\1-\2", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_repeated_lines(pages: List[str]) -> List[str]:
    """Remove running headers/footers: lines (digits ignored) present on more than half of the pages."""
    if len(pages) < 3:
        return pages
    key = lambda line: re.sub(r"\d+", "#", line.strip())
    counts = Counter()
    for p in pages:
        counts.update({key(l) for l in p.split("\n") if l.strip()})
    repeated = {k for k, c in counts.items() if c > len(pages) / 2 and len(k) > 3}
    return ["\n".join(l for l in p.split("\n") if key(l) not in repeated) for p in pages]


def parse_pdf(data: bytes) -> List[Block]:
    import pypdf
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                if reader.decrypt("") == 0:
                    raise ParseError("PDF is password-protected.")
            except Exception:
                raise ParseError("PDF is password-protected.")
        if len(reader.pages) > settings.MAX_PDF_PAGES:
            raise ParseError(f"PDF has more than {settings.MAX_PDF_PAGES} pages.")
        raw = []
        for page in reader.pages:
            try:
                raw.append(page.extract_text() or "")
            except Exception:  # one broken page should not fail the document
                raw.append("")
    except ParseError:
        raise
    except Exception as e:
        raise ParseError("The PDF could not be read (corrupted or unsupported).") from e
    pages = _strip_repeated_lines([normalize_text(t) for t in raw])
    return [{"text": t, "page_number": i + 1, "section": None} for i, t in enumerate(pages) if t.strip()]


def parse_docx(data: bytes) -> List[Block]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as e:
        raise ParseError("The Word document could not be read (corrupted or unsupported).") from e
    lines: List[str] = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, document)
            text = p.text.strip()
            if not text:
                continue
            style = (p.style.name or "").lower() if p.style is not None else ""
            m = re.match(r"heading (\d)", style)
            if m or style == "title":
                level = int(m.group(1)) if m else 1
                lines.append(f"{'#' * min(level, 6)} {text}")
            else:
                lines.append(text)
        elif tag == "tbl":
            table = Table(child, document)
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(cells):
                    lines.append(" | ".join(cells))
            lines.append("")
    text = normalize_text("\n\n".join(lines))
    return [{"text": text, "page_number": 1, "section": None, "markdown": True}] if text else []


def decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def parse_text(data: bytes, markdown: bool = False) -> List[Block]:
    text = normalize_text(decode_text(data))
    return [{"text": text, "page_number": 1, "section": None, "markdown": markdown}] if text else []


def parse_csv(data: bytes, rows_per_block: int = 25, max_rows: int = 100_000) -> List[Block]:
    text = decode_text(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return []
    blocks, buf, start = [], [], 1
    for n, row in enumerate(reader, start=1):
        if n > max_rows:
            logger.warning("CSV truncated at %d rows", max_rows)
            break
        if not any(c.strip() for c in row):
            continue
        pairs = [f"{header[i] if i < len(header) and header[i] else f'col{i + 1}'}: {v.strip()}"
                 for i, v in enumerate(row) if v.strip()]
        buf.append("; ".join(pairs))
        if len(buf) >= rows_per_block:
            blocks.append({"text": normalize_text("\n".join(buf)), "page_number": 1, "section": f"Rows {start}-{n}"})
            buf, start = [], n + 1
    if buf:
        blocks.append({"text": normalize_text("\n".join(buf)), "page_number": 1, "section": f"Rows {start}-{start + len(buf) - 1}"})
    return blocks


def parse(data: bytes, file_type: str) -> List[Block]:
    file_type = file_type.lower().strip(".")
    if file_type == "pdf":
        blocks = parse_pdf(data)
    elif file_type == "docx":
        blocks = parse_docx(data)
    elif file_type in ("md", "markdown"):
        blocks = parse_text(data, markdown=True)
    elif file_type == "txt":
        blocks = parse_text(data)
    elif file_type == "csv":
        blocks = parse_csv(data)
    else:
        raise ParseError(f"Unsupported file type: .{file_type}")
    total = sum(len(b["text"]) for b in blocks)
    if total > settings.MAX_EXTRACTED_CHARS:
        raise ParseError("Document contains too much text to index.")
    if total == 0:
        raise ParseError("No extractable text found (the file may be empty or a scanned image).")
    return blocks


class FileParser:
    """Backwards-compatible facade used by older call sites."""

    @staticmethod
    def parse_bytes(data: bytes, file_type: str) -> List[Block]:
        return parse(data, file_type)
