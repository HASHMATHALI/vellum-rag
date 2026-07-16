import os
import pypdf
import docx
import requests
import tempfile
from typing import List, Dict

class FileParser:
    """Service to parse content from different document types and return page-by-page text."""

    @staticmethod
    def parse_pdf(filepath: str) -> List[Dict[str, any]]:
        pages = []
        try:
            with open(filepath, "rb") as f:
                reader = pypdf.PdfReader(f)
                for idx, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text and text.strip():
                        pages.append({
                            "text": text.strip(),
                            "page_number": idx + 1
                        })
        except Exception as e:
            raise ValueError(f"Error parsing PDF file: {e}")
        return pages

    @staticmethod
    def parse_docx(filepath: str) -> List[Dict[str, any]]:
        pages = []
        try:
            doc = docx.Document(filepath)
            full_text = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    full_text.append(paragraph.text.strip())
            
            # DOCX doesn't have native "pages", so we aggregate text blocks
            # We treat every ~15 paragraphs or 1500 chars as a "page" block
            current_block = []
            char_count = 0
            page_idx = 1
            
            for para in full_text:
                current_block.append(para)
                char_count += len(para)
                if char_count > 1500:
                    pages.append({
                        "text": "\n".join(current_block),
                        "page_number": page_idx
                    })
                    current_block = []
                    char_count = 0
                    page_idx += 1
            
            if current_block:
                pages.append({
                    "text": "\n".join(current_block),
                    "page_number": page_idx
                })
        except Exception as e:
            raise ValueError(f"Error parsing DOCX file: {e}")
        return pages

    @staticmethod
    def parse_txt(filepath: str) -> List[Dict[str, any]]:
        pages = []
        try:
            # Try UTF-8 first, fallback to Latin-1
            content = ""
            for encoding in ("utf-8", "latin-1", "cp1252"):
                try:
                    with open(filepath, "r", encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if not content:
                raise ValueError("Could not decode file with supported encodings.")

            # Chunk into "pages" by character limits (~2000 chars per page block)
            chunk_size = 2000
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i+chunk_size]
                if chunk.strip():
                    pages.append({
                        "text": chunk.strip(),
                        "page_number": (i // chunk_size) + 1
                    })
        except Exception as e:
            raise ValueError(f"Error parsing text file: {e}")
        return pages

    @classmethod
    def parse(cls, filepath: str, file_type: str) -> List[Dict[str, any]]:
        """Main routing method for file parsing. Handles local paths and remote URLs."""
        is_remote = filepath.startswith("http://") or filepath.startswith("https://")
        
        target_path = filepath
        temp_file = None
        
        try:
            if is_remote:
                suffix = f".{file_type.lower().strip('.')}"
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                
                response = requests.get(filepath, timeout=30)
                response.raise_for_status()
                temp_file.write(response.content)
                temp_file.close()
                target_path = temp_file.name
                
            if not os.path.exists(target_path):
                raise FileNotFoundError(f"File not found: {target_path}")
                
            file_type = file_type.lower().strip(".")
            if file_type == "pdf":
                return cls.parse_pdf(target_path)
            elif file_type == "docx":
                return cls.parse_docx(target_path)
            elif file_type in ["txt", "md", "markdown"]:
                return cls.parse_txt(target_path)
            else:
                raise ValueError(f"Unsupported file type: .{file_type}")
                
        finally:
            if is_remote and temp_file and os.path.exists(temp_file.name):
                try:
                    os.remove(temp_file.name)
                except Exception:
                    pass
