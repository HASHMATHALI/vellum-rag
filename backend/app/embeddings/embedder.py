import os
import time
import logging
from typing import List
import numpy as np
import requests

logger = logging.getLogger(__name__)

class Embedder:
    """Singleton class to generate semantic text embeddings via HuggingFace's Free Inference API.
    This prevents local model loading and stays well under Render's 512MB RAM limit.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Embedder, cls).__new__(cls)
            cls._instance.api_url = "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"
            cls._instance.token = os.getenv("HF_TOKEN", "")
        return cls._instance

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        # Up to 5 retries if the model is currently cold-starting on HuggingFace servers
        for attempt in range(5):
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json={"inputs": texts, "options": {"wait_for_model": True}},
                    timeout=30
                )
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 503:
                    # Model is loading on HuggingFace. Wait and retry.
                    wait_time = response.json().get("estimated_time", 5.0)
                    logger.warning(f"HuggingFace model loading. Waiting {wait_time}s and retrying (attempt {attempt+1}/5)...")
                    time.sleep(min(wait_time, 5.0))
                    continue
                else:
                    raise Exception(f"HuggingFace API error {response.status_code}: {response.text}")
            except requests.RequestException as e:
                logger.error(f"Network error calling HuggingFace API: {e}")
                if attempt == 4:
                    raise
                time.sleep(2)
        
        raise Exception("Failed to load HuggingFace embedding model after 5 attempts.")

    def get_embedding(self, text: str) -> np.ndarray:
        """Get embedding vector for a single string of text."""
        res = self._call_api([text])
        return np.array(res[0], dtype=np.float32)

    def get_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """Get embedding vectors for a list of strings."""
        if not texts:
            return []
        res = self._call_api(texts)
        return [np.array(emb, dtype=np.float32) for emb in res]

    @property
    def embedding_dimension(self) -> int:
        """Returns the embedding output size, 384 for all-MiniLM-L6-v2."""
        return 384

# Instantiate the global embedder
embedder = Embedder()

