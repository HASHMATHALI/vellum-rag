import os
import logging
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class Embedder:
    """Singleton class to generate semantic text embeddings locally via SentenceTransformers.
    This runs offline, requires no API tokens, and resolves connection/authorization issues.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Embedder, cls).__new__(cls)
            logger.info("Initializing local SentenceTransformer model (all-MiniLM-L6-v2)...")
            # Enforce offline loading to prevent startup network timeouts
            os.environ["HF_HUB_OFFLINE"] = "1"
            try:
                cls._instance.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', local_files_only=True)
            except Exception as e:
                logger.warning(f"Offline load failed ({e}). Retrying without local_files_only restriction...")
                cls._instance.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
            logger.info("Local SentenceTransformer model loaded successfully.")
        return cls._instance

    def get_embedding(self, text: str) -> np.ndarray:
        """Get embedding vector for a single string of text."""
        emb = self.model.encode(text)
        return np.array(emb, dtype=np.float32)

    def get_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """Get embedding vectors for a list of strings."""
        if not texts:
            return []
        embs = self.model.encode(texts)
        return [np.array(emb, dtype=np.float32) for emb in embs]

    @property
    def embedding_dimension(self) -> int:
        """Returns the embedding output size, 384 for all-MiniLM-L6-v2."""
        return 384

# Instantiate the global embedder
embedder = Embedder()
