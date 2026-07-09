import threading
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer

class Embedder:
    """Thread-safe Singleton class to generate semantic text embeddings using SentenceTransformers."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Embedder, cls).__new__(cls)
                cls._instance._model = None
            return cls._instance

    def _init_model(self):
        """Lazy load the sentence transformer model if not already initialized."""
        if self._model is None:
            # Load the model. It was cached during docker build.
            self._model = SentenceTransformer("all-MiniLM-L6-v2")

    def get_embedding(self, text: str) -> np.ndarray:
        """Get embedding vector for a single string of text."""
        self._init_model()
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding

    def get_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """Get embedding vectors for a list of strings."""
        if not texts:
            return []
        self._init_model()
        embeddings = self._model.encode(texts, convert_to_numpy=True, batch_size=32)
        return [emb for emb in embeddings]

    @property
    def embedding_dimension(self) -> int:
        """Returns the embedding output size, 384 for all-MiniLM-L6-v2."""
        self._init_model()
        return self._model.get_sentence_embedding_dimension()

# Instantiate the global embedder
embedder = Embedder()
