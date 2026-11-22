"""Local SentenceTransformer embeddings (all-MiniLM-L6-v2, 384-d), L2-normalised.

- Lazy load (first use) so importing the app does not pay the model load cost.
- Async wrappers run the CPU-bound encode in a worker thread so the event loop is never blocked.
- Query embeddings are cached (LRU) because hybrid/MMR/eval paths embed the same query repeatedly.
"""
import logging
import os
import threading
from collections import OrderedDict
from typing import List

import numpy as np
from starlette.concurrency import run_in_threadpool

from app.config.settings import settings

logger = logging.getLogger(__name__)


class Embedder:
    def __init__(self, model_name: str = settings.EMBEDDING_MODEL):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        self._cache: "OrderedDict[str, np.ndarray]" = OrderedDict()
        self._cache_size = 512

    @property
    def model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    import torch
                    from sentence_transformers import SentenceTransformer
                    torch.set_num_threads(settings.TORCH_THREADS)
                    logger.info("Loading embedding model %s", self.model_name)
                    try:
                        self._model = SentenceTransformer(self.model_name, local_files_only=True)
                    except Exception:
                        if os.environ.get("HF_HUB_OFFLINE") == "1":
                            raise
                        self._model = SentenceTransformer(self.model_name)
                    dim = (getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension)()
                    if dim != settings.EMBEDDING_DIM:
                        raise RuntimeError(f"Embedding model outputs {dim} dims but EMBEDDING_DIM={settings.EMBEDDING_DIM}")
        return self._model

    @property
    def embedding_dimension(self) -> int:
        return settings.EMBEDDING_DIM

    def get_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        if not texts:
            return []
        embs = self.model.encode(texts, batch_size=settings.EMBEDDING_BATCH_SIZE, normalize_embeddings=True,
                                 show_progress_bar=False, convert_to_numpy=True)
        return [np.asarray(e, dtype=np.float32) for e in embs]

    def get_embedding(self, text: str) -> np.ndarray:
        cached = self._cache.get(text)
        if cached is not None:
            self._cache.move_to_end(text)
            return cached
        emb = self.get_embeddings([text])[0]
        self._cache[text] = emb
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return emb

    async def aembed_query(self, text: str) -> np.ndarray:
        if text in self._cache:
            return self.get_embedding(text)
        return await run_in_threadpool(self.get_embedding, text)

    async def aembed_documents(self, texts: List[str]) -> List[np.ndarray]:
        return await run_in_threadpool(self.get_embeddings, texts)


embedder = Embedder()
