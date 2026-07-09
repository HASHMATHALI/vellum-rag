import os
import threading
import logging
from typing import List, Tuple
import numpy as np
import faiss
from app.config.settings import settings
from app.embeddings.embedder import embedder

logger = logging.getLogger(__name__)

class FaissStore:
    """Thread-safe FAISS vector store service mapped directly to Database chunk IDs."""
    
    def __init__(self, index_path: str = None):
        self.index_path = index_path or os.path.join(settings.VECTOR_STORE_DIR, "faiss_index.bin")
        self.dimension = embedder.embedding_dimension
        self.index = None
        self.lock = threading.Lock()
        self._load_or_create_index()

    def _load_or_create_index(self):
        """Loads a FAISS index from disk or initializes a new one if missing."""
        with self.lock:
            if os.path.exists(self.index_path):
                try:
                    self.index = faiss.read_index(self.index_path)
                    logger.info(f"FaissStore: Successfully loaded index from {self.index_path}. Total vectors: {self.index.ntotal}")
                    return
                except Exception as e:
                    logger.error(f"FaissStore: Error loading index file ({e}). Re-initializing index.")
            
            # Create a base Flat IP (Inner Product) index for Cosine Similarity
            # Note: We need to normalize vectors before adding/searching to achieve exact Cosine Similarity
            base_index = faiss.IndexFlatIP(self.dimension)
            # Wrap in an IDMap so we can supply arbitrary database ID integers as labels
            self.index = faiss.IndexIDMap(base_index)
            logger.info("FaissStore: Initialized new FAISS IndexIDMap with IndexFlatIP.")

    def save_index(self):
        """Saves the current FAISS index state to disk."""
        with self.lock:
            try:
                # Ensure the vector_store dir exists
                os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
                faiss.write_index(self.index, self.index_path)
                logger.info(f"FaissStore: Index saved to {self.index_path}. Total vectors: {self.index.ntotal}")
            except Exception as e:
                logger.error(f"FaissStore: Failed to save index to disk ({e})")

    def add_vectors(self, vectors: List[np.ndarray], ids: List[int]):
        """Adds a list of normalized vectors mapped to their database IDs."""
        if not vectors or not ids:
            return
            
        # Ensure correct formats
        np_vectors = np.array(vectors, dtype=np.float32)
        np_ids = np.array(ids, dtype=np.int64)
        
        # Normalize vectors for Cosine Similarity (IP index)
        faiss.normalize_L2(np_vectors)
        
        with self.lock:
            self.index.add_with_ids(np_vectors, np_ids)
            
        # Write back changes to disk
        self.save_index()

    def delete_vectors(self, ids: List[int]):
        """Removes vectors matching specific database IDs from the FAISS store."""
        if not ids:
            return
        np_ids = np.array(ids, dtype=np.int64)
        with self.lock:
            try:
                self.index.remove_ids(np_ids)
                logger.info(f"FaissStore: Removed {len(ids)} vectors from index.")
            except Exception as e:
                logger.error(f"FaissStore: Error removing IDs from FAISS index ({e})")
        self.save_index()

    def search(self, query_vector: np.ndarray, k: int = 5) -> List[Tuple[int, float]]:
        """Search the FAISS index for the k most similar vectors. Returns list of (id, similarity_score)."""
        # Ensure embedding shape matches dimension
        np_query = np.array(query_vector, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(np_query)
        
        with self.lock:
            if self.index.ntotal == 0:
                return []
            
            # similarity scores (inner product on normalized vectors is cosine similarity)
            # return lists of shape [1, k]
            scores, ids = self.index.search(np_query, k)
            
        results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx != -1:  # -1 means not found (if k > total vectors)
                results.append((int(idx), float(score)))
        return results

    def clear(self):
        """Clears all vectors from the index and updates disk."""
        with self.lock:
            base_index = faiss.IndexFlatIP(self.dimension)
            self.index = faiss.IndexIDMap(base_index)
        self.save_index()
        logger.info("FaissStore: Cleared index.")

# Instantiate global vector store
vector_store = FaissStore()
