"""Structure-aware recursive chunker.

1. Track Markdown-style headings ("# ...") so each chunk carries its section title.
2. Split each section recursively on paragraph -> line -> sentence -> word boundaries until every piece fits.
3. Greedily merge pieces into chunks of at most `chunk_size` characters, carrying `chunk_overlap` characters
   of trailing whole pieces into the next chunk so context is not severed at boundaries.
Chunk size/overlap defaults were selected with evaluation/retrieval_benchmark.py (see RAG_EVALUATION_REPORT.md).
"""
import re
from typing import Dict, List, Optional

from app.config.settings import settings

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_SEPARATORS = ["\n\n", "\n", r"(?<=[.!?])\s+", " "]


def _split_recursive(text: str, size: int, level: int = 0) -> List[str]:
    if len(text) <= size:
        return [text]
    if level >= len(_SEPARATORS):
        return [text[i:i + size] for i in range(0, len(text), size)]
    sep = _SEPARATORS[level]
    parts = re.split(sep, text) if level == 2 else text.split(sep)
    out: List[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) > size:
            out.extend(_split_recursive(part, size, level + 1))
        else:
            out.append(part)
    return out


class TextChunker:
    def __init__(self, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP if chunk_overlap is None else chunk_overlap
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

    def _sections(self, blocks: List[Dict]) -> List[Dict]:
        """Split blocks into (section, page, text) units at heading lines."""
        units, current_section = [], None
        for block in blocks:
            page = int(block.get("page_number") or 1)
            if block.get("section"):
                current_section = str(block["section"])
            buf: List[str] = []
            # Only Markdown-derived text (md files, DOCX headings) has real "#" headings. In PDFs/TXT a leading "#"
            # is usually a code or shell comment, so heading detection is disabled there.
            markdown = bool(block.get("markdown"))
            in_fence = False
            for line in str(block["text"]).split("\n"):
                if line.strip().startswith("```"):
                    in_fence = not in_fence
                m = _HEADING.match(line.strip()) if markdown and not in_fence else None
                if m:
                    if "".join(buf).strip():
                        units.append({"section": current_section, "page": page, "text": "\n".join(buf).strip()})
                    current_section = m.group(2).strip()[:300]
                    buf = [line.strip()]  # keep the heading text in the chunk for lexical matching
                else:
                    buf.append(line)
            if "".join(buf).strip():
                units.append({"section": current_section, "page": page, "text": "\n".join(buf).strip()})
        return units

    def _merge(self, pieces: List[str]) -> List[str]:
        chunks, current, length = [], [], 0
        for piece in pieces:
            add = len(piece) + (1 if current else 0)
            if current and length + add > self.chunk_size:
                chunks.append("\n".join(current))
                # carry trailing pieces up to the overlap budget
                carry, carry_len = [], 0
                for prev in reversed(current):
                    if carry_len + len(prev) + 1 > self.chunk_overlap:
                        break
                    carry.insert(0, prev)
                    carry_len += len(prev) + 1
                current, length = carry, sum(len(c) + 1 for c in carry)
            current.append(piece)
            length += len(piece) + (1 if len(current) > 1 else 0)
        if current:
            chunks.append("\n".join(current))
        return chunks

    def chunk_document(self, blocks: List[Dict]) -> List[Dict]:
        out, idx = [], 0
        for unit in self._sections(blocks):
            pieces = _split_recursive(unit["text"], self.chunk_size)
            for text in self._merge(pieces):
                text = text.strip()
                # Skip fragments that are only a heading or punctuation.
                if len(re.sub(r"[#\W_]+", "", text)) < 3:
                    continue
                out.append({"chunk_index": idx, "text_content": text, "page_number": unit["page"],
                            "section": unit["section"]})
                idx += 1
        return out
