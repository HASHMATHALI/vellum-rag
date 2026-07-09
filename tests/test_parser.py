import sys
import os
import tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.ingestion.parser import FileParser

def test_txt_parsing():
    # Create temp text file
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w+", delete=False, encoding="utf-8") as f:
        f.write("Line 1 sample text for parser validation.\nLine 2 another sentence.")
        filepath = f.name
        
    try:
        pages = FileParser.parse(filepath, "txt")
        assert len(pages) == 1
        assert "Line 1" in pages[0]["text"]
        assert pages[0]["page_number"] == 1
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)
            
def test_unsupported_parsing():
    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
        filepath = f.name
    try:
        FileParser.parse(filepath, "xyz")
        assert False, "Should have raised ValueError for unsupported format"
    except ValueError:
        pass
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)
