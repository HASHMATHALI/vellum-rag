from typing import List, Dict
from app.config.settings import settings

class TextChunker:
    """Chunks documents into pieces of text with a sliding window overlay, preserving source pages."""

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    def chunk_document(self, parsed_pages: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Takes a list of parsed pages and splits their text into overlapping chunks."""
        chunks = []
        chunk_idx = 0

        for page in parsed_pages:
            text = page["text"]
            page_num = page["page_number"]
            
            if not text:
                continue

            # Implement overlapping sliding window split
            words = text.split()
            # Approximate characters check: we split by words to avoid splitting inside words
            i = 0
            while i < len(words):
                # Build chunk up to chunk_size characters
                current_words = []
                current_len = 0
                
                # Consume words until we exceed chunk_size
                j = i
                while j < len(words) and current_len < self.chunk_size:
                    word = words[j]
                    current_words.append(word)
                    current_len += len(word) + 1 # +1 for space
                    j += 1
                
                chunk_text = " ".join(current_words).strip()
                if chunk_text:
                    chunks.append({
                        "chunk_index": chunk_idx,
                        "text_content": chunk_text,
                        "page_number": page_num
                    })
                    chunk_idx += 1
                
                # Advance step with overlap
                # Calculate how many words we should skip back for overlap
                # If we processed from i to j, the next chunk should start at some index between i and j.
                # Let's say we want to step forward by (chunk_size - chunk_overlap) characters.
                # We can approximate this by step size in words.
                consumed_words_count = j - i
                if consumed_words_count <= 1 or j == len(words):
                    i = j
                else:
                    # Estimate average word length is 6 characters
                    avg_word_len = 6
                    overlap_words = self.chunk_overlap // avg_word_len
                    step = max(1, consumed_words_count - overlap_words)
                    i += step
                    
        return chunks
