import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.ingestion.chunker import TextChunker

def test_text_chunker():
    # Setup parsed pages input
    parsed_pages = [
        {"text": "This is page one content. It contains some words that should be chunked properly.", "page_number": 1},
        {"text": "This is page two content. It has some other keywords that will go into a second chunk.", "page_number": 2}
    ]
    
    # Configure chunk size to be small to force splits
    chunker = TextChunker(chunk_size=30, chunk_overlap=10)
    chunks = chunker.chunk_document(parsed_pages)
    
    assert len(chunks) > 0
    # Check shape
    first_chunk = chunks[0]
    assert "chunk_index" in first_chunk
    assert "text_content" in first_chunk
    assert "page_number" in first_chunk
    assert first_chunk["page_number"] == 1
